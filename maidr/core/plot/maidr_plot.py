from __future__ import annotations

from abc import ABC, abstractmethod

from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.util.environment import Environment


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
        A dictionary containing structured data about the plot, including type, title, axes labels, and data.

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

        # MAIDR data
        self.type = plot_type
        self._schema = {}

    def render(self) -> dict:
        """Initialize the MAIDR schema dictionary with basic plot information."""
        maidr_schema = {
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
        return "path[maidr='true']"

    def _extract_axes_data(self) -> dict:
        """Extract the plot's axes data"""
        engine = Environment.get_engine()
        if engine == "ts":
            return {MaidrKey.X: self.ax.get_xlabel(), MaidrKey.Y: self.ax.get_ylabel()}
        return {
            MaidrKey.X: {
                MaidrKey.LABEL: self.ax.get_xlabel(),
            },
            MaidrKey.Y: {
                MaidrKey.LABEL: self.ax.get_ylabel(),
            },
        }

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
