from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.environment import Environment
from maidr.util.mixin import LineExtractorMixin


class LinePlot(MaidrPlot, LineExtractorMixin):
    def __init__(self, ax: Axes) -> None:
        super().__init__(ax, PlotType.LINE)

    def _get_selector(self) -> str:
        return "g[maidr='true'] > path"

    def _extract_plot_data(self) -> list[dict]:
        plot = self.extract_line(self.ax)
        data = self._extract_line_data(plot)
        engine = Environment.get_engine()
        if engine == "ts":
            data = [data]

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_line_data(self, plot: Line2D | None) -> list[dict] | None:
        if plot is None or plot.get_xydata() is None:
            return None

        # Tag the elements for highlighting.
        self._elements.append(plot)

        return [
            {
                MaidrKey.X: float(x),
                MaidrKey.Y: float(y),
            }
            for x, y in plot.get_xydata()
        ]
