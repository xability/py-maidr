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
    scatter_positions : list of int
        Each trace's zero-based position among the subplot's scatter-family
        traces, in trace order. Required: see the note below.
    **kwargs : str
        Axis names forwarded to the parent class.

    Notes
    -----
    ``scatter_positions`` deliberately has no default. It previously fell back
    to the traces' own order, ``list(range(len(traces)))``, which is right
    only for a layer that owns every scatter trace on its subplot — an
    invariant that ended when steps were split into their own layers. For any
    other layer that default emitted ``nth-child(1), nth-child(2), …``
    pointing at whichever elements happened to occupy those positions: no
    error, nothing visibly wrong in the output, and the wrong element
    highlighted. A missing position is now a ``TypeError`` at the call site.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        scatter_positions: list[int],
        **kwargs: str,
    ) -> None:
        if not traces:
            raise ValueError("a multi-line layer needs at least one trace")
        self._validate_scatter_positions(scatter_positions, len(traces))

        super().__init__(traces[0], layout, PlotType.LINE, **kwargs)
        self._traces = traces
        self._scatter_positions = scatter_positions

    def _get_selector(self) -> list[str]:
        """
        Return one selector per line, matching the rendered line paths.

        Indices are subplot-relative, not layer-relative: a step trace
        declared before these lines shifts every one of them in the
        ``scatterlayer``, so numbering from 1 here would point each line at
        its predecessor and collide with the step layer's own selectors.

        Returns
        -------
        list of str
            One CSS selector per line, in trace order.
        """
        return [
            self._scatter_line_selector(position)
            for position in self._scatter_positions
        ]

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
