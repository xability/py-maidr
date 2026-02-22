from __future__ import annotations

import re
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
        """Extract axes labels and format configuration from the layout."""
        xaxis = self._layout.get("xaxis", {})
        yaxis = self._layout.get("yaxis", {})

        x_label = xaxis.get("title", "")
        if isinstance(x_label, dict):
            x_label = x_label.get("text", "")

        y_label = yaxis.get("title", "")
        if isinstance(y_label, dict):
            y_label = y_label.get("text", "")

        axes_data: dict = {
            MaidrKey.X: str(x_label) if x_label else "X",
            MaidrKey.Y: str(y_label) if y_label else "Y",
        }

        format_config = self._extract_format(xaxis, yaxis)
        if format_config:
            axes_data[MaidrKey.FORMAT] = format_config

        return axes_data

    @staticmethod
    def _extract_format(
        xaxis: dict, yaxis: dict
    ) -> dict[str, dict[str, Any]] | None:
        """Extract format configuration from Plotly axis settings.

        Parses ``tickformat``, ``tickprefix``, and ``ticksuffix`` from
        each axis and converts to MAIDR-compatible format dicts.
        """
        result: dict[str, dict[str, Any]] = {}

        x_fmt = PlotlyPlot._parse_axis_format(xaxis)
        if x_fmt:
            result["x"] = x_fmt

        y_fmt = PlotlyPlot._parse_axis_format(yaxis)
        if y_fmt:
            result["y"] = y_fmt

        return result if result else None

    @staticmethod
    def _parse_axis_format(axis: dict) -> dict[str, Any] | None:
        """Parse a single Plotly axis dict into a MAIDR format config.

        Handles Plotly's d3-format ``tickformat`` strings as well as
        ``tickprefix`` / ``ticksuffix`` for currency and percent.
        """
        tickformat = axis.get("tickformat", "")
        prefix = axis.get("tickprefix", "")
        suffix = axis.get("ticksuffix", "")

        # Check for date axis type even without tickformat/prefix/suffix
        if not tickformat and not prefix and not suffix:
            if axis.get("type") == "date":
                return {"type": "date", "dateFormat": None}
            return None

        # Currency via prefix ($, €, £, ¥)
        currency_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
        for symbol, code in currency_map.items():
            if symbol in prefix or symbol in tickformat:
                decimals = _extract_decimals(tickformat)
                return {"type": "currency", "decimals": decimals, "currency": code}

        # Percent via suffix or tickformat
        if suffix == "%" or (tickformat and "%" in tickformat):
            decimals = _extract_decimals(tickformat)
            return {"type": "percent", "decimals": decimals}

        # Scientific notation
        if tickformat and re.search(r"\.?\d*[eE]", tickformat):
            decimals = _extract_decimals(tickformat)
            return {"type": "scientific", "decimals": decimals}

        # Number with comma separator
        if tickformat and "," in tickformat:
            decimals = _extract_decimals(tickformat)
            return {"type": "number", "decimals": decimals}

        # Fixed decimal (e.g., ".2f")
        match = re.search(r"\.(\d+)f", tickformat) if tickformat else None
        if match:
            return {"type": "fixed", "decimals": int(match.group(1))}

        # Date format
        if axis.get("type") == "date":
            return {"type": "date", "dateFormat": tickformat or None}

        return None

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


def _extract_decimals(fmt: str) -> int | None:
    """Extract decimal places from a d3-format / Plotly tickformat string."""
    if not fmt:
        return None
    match = re.search(r"\.(\d+)", fmt)
    return int(match.group(1)) if match else None
