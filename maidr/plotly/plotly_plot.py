from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType


class PlotlyPlot(ABC):
    """
    Abstract base class for Plotly plots managed by the MAIDR system.

    Parameters
    ----------
    trace : dict
        The Plotly trace dictionary containing plot data.
    layout : dict
        The Plotly layout dictionary containing axes and title info.
    plot_type : PlotType
        The type of the plot to be created, as defined in the PlotType enum.
    """

    def __init__(self, trace: dict, layout: dict, plot_type: PlotType) -> None:
        self._trace = trace
        self._layout = layout
        self.type = plot_type
        self._schema: dict = {}

    @staticmethod
    def _to_native(val: Any) -> Any:
        """Convert numpy scalars to native Python types.

        Parameters
        ----------
        val : Any
            The value to convert.

        Returns
        -------
        Any
            A native Python type if the input was a numpy scalar,
            otherwise the original value.
        """
        if hasattr(val, "item"):
            return val.item()
        return val

    def render(self) -> dict:
        """Generate the MAIDR schema for this plot layer."""
        schema = {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: self.type,
            MaidrKey.TITLE: self._get_title(),
            MaidrKey.AXES: self._extract_axes_data(),
            MaidrKey.DATA: self._extract_plot_data(),
        }
        selector = self._get_selector()
        if selector:
            schema[MaidrKey.SELECTOR] = selector
        return schema

    def _get_selector(self) -> str:
        """Return a CSS selector for Plotly SVG elements."""
        return ""

    def _get_title(self) -> str:
        """Extract the plot title from the layout."""
        title = self._layout.get("title", "")
        if isinstance(title, dict):
            return title.get("text", "")
        return str(title) if title else ""

    def _extract_axes_data(self) -> dict:
        """Extract the axes labels from the layout."""
        xaxis = self._layout.get("xaxis", {})
        yaxis = self._layout.get("yaxis", {})

        x_label = xaxis.get("title", "")
        if isinstance(x_label, dict):
            x_label = x_label.get("text", "")

        y_label = yaxis.get("title", "")
        if isinstance(y_label, dict):
            y_label = y_label.get("text", "")

        return {
            MaidrKey.X: str(x_label) if x_label else "X",
            MaidrKey.Y: str(y_label) if y_label else "Y",
        }

    @abstractmethod
    def _extract_plot_data(self) -> list | dict:
        """Extract specific data from the Plotly trace."""
        raise NotImplementedError()

    @property
    def schema(self) -> dict:
        """Return the MAIDR schema of the plot as a dictionary."""
        if not self._schema:
            self._schema = self.render()
        return self._schema
