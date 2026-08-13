from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot
from maidr.plotly.step_shape import step_direction_of


class PlotlyStepPlot(PlotlyPlot):
    """
    A Plotly staircase trace, exported as a MAIDR step layer.

    Plotly has no step trace type: a step chart is a ``scatter`` trace whose
    ``line.shape`` makes plotly.js draw risers between the samples rather than
    interpolating across them. Read as a line, such a chart tells a blind user
    the value passed through every intermediate level, which is exactly what
    piecewise-constant data does not do.

    One instance covers both the single- and multi-series cases, mirroring
    ``PlotlyMultiLinePlot``: ``data`` is always a list of series. Every trace
    handed here must share one step convention — see
    :func:`maidr.plotly.step_shape.group_by_direction` — because a MAIDR layer
    carries a single ``stepDirection`` for all of its series.

    Parameters
    ----------
    traces : list of dict
        The staircase traces forming this layer, all of one convention.
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
    to the traces' own order, which is right only for a layer that owns every
    scatter trace on its subplot — and splitting steps by convention makes a
    step layer routinely *not* the leading one. An ``hv`` layer and a ``vh``
    layer both numbering from 1 would highlight the same elements, silently.
    A missing position is now a ``TypeError`` at the call site.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        scatter_positions: list[int],
        **kwargs: str,
    ) -> None:
        if not traces:
            raise ValueError("a step layer needs at least one trace")
        PlotlyPlot._validate_scatter_positions(scatter_positions, len(traces))

        super().__init__(traces[0], layout, PlotType.STEP, **kwargs)
        # Copied, not aliased: a caller mutating its list afterwards would
        # silently change this layer's selectors on the next render -- the
        # same wrong-element failure the required parameter exists to end.
        self._traces = list(traces)
        self._scatter_positions = list(scatter_positions)

    def _get_selector(self) -> list[str]:
        """
        Return one selector per series, matching the rendered line paths.

        A staircase renders as the same ``path.js-line`` a plain line does —
        plotly varies the path geometry, not the element — so the selectors are
        the line ones. The single-series case is still scoped by ``nth-child``
        rather than falling back to the unscoped ``.trace.scatter`` form, so a
        lone step trace sitting beside other scatter traces cannot match theirs.

        ``nth-child`` counts within the subplot's ``scatterlayer``, so the
        index has to be each trace's position *there* and not its position
        within this layer. Splitting steps by convention means a layer's
        traces are routinely not the leading ones: an ``hv`` layer and a
        ``vh`` layer both starting from 1 would highlight the same elements.

        A ``scattergl`` staircase gets none: it is painted to a canvas, so
        there is no path to address.

        Returns
        -------
        list of str
            One CSS selector per series, in trace order; empty for a WebGL
            layer.
        """
        # Positions filtered by the same predicate that filters the data, so
        # series *i* always addresses the element series *i* is drawn as --
        # see `_line_series_with_positions`.
        _, drawn_positions = self._line_series_with_positions(
            self._traces, self._scatter_positions
        )
        return self._scatter_line_selectors(self._traces, drawn_positions)

    def render(self) -> dict:
        """
        Build the base layer schema, then add the step convention.

        Returns
        -------
        dict
            The MAIDR layer schema, carrying ``stepDirection`` only when the
            traces authored a shape MAIDR has a name for. ``vhv`` reports none,
            so such a layer binds as a step without claiming a convention.
        """
        schema = super().render()

        direction = self._resolve_direction()
        if direction is not None:
            schema[MaidrKey.STEP_DIRECTION] = direction

        return schema

    def _resolve_direction(self) -> str | None:
        """
        Resolve the one step convention these traces share.

        Returns
        -------
        str or None
            The shared direction, or None when the traces disagree or their
            shape has no MAIDR equivalent. Disagreement should not reach here
            — the traces are grouped by direction before construction — so the
            check is a guard against a caller that skipped the grouping rather
            than an expected case.
        """
        directions = {step_direction_of(trace) for trace in self._traces}
        if len(directions) != 1:
            return None
        return directions.pop()

    def _extract_plot_data(self) -> list[list[dict]]:
        """
        Return the samples as a list of series.

        One point per **data sample**, never one per stairstep vertex: the
        frontend derives transitions and run lengths by comparing consecutive
        ``y`` values and reconstructs the riser geometry itself, so vertex-level
        data would double every level and misreport both.

        Returns
        -------
        list of list of dict
            ``{x, y}`` per point, with ``z`` set to the trace name when it has
            one. Empty series are dropped, matching ``PlotlyMultiLinePlot``.
        """
        series, _ = self._line_series_with_positions(
            self._traces, self._scatter_positions
        )
        return series
