from __future__ import annotations

from abc import ABC, abstractmethod

from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
# uuid is used to generate unique identifiers for each plot layer in the MAIDR schema.
import uuid


class MaidrPlot(ABC):
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

    def __init__(self, ax: Axes, plot_type: PlotType) -> None:
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
        Generate the MAIDR schema for this plot layer, including a unique id for layer identification.
        """
        # Generate a unique UUID for this layer to ensure each plot layer can be distinctly identified
        # in the MAIDR frontend. This supports robust layer switching.
        maidr_schema = {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: self.type,
            MaidrKey.TITLE: self.ax.get_title(),
            MaidrKey.AXES: self._extract_axes_data(),
            MaidrKey.DATA: self._extract_plot_data(),
        }

        # Include selector only if the plot supports highlighting.
        if self._support_highlighting:
            maidr_schema[MaidrKey.SELECTOR] = self._get_selector()

        return maidr_schema

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
        """Extract the plot's axes data"""
        x_labels = self.ax.get_xlabel()
        if not x_labels:
            x_labels = self.extract_shared_xlabel(self.ax)
        if not x_labels:
            x_labels = "X"
        return {MaidrKey.X: x_labels, MaidrKey.Y: self.ax.get_ylabel()}

    @abstractmethod
    def _extract_plot_data(self) -> list | dict:
        """Extract specific data from the plot."""
        raise NotImplementedError()

    @property
    def schema(self) -> dict:
        """Return the MAIDR schema of the plot as a dictionary."""
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
