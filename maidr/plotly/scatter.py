from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyScatterPlot(PlotlyPlot):
    """Extract data from a Plotly scatter trace with mode='markers'."""

    def __init__(self, trace: dict, layout: dict) -> None:
        super().__init__(trace, layout, PlotType.SCATTER)

    def _extract_plot_data(self) -> list[dict]:
        x = self._trace.get("x", [])
        y = self._trace.get("y", [])

        return [
            {MaidrKey.X: self._to_native(xv), MaidrKey.Y: self._to_native(yv)}
            for xv, yv in zip(x, y)
        ]

    @staticmethod
    def _to_native(val):
        """Convert numpy scalars to native Python types."""
        if hasattr(val, "item"):
            return val.item()
        return val
