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
    scatter_positions : list of int, optional
        Each trace's zero-based position among the subplot's scatter-family
        traces. Required whenever these are not the leading scatter traces of
        the subplot — which a step trace declared alongside them makes the
        normal case. Defaults to the traces' own order, correct only for a
        layer that owns every scatter trace on its subplot.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        scatter_positions: list[int] | None = None,
        **kwargs: str,
    ) -> None:
        super().__init__(traces[0], layout, PlotType.LINE, **kwargs)
        self._traces = traces
        self._scatter_positions = (
            list(range(len(traces)))
            if scatter_positions is None
            else scatter_positions
        )

    def _get_selector(self) -> list[str]:
        """
        Return one selector per line, matching the rendered line paths.

        Indices are subplot-relative, not layer-relative: a step trace
        declared before these lines shifts every one of them in the
        ``scatterlayer``, so numbering from 1 here would point each line at
        its predecessor and collide with the step layer's own selectors.

        A ``scattergl`` layer gets none: it is painted to a canvas, so there
        is no path to address.

        Returns
        -------
        list of str
            One CSS selector per line, in trace order; empty for a WebGL
            layer.
        """
        return self._scatter_line_selectors(
            self._traces, self._scatter_positions
        )

    def _extract_plot_data(self) -> list[list[dict]]:
        """Return multi-line data as a list-of-lists.

        Each inner list contains ``{x, y}`` dicts for one line, with an
        optional ``z`` key set to the trace name.
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
                    point[MaidrKey.Z] = name
                line_data.append(point)

            if line_data:
                all_lines.append(line_data)

        return all_lines
