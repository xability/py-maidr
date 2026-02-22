from __future__ import annotations

from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyCandlestickPlot(PlotlyPlot):
    """Extract data from a Plotly candlestick trace."""

    def __init__(self, trace: dict, layout: dict) -> None:
        super().__init__(trace, layout, PlotType.CANDLESTICK)

    @staticmethod
    def _to_native(val: Any) -> Any:
        """Convert numpy scalars to native Python types.

        Extends the base implementation to coerce numeric values to float.
        """
        if hasattr(val, "item"):
            return val.item()
        try:
            return float(val)
        except (ValueError, TypeError):
            return val

    def render(self) -> dict:
        base = super().render()
        base[MaidrKey.TITLE] = self._get_title() or "Candlestick Chart"
        return base

    def _extract_axes_data(self) -> dict:
        axes = super()._extract_axes_data()
        # Default axis labels for candlestick charts
        if axes.get(MaidrKey.X) == "X":
            axes[MaidrKey.X] = "Date"
        if axes.get(MaidrKey.Y) == "Y":
            axes[MaidrKey.Y] = "Price"
        return axes

    def _extract_plot_data(self) -> list[dict]:
        x = self._trace.get("x", [])
        open_vals = self._trace.get("open", [])
        high_vals = self._trace.get("high", [])
        low_vals = self._trace.get("low", [])
        close_vals = self._trace.get("close", [])

        data = []
        for i in range(len(x)):
            data.append(
                {
                    "value": str(x[i]) if i < len(x) else "",
                    "open": self._to_native(open_vals[i]) if i < len(open_vals) else 0,
                    "high": self._to_native(high_vals[i]) if i < len(high_vals) else 0,
                    "low": self._to_native(low_vals[i]) if i < len(low_vals) else 0,
                    "close": self._to_native(close_vals[i])
                    if i < len(close_vals)
                    else 0,
                }
            )
        return data
