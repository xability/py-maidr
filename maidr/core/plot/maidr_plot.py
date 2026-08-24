from __future__ import annotations

from abc import ABC, abstractmethod

from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.util.grid_position import topmost_subplotspec
from maidr.util.panel_title import panel_title
from maidr.util.mixin import FormatExtractorMixin

# uuid is used to generate unique identifiers for each plot layer in the MAIDR schema.
import uuid


#: Key a patch passes a layer's group name under.
#:
#: A chart that draws one layer per group -- a hue-split histogram, one KDE
#: curve per level -- leaves a reader several layers of a kind over one axis
#: with nothing to tell them apart, which is the position
#: ``MaidrLayer.name`` was added for (xability/maidr#828).
#:
#: Defined here because more than one layer type answers to it, and
#: **honoured per class** rather than read by this base: most subclasses call
#: ``super().__init__(ax, PlotType.X)`` without forwarding their keyword
#: arguments, so a key read here would arrive for some layer types and be
#: swallowed by the rest -- a promise kept by accident of how each
#: constructor happens to be written. ``HistPlot``, ``SmoothPlot``,
#: ``BoxPlot``, ``ScatterPlot`` and ``ErrorBarPlot`` opt in today, each in one
#: visible line -- :func:`group_name_of`.
#:
#: ``ScatterPlot`` reads it **second**, after its own ``HUE_GROUP``: that key
#: carries which *points* belong to the group, because the scatter patch
#: splits one collection between levels, while this one carries only the name
#: -- which is all a layer that is a whole group needs, and what a `regplot`
#: hands over (#612).
#:
#: ``EventPlot`` names its layers by other means -- row labels -- and is
#: unaffected, being passed neither this key nor anything that collides
#: with it.
#:
#: The value may be a **string** or a **callable returning one**. A string is
#: the name the patch already resolved; a callable is resolved at render, for
#: a chart whose legend does not exist yet when its layers register. A
#: ``pairplot(hue=...)`` is that chart: ``PairGrid.add_legend()`` runs after
#: every panel is drawn, so at registration there is no legend anywhere and
#: every diagonal came out anonymous while the scatters beside it were named
#: (#561). Each class that honours this key resolves the callable itself.
GROUP_NAME = "_maidr_group_name"


def group_name_of(kwargs: dict):
    """
    Read :data:`GROUP_NAME` out of a layer's keyword arguments.

    One line in each opting-in constructor, and the same line. Three copies
    of it drifted apart is a layer honouring the key in a way the others do
    not, which is the failure this whole mechanism exists to prevent -- and
    they had already begun to: ``SmoothPlot`` read the key with ``get`` where
    the others used ``pop``. Harmless there, since nothing reads it again and
    the base constructor is called without the keyword arguments, but it is
    the shape divergence takes.

    Parameters
    ----------
    kwargs : dict
        The layer's keyword arguments. The key is **popped**, so it does not
        travel on to a base class that would not know it.

    Returns
    -------
    str or callable or None
        What the patch handed over, or ``None`` when it handed over nothing
        this can use.
    """
    name = kwargs.pop(GROUP_NAME, None)
    return name if isinstance(name, str) or callable(name) else None


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
        ss = topmost_subplotspec(self.ax)
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

        # Extraction owns the whole element list, so it starts empty every time.
        #
        # A layer is rendered more than once -- `schema`, `elements` and
        # `set_id` each render when nothing is cached, and a caller may render
        # explicitly besides -- and every subclass appended without clearing,
        # so the list grew by a full set of artists per render. `elements` is
        # the ordered list the highlight machinery tags and the frontend
        # indexes into by point index, so a doubled list leaves point n
        # pointing at the artist for point n mod count. Nothing errors; the
        # outline simply lands on the wrong mark (#354).
        self._elements.clear()

        # Generate a unique UUID for this layer to ensure each plot layer can be distinctly identified
        # in the MAIDR frontend. This supports robust layer switching.
        maidr_schema = {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: self.type,
            # The caller's own title wins; the generated one names a panel
            # of a seaborn grid, which seaborn leaves untitled (#660).
            MaidrKey.TITLE: self.ax.get_title() or panel_title(self.ax),
            MaidrKey.AXES: axes_data,
            MaidrKey.DATA: self._extract_plot_data(),
        }

        # Include selector only if the plot supports highlighting.
        if self._support_highlighting:
            maidr_schema[MaidrKey.SELECTOR] = self._get_selector()

        return maidr_schema

    def _legend_title(self) -> str:
        """
        The grouping variable's name, as the legend titles it.

        A ``hue`` split names its groups in the legend entries and names the
        *variable* in the legend title, and the title is the only place that
        name appears -- so this is what an ``axes.z`` label is read from.
        Shared rather than restated: ``MultiLinePlot`` and ``PointPlot`` both
        need it and would otherwise drift apart if the convention changed.

        Read **live**, when the schema is built, while the group *names* are
        captured once as the plotting call is patched. A caller who retitles
        or relabels the legend in between can therefore make the two
        disagree -- the points would carry the names the chart was drawn
        with and the axis would carry the new title. Pre-existing, and
        sharper for ``PointPlot`` than for ``MultiLinePlot`` because there
        the divergence reaches per-point ``z`` values rather than one label.
        Reconciling them means either freezing the title at registration or
        re-reading the names at render, and both are changes to when a
        layer decides what it says.

        Returns
        -------
        str
            The title, or an empty string when there is no legend or no
            title on it.
        """
        legend = self.ax.get_legend()
        if legend is None:
            return ""
        title = legend.get_title()
        if title is None:
            return ""
        return title.get_text().strip()

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

    def extract_shared_xlabel(self, ax: Axes, y_threshold: float = 0.2) -> str:
        """Recover an x-axis label shared across a ``sharex`` axes group.

        A faceted figure often labels only one member of a shared-x group,
        or labels the figure rather than any axes. Either way the sibling
        axes report an empty ``get_xlabel()`` and would announce ``X``.

        Three sources, in order of how plainly they say "this labels your
        x axis": a sibling's own label, ``Figure.supxlabel``, and finally a
        figure-level text sitting in the bottom margin.

        Parameters
        ----------
        ax : Axes
            The axes whose shared x-label should be recovered.
        y_threshold : float, optional
            Figure-fraction y-position below which a figure text is treated
            as a bottom-margin (shared) x-label, by default 0.2.

        Returns
        -------
        str
            The recovered label, or ``""`` if none is found.

        Notes
        -----
        The margin scan is reached only when this axes really is in a
        shared-x group -- more than one sibling. Without that condition it
        fired on figures that share nothing, and read a bottom caption as
        the x label of every panel, announced on every data point with
        nothing marking it as a guess and no way to turn it off (#514).

        The condition is the method's own name taken seriously: an axes
        that shares its x with nobody has no *shared* label to recover, so
        an unrelated text in the margin is not a candidate for one.
        ``supxlabel`` needs no such guard, because a figure that calls it
        has said what the text means.
        """
        # First, try to get an xlabel from any shared axes.
        siblings = ax.get_shared_x_axes().get_siblings(ax)
        for shared_ax in siblings:
            xlabel = shared_ax.get_xlabel().strip()
            if xlabel:  # if non-blank
                return xlabel

        supxlabel = ax.figure.get_supxlabel().strip()
        if supxlabel:
            return supxlabel

        if len(siblings) > 1:
            for text in ax.figure.texts:
                if text.get_position()[1] < y_threshold:
                    label = text.get_text().strip()
                    if label:
                        return label

        return ""

    def extract_shared_ylabel(self, ax: Axes, x_threshold: float = 0.2) -> str:
        """Recover a y-axis label shared across a ``sharey`` axes group.

        When a faceted figure sets the y-label on only one member of a shared
        y-axis group, the sibling axes report an empty ``get_ylabel()``. This
        mirrors :meth:`extract_shared_xlabel`: it first scans shared-y siblings
        for a non-blank label, then ``Figure.supylabel``, then a figure-level
        text sitting in the left margin -- that last only when the axes is
        genuinely in a shared-y group. See :meth:`extract_shared_xlabel` for
        why that condition is there.

        Parameters
        ----------
        ax : Axes
            The axes whose shared y-label should be recovered.
        x_threshold : float, optional
            Figure-fraction x-position below which a figure text is treated as
            a left-margin (shared) y-label, by default 0.2.

        Returns
        -------
        str
            The recovered label, or ``""`` if none is found.
        """
        # First, try to get a ylabel from any shared axes. Whitespace-only
        # labels are treated as blank (unavailable), consistent with maidr's
        # blank-label handling.
        siblings = ax.get_shared_y_axes().get_siblings(ax)
        for shared_ax in siblings:
            ylabel = shared_ax.get_ylabel().strip()
            if ylabel:  # if non-blank
                return ylabel

        supylabel = ax.figure.get_supylabel().strip()
        if supylabel:
            return supylabel

        # Only for an axes that really is in a shared-y group -- see
        # :meth:`extract_shared_xlabel` for what the unguarded scan cost.
        if len(siblings) > 1:
            for text in ax.figure.texts:
                if text.get_position()[0] < x_threshold:
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
            y_label = self.extract_shared_ylabel(self.ax)
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
