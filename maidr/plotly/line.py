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
    scatter_position : int, optional
        The trace's zero-based position among the subplot's scatter-family
        traces. Pass this whenever the subplot holds more than this one
        scatter trace — a step trace beside it makes that the normal case.
    **kwargs : str
        Axis names forwarded to the parent class.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        scatter_position: int | None = None,
        **kwargs: str,
    ) -> None:
        super().__init__(trace, layout, PlotType.LINE, **kwargs)
        self._scatter_position = scatter_position

    def _get_selector(self) -> list[str]:
        """
        Return the selector for this line's rendered path.

        With a known position the selector is scoped to that one trace.
        Without one it falls back to the unscoped subplot-wide form, which
        assumes this is the only ``path.js-line`` on the subplot. That
        assumption held while a line layer owned every scatter trace, but a
        step trace renders as ``path.js-line`` too, so the unscoped form
        would match both. ``PlotlyMaidr`` therefore always supplies a
        position; the fallback is for direct/standalone construction.

        Returns
        -------
        list of str
            A single CSS selector.
        """
        if self._scatter_position is None:
            return [f"{self._subplot_css_prefix()}.trace.scatter path.js-line"]
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
