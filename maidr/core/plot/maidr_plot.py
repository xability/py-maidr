from __future__ import annotations

from abc import ABC, abstractmethod

from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.util.mixin import FormatExtractorMixin

# uuid is used to generate unique identifiers for each plot layer in the MAIDR schema.
import uuid


class MaidrPlot(ABC, FormatExtractorMixin):
    """
    Abstract base class for plots managed by the MAIDR system.

    Parameters
    ----------
    ax : Axes
        The ``matplotlib.axes.Axes`` object where the plot will be drawn.
    plot_type : PlotType
        The type of the plot to be created, as defined in the PlotType enum.

    Attributes
    ----------
    ax : Axes
        The ``matplotlib.axes.Axes`` object associated with this plot.
    type : PlotType
        The specific type of the plot.
    _schema : dict
        A dictionary containing structured data about the plot, including type, title,
        axes labels, and data.

    Methods
    -------
    schema()
        Returns a dictionary containing MAIDR data about the plot.
    set_id(maidr_id: str)
        Sets a unique identifier for the plot in the schema.
    """

    def __init__(self, ax: Axes, plot_type: PlotType, **kwargs) -> None:
        # graphic object
        self.ax = ax
        self._support_highlighting = True
        self._elements = []
        ss = self.ax.get_subplotspec()
        # Handle cases where subplotspec is None (dynamically created axes)
        if ss is not None:
            self.row_index = ss.rowspan.start
            self.col_index = ss.colspan.start
        else:
            self.row_index = 0
            self.col_index = 0

        # MAIDR data
        self.type = plot_type
        self._schema = {}

    def render(self) -> dict:
        """
        Generate the MAIDR schema for this plot layer, including a unique id for
        layer identification.

        The ``axes`` payload follows the canonical per-axis ``AxisConfig`` form:
        each of ``x``, ``y``, ``z`` (when present) is a dict that may contain
        ``label``, ``min``, ``max``, ``tickStep``, and ``format``. ``format`` is
        nested *inside* each axis, never emitted as a sibling.
        """
        # Extract axes data first (per-axis AxisConfig objects).
        axes_data = self._extract_axes_data()

        # Merge per-axis format configuration into each AxisConfig under its own
        # "format" key. The legacy sibling "axes.format" emission has been removed.
        format_config = self.extract_format(self.ax)
        if format_config:
            self._merge_format_into_axes(axes_data, format_config)

        # Generate a unique UUID for this layer to ensure each plot layer can be distinctly identified
        # in the MAIDR frontend. This supports robust layer switching.
        maidr_schema = {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: self.type,
            MaidrKey.TITLE: self.ax.get_title(),
            MaidrKey.AXES: axes_data,
            MaidrKey.DATA: self._extract_plot_data(),
        }

        # Include selector only if the plot supports highlighting.
        if self._support_highlighting:
            maidr_schema[MaidrKey.SELECTOR] = self._get_selector()

        return maidr_schema

    @staticmethod
    def _axis_config(
        label: str | None = None,
        *,
        min: float | None = None,
        max: float | None = None,
        tick_step: float | None = None,
        format: dict | None = None,
    ) -> dict:
        """
        Build a canonical ``AxisConfig`` dict, emitting only non-None properties.

        Parameters
        ----------
        label : str, optional
            Human-readable axis label.
        min : float, optional
            Numeric lower bound (numeric axes only).
        max : float, optional
            Numeric upper bound (numeric axes only).
        tick_step : float, optional
            Tick spacing (numeric axes only).
        format : dict, optional
            Per-axis ``AxisFormat`` object.

        Returns
        -------
        dict
            A sparse ``AxisConfig`` dict. May be empty.
        """
        cfg: dict = {}
        if label is not None:
            cfg[MaidrKey.LABEL] = label
        if min is not None:
            cfg[MaidrKey.MIN] = min
        if max is not None:
            cfg[MaidrKey.MAX] = max
        if tick_step is not None:
            cfg[MaidrKey.TICK_STEP] = tick_step
        if format is not None:
            cfg[MaidrKey.FORMAT] = format
        return cfg

    @staticmethod
    def _merge_format_into_axes(axes_data: dict, format_config: dict) -> None:
        """
        Nest a per-axis format mapping ``{"x": {...}, "y": {...}}`` into each
        corresponding ``AxisConfig`` inside ``axes_data``.

        If an axis exists in ``format_config`` but not in ``axes_data``, a new
        ``AxisConfig`` dict is created for it.
        """
        for axis_key, fmt in format_config.items():
            # Normalize str-enum keys (e.g., MaidrKey.X) against plain "x"/"y"/"z".
            key = axis_key.value if hasattr(axis_key, "value") else axis_key
            target_key = None
            for candidate in (key, MaidrKey.X, MaidrKey.Y, MaidrKey.Z):
                if candidate in axes_data:
                    ck = candidate.value if hasattr(candidate, "value") else candidate
                    if ck == key:
                        target_key = candidate
                        break
            if target_key is None:
                # Map plain string back to enum for consistent key typing.
                target_key = {
                    "x": MaidrKey.X,
                    "y": MaidrKey.Y,
                    "z": MaidrKey.Z,
                }.get(key, key)
                axes_data[target_key] = {}
            axis_cfg = axes_data[target_key]
            if not isinstance(axis_cfg, dict):
                # Defensive: legacy string slipped through; upgrade to AxisConfig.
                axis_cfg = {MaidrKey.LABEL: axis_cfg}
                axes_data[target_key] = axis_cfg
            axis_cfg[MaidrKey.FORMAT] = fmt

    def _get_selector(self) -> str:
        """Return the CSS selector for highlighting elements."""
        return "g[maidr='true'] > path"

    def extract_shared_xlabel(self, ax, y_threshold=0.2):
        # First, try to get an xlabel from any shared axes.
        siblings = ax.get_shared_x_axes().get_siblings(ax)
        for shared_ax in siblings:
            xlabel = shared_ax.get_xlabel()
            if xlabel:  # if non-empty
                return xlabel

        for text in ax.figure.texts:
            if text.get_position()[1] < y_threshold:
                label = text.get_text().strip()
                if label:
                    return label

        return ""

    def _extract_axes_data(self) -> dict:
        """
        Extract the plot's axes data as per-axis ``AxisConfig`` objects.

        Returns
        -------
        dict
            ``{"x": {"label": ...}, "y": {"label": ...}}``. Keys ``x`` and ``y``
            are always present; subclasses may add ``z`` when appropriate.
        """
        x_label = self.ax.get_xlabel()
        if not x_label:
            x_label = self.extract_shared_xlabel(self.ax)
        if not x_label:
            x_label = "X"

        y_label = self.ax.get_ylabel()
        if not y_label:
            y_label = "Y"

        return {
            MaidrKey.X: self._axis_config(label=x_label),
            MaidrKey.Y: self._axis_config(label=y_label),
        }

    @abstractmethod
    def _extract_plot_data(self) -> list | dict:
        """Extract specific data from the plot."""
        raise NotImplementedError()

    @property
    def schema(self) -> dict:
        """Return the MAIDR schema of the plot as a dictionary.

        The emitted ``axes`` payload follows the canonical per-axis form —
        keys ⊆ ``{x, y, z}``; each value is an ``AxisConfig`` dict with
        optional ``label``, ``min``, ``max``, ``tickStep``, and ``format``
        fields. ``format``/``min``/``max``/``tickStep``/``fill``/``level``
        never appear as siblings of ``x``/``y``/``z``.
        """
        if not self._schema:
            self._schema = self.render()
        return self._schema

    @property
    def elements(self) -> list:
        if not self._schema:
            self._schema = self.render()
        return self._elements

    def set_id(self, maidr_id: str) -> None:
        """Set the unique identifier for the plot within the MAIDR schema."""
        if not self._schema:
            self._schema = self.render()
        self._schema[MaidrKey.ID] = maidr_id
