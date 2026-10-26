from __future__ import annotations

import math

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, tick_names
from maidr.plotly.step_shape import shared_step_direction


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
        # see `_line_series_with_positions`. The pass is shared with
        # `_extract_plot_data` rather than repeated: see `_drawn_line_series`.
        _, drawn_positions = self._drawn_line_series(
            self._traces, self._scatter_positions
        )
        return self._scatter_line_selectors(self._traces, drawn_positions)

    def render(self) -> dict:
        """
        Build the base layer schema, then add the step convention and the
        names of the levels.

        Returns
        -------
        dict
            The MAIDR layer schema, carrying ``stepDirection`` only when the
            traces authored a shape MAIDR has a name for. ``vhv`` reports none,
            so such a layer binds as a step without claiming a convention.
            Every point whose ``y`` sits on a named y tick carries the name as
            its ``label``.
        """
        schema = super().render()

        # Disagreement should not reach here -- the traces are grouped by
        # direction before construction -- so a None from a mixed set is a
        # guard against a caller that skipped the grouping rather than an
        # expected case. `vhv` reaching it is expected: MAIDR has no name for
        # that convention.
        direction = shared_step_direction(self._traces)
        if direction is not None:
            schema[MaidrKey.STEP_DIRECTION] = direction

        self._attach_level_names(schema[MaidrKey.DATA])

        return schema

    def _attach_level_names(self, data: list[list[dict]]) -> None:
        """
        Name each point's level from the y axis's named ticks.

        A hypnogram codes its stages as numbers so they can drive the pitch,
        the braille and the range, and names them with ``tickvals`` and
        ``ticktext``. Only the codes were read, so a reader heard "Sleep stage
        is 4" where the chart says Awake. Each point whose ``y`` sits on a
        named tick now carries the name as ``label``, which the core announces
        in place of the number while ``y`` keeps driving everything else --
        what the matplotlib ``StepPlot`` does from named y ticks. A point
        between named ticks, and every point of an axis that names none, is
        left as it was.

        Only the y axis is read. A plotly staircase is a scatter trace, which
        has no orientation: it holds its y values and steps along x, and
        ``label`` names the level a ``y`` encodes.

        Parameters
        ----------
        data : list of list of dict
            The layer's series, as :meth:`_extract_plot_data` returns them.
            Changed in place.
        """
        levels = tick_names(self._layout, self._yaxis_name)
        if not levels:
            return

        # The plain strings, as `_line_series_with_positions` keys the points.
        ky, label = MaidrKey.Y.value, MaidrKey.LABEL.value
        for series in data:
            for point in series:
                try:
                    name = _level_at(levels, float(point.get(ky)))
                except (TypeError, ValueError):
                    continue
                if name:
                    point[label] = name

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
        series, _ = self._drawn_line_series(self._traces, self._scatter_positions)
        return series


def _level_at(levels: dict[float, str], value: float) -> str | None:
    """
    Return the name of the tick a value sits on, or None.

    Matched by closeness rather than by equality, so a value computed as
    ``0.1 + 0.2`` sits on a tick placed at ``0.3``, as it does on the chart.

    Parameters
    ----------
    levels : dict of float to str
        ``{tick position: name}``, as :func:`tick_names` returns it.
    value : float
        A point's ``y``.

    Returns
    -------
    str or None
        The tick's name, or None when the value is on no named tick.
    """
    for position, name in levels.items():
        if math.isclose(value, position, rel_tol=1e-9, abs_tol=1e-12):
            return name
    return None
