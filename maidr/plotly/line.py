from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyLinePlot(PlotlyPlot):
    """
    Extract data from a Plotly scatter trace with mode='lines'.

    Parameters
    ----------
    trace : dict
        The scatter/lines trace dict.
    layout : dict
        The Plotly figure layout.
    scatter_position : int
        The trace's zero-based position among the subplot's scatter-family
        traces. Required: it is the only thing that makes this layer's
        selector address *this* trace rather than whichever one happens to
        sit first. See the class note below on why it has no default.
    **kwargs : str
        Axis names forwarded to the parent class.

    Notes
    -----
    ``scatter_position`` deliberately has no default. It previously fell back
    to an unscoped ``.trace.scatter path.js-line``, which over-matched — a
    step trace renders as ``path.js-line`` too, so the fallback selected it
    as well. A caller that cannot supply a real position has to say so at the
    call site now, rather than silently getting a selector that is wrong in a
    way nothing reports.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        scatter_position: int,
        **kwargs: str,
    ) -> None:
        # Routed through the list validator so the non-negative rule has
        # one home rather than a scalar copy that can drift from it.
        PlotlyPlot._validate_scatter_positions([scatter_position], 1)

        super().__init__(trace, layout, PlotType.LINE, **kwargs)
        self._scatter_position = scatter_position

    def _get_selector(self) -> list[str]:
        """
        Return the selector for this line's rendered path.

        Returns
        -------
        list of str
            A single CSS selector, scoped to this trace's position among the
            subplot's scatter traces.
        """
        return [self._scatter_line_selector(self._scatter_position)]

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
                point[MaidrKey.Z] = name
            line_data.append(point)

        return [line_data]
