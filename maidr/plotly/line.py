from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyLinePlot(PlotlyPlot):
    """Extract data from a Plotly scatter trace with mode='lines'."""

    def __init__(self, trace: dict, layout: dict) -> None:
        super().__init__(trace, layout, PlotType.LINE)

    def _extract_plot_data(self) -> list[list[dict]]:
        x = self._trace.get("x", [])
        y = self._trace.get("y", [])
        name = self._trace.get("name", "")

        line_data = []
        for xv, yv in zip(x, y):
            point: dict = {
                MaidrKey.X: self._to_native(xv),
                MaidrKey.Y: self._to_native(yv),
            }
            if name:
                point[MaidrKey.FILL] = name
            line_data.append(point)

        return [line_data]

    @staticmethod
    def _to_native(val):
        """Convert numpy scalars to native Python types."""
        if hasattr(val, "item"):
            return val.item()
        return val
