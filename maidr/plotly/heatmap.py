from __future__ import annotations

from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyHeatmapPlot(PlotlyPlot):
    """Extract data from a Plotly heatmap trace."""

    def __init__(self, trace: dict, layout: dict) -> None:
        super().__init__(trace, layout, PlotType.HEAT)

    @staticmethod
    def _to_native(val: Any) -> Any:
        """Convert numpy scalars to native Python types.

        Extends the base implementation to also convert numeric strings
        and non-numpy numeric types to floats.
        """
        if hasattr(val, "item"):
            return val.item()
        if isinstance(val, str):
            return val
        try:
            return float(val)
        except (TypeError, ValueError):
            return val

    def _extract_plot_data(self) -> dict:
        z = self._trace.get("z", [])
        x = self._trace.get("x", None)
        y = self._trace.get("y", None)

        # Convert z matrix to list of lists of native floats
        points = []
        for row in z:
            points.append([self._to_native(v) for v in row])

        result: dict = {MaidrKey.POINTS: points}

        if x is not None:
            result[MaidrKey.X] = [self._to_native(v) for v in x]
        if y is not None:
            result[MaidrKey.Y] = [self._to_native(v) for v in y]

        return result

    def _extract_axes_data(self) -> dict:
        """Extract axes data, including fill label for heatmaps."""
        base = super()._extract_axes_data()
        # Add fill label from colorbar title if available
        colorbar = self._trace.get("colorbar", {})
        fill_label = ""
        if isinstance(colorbar, dict):
            title = colorbar.get("title", "")
            if isinstance(title, dict):
                fill_label = title.get("text", "")
            elif title:
                fill_label = str(title)
        if fill_label:
            base[MaidrKey.FILL] = fill_label
        return base
