from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyMultiLinePlot(PlotlyPlot):
    """Extract data from multiple Plotly scatter/lines traces as one layer.

    Mirrors the matplotlib ``MultiLinePlot`` which collects all lines on
    the same axes into a single MAIDR layer with a list-of-lists data
    format: ``[[line1_points], [line2_points], ...]``.

    Parameters
    ----------
    traces : list[dict]
        All scatter/lines trace dicts belonging to the multi-line plot.
    layout : dict
        The Plotly figure layout.
    """

    def __init__(self, traces: list[dict], layout: dict) -> None:
        super().__init__(traces[0], layout, PlotType.LINE)
        self._traces = traces

    def _get_selector(self) -> str:
        return ".trace.scatter path.js-line"

    def _extract_plot_data(self) -> list[list[dict]]:
        """Return multi-line data as a list-of-lists.

        Each inner list contains ``{x, y}`` dicts for one line, with an
        optional ``fill`` key set to the trace name.
        """
        all_lines: list[list[dict]] = []

        for trace in self._traces:
            x = trace.get("x", [])
            y = trace.get("y", [])
            name = trace.get("name", "")

            line_data: list[dict] = []
            for xv, yv in zip(x, y):
                point: dict = {
                    MaidrKey.X: self._to_native(xv),
                    MaidrKey.Y: self._to_native(yv),
                }
                if name:
                    point[MaidrKey.FILL] = name
                line_data.append(point)

            if line_data:
                all_lines.append(line_data)

        return all_lines
