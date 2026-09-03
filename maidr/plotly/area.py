"""Plotly area charts, which arrive as scatter traces carrying a stackgroup.

`px.area` produces a `Scatter`, and the only thing separating it from a line
is `stackgroup`. The adapter had no area handling at all, so every one of them
fell through to `line` -- a reader was not told the bands are filled, that they
stack, or what the running total at each x is, which is the reason someone
draws this chart rather than a multi-line one (#392).
"""

from __future__ import annotations

import math
from typing import Any, Hashable

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot
from maidr.plotly.step_shape import (
    is_scatter_family_trace,
    renders_through_webgl,
    shared_step_direction,
)

#: The values ``groupnorm`` takes when plotly rescales a stack to a common
#: total -- its own switch for a 100% stacked area, and the counterpart of
#: ``barnorm`` on the bar path -- and the total each scales a position to.
#: One table rather than a set beside a dict, so the type a stack is given
#: and the scale its values are rescaled by cannot disagree (#409's lesson
#: on the bar path).
_GROUPNORM_SCALES: dict[str, float] = {"percent": 100.0, "fraction": 1.0}
_NORMALISING_GROUPNORMS = frozenset(_GROUPNORM_SCALES)


def is_area_trace(trace: dict) -> bool:
    """Whether plotly fills this trace down to a baseline.

    ``stackgroup`` is the whole signal, and it is structural rather than a
    display string: plotly stacks traces that share one and leaves traces with
    an empty one alone. Measured in Chromium -- a trace with ``stackgroup``
    set resolves to ``fill: "tonexty"`` and its calcdata carries an ``s`` key
    holding the series' own value, while a plain line resolves to
    ``fill: "none"`` and has no ``s`` at all.

    A WebGL trace is excluded because plotly does not stack one. ``scattergl``
    has no ``stackgroup`` attribute at all -- ``go.Scattergl(stackgroup="one")``
    raises ``Bad property path`` -- and plotly.js ignores the key on a raw
    ``scattergl`` dict that carries it anyway: measured in Chromium, such a
    trace comes back with ``fill: "none"``, no ``stackgroup`` in ``_fullData``
    and nothing accumulated. Reading it as an area would announce a filled,
    stacked band where plotly draws a plain line.

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    bool
        True when the trace is drawn as a filled band.
    """
    return (
        bool(trace.get("stackgroup"))
        and is_scatter_family_trace(trace)
        and not renders_through_webgl(trace)
    )


def area_stack_groups(traces: list[dict]) -> list[list[dict]]:
    """Split area traces into the stacks plotly actually accumulates.

    Traces stack only with others sharing their ``stackgroup``. Two groups on
    one subplot are two independent stacks, and measured that way: given
    ``stackgroup='one'`` and ``stackgroup='two'``, each series' calcdata ``y``
    equals its own ``s`` -- nothing accumulated across the two -- where within
    one group the second series' ``y`` is the running total.

    Groups come back in first-seen order so the emitted layers follow plotly's
    own trace order rather than a sorted one.

    Parameters
    ----------
    traces : list[dict]
        The subplot's area traces, in declaration order.

    Returns
    -------
    list[list[dict]]
        One list per stack group.
    """
    groups: dict[str, list[dict]] = {}
    for trace in traces:
        groups.setdefault(str(trace.get("stackgroup")), []).append(trace)
    return list(groups.values())


def area_plot_type(traces: list[dict]) -> PlotType:
    """Which area type a stack group is.

    A lone band has nothing stacked on it, so it is a plain ``area`` -- the
    same distinction the matplotlib path draws for a single ``stackplot``
    band. ``groupnorm`` then separates a stack from a normalised one, exactly
    as ``barnorm`` does for bars.
    """
    if any(t.get("groupnorm") in _NORMALISING_GROUPNORMS for t in traces):
        return PlotType.NORMALIZED_AREA
    if len(traces) > 1:
        return PlotType.STACKED_AREA
    return PlotType.AREA


def groupnorm_scale(traces: list[dict]) -> float | None:
    """The total a stack's ``groupnorm`` scales each position to.

    Read from the first trace in the stack that sets it, not the first trace.
    plotly's ``stack_defaults`` reads ``groupnorm`` off the group's first
    trace or, failing that, the first later trace that sets it -- it flags
    ``groupnormFound`` and ignores the setting on every trace after -- so a
    ``groupnorm`` on the second trace alone still governs the whole stack.
    :func:`area_plot_type` already types the stack by that rule; the scale
    has to be read by the same one or the type and the values part company.

    Parameters
    ----------
    traces : list[dict]
        The stack's traces, in declaration order.

    Returns
    -------
    float or None
        ``100.0`` for ``percent``, ``1.0`` for ``fraction``, and ``None``
        when plotly normalises nothing -- ``None``, ``""`` and anything
        unrecognised alike -- so the caller emits the values untouched.
    """
    for trace in traces:
        groupnorm = trace.get("groupnorm")
        if isinstance(groupnorm, str) and groupnorm in _GROUPNORM_SCALES:
            return _GROUPNORM_SCALES[groupnorm]
    return None


def _finite(value: Any) -> bool:
    """Whether a value takes part in a column total.

    ``None`` and a non-finite number are gaps: plotly leaves them out of the
    sum, and they come back as they went in rather than as a share.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return math.isfinite(value)


def normalised_bands(bands: list[list[dict]], scale: float) -> list[list[dict]]:
    """Rescale every band's value to its share of its column, as plotly does.

    The rule is plotly.js's scatter cross-trace calc, not the bar one. For a
    stack group it sums every band's own value at each position and then
    divides each by ``(groupnorm === "fraction" ? m : m / 100) || 1``. Two
    consequences that :func:`maidr.plotly.barnorm.stack_shares` does not
    share, which is why that helper is not reused here:

    * A position whose total is zero divides by **1**, so its values come
      back unchanged -- zeros stay zeros -- where ``barnorm`` leaves such a
      position undefined.
    * There is no per-sign split and no ``barmode``: one signed total serves
      every band at the position.

    Positions are keyed by the emitted ``x`` and matched by value, not by
    index, so a band that skips an x contributes nothing to that column and
    the rest are not shifted -- plotly's default ``stackgaps`` of
    ``"infer zero"``. A ``None`` or non-finite value is left out of the
    total and left as it is.

    Parameters
    ----------
    bands : list of list of dict
        One list of ``{x, y[, z]}`` points per drawn band, as
        ``_line_series_with_positions`` builds them.
    scale : float
        ``100.0`` or ``1.0``, from :func:`groupnorm_scale`.

    Returns
    -------
    list of list of dict
        New points, aligned elementwise with *bands*, with every finite ``y``
        replaced by its share. The input is not touched, so a layer rendered
        twice does not rescale an already rescaled stack.
    """
    totals: dict[Hashable, float] = {}
    for band in bands:
        for point in band:
            value = point[MaidrKey.Y]
            if _finite(value):
                totals[point[MaidrKey.X]] = totals.get(point[MaidrKey.X], 0.0) + value

    shares: list[list[dict]] = []
    for band in bands:
        row: list[dict] = []
        for point in band:
            value = point[MaidrKey.Y]
            if _finite(value):
                total = totals[point[MaidrKey.X]]
                # plotly's `|| 1`: a zero total divides by one, not by zero.
                divisor = (total if scale == 1.0 else total / scale) or 1.0
                point = {**point, MaidrKey.Y: value / divisor}
            row.append(point)
        shares.append(row)
    return shares


class PlotlyAreaPlot(PlotlyPlot):
    """One stack of filled bands.

    Emits each band's **own** value, with the series name alongside, matching
    what :class:`~maidr.core.plot.areaplot.AreaPlot` produces for
    ``stackplot``. The running total is the core's to derive: a stacked area
    trace already sums its bands, and emitting a total here would give it two
    sources that could disagree.

    Plotly agrees about which number is which. Its calcdata carries both --
    ``s`` for the band's own value and ``y`` for the running total -- and for
    two series of ``1,2,3`` and ``10,20,30`` the second's ``y`` comes back
    ``11,22,33``. So ``trace["y"]``, which the Python side has, is the band's
    own value and needs no un-accumulating. That is the opposite of the
    matplotlib and ggplot2 hazard, where the built data holds the cumulative
    top and reading it straight through announces totals as values.

    Parameters
    ----------
    traces : list of dict
        The stack's traces, in declaration order. At least one is required.
    layout : dict
        The figure layout the axis titles and ranges come from.
    plot_type : PlotType
        Which of ``AREA``/``STACKED_AREA``/``NORMALIZED_AREA`` this stack is,
        as resolved by :func:`area_plot_type`.
    scatter_positions : list of int
        Each trace's zero-based position among the subplot's scatter-family
        traces. Required rather than defaulted: an area shares its
        ``scatterlayer`` with the lines beside it, so numbering from zero
        here would point each band at another layer's element.
    **kwargs
        Forwarded to :class:`~maidr.plotly.plotly_plot.PlotlyPlot`.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        plot_type: PlotType,
        scatter_positions: list[int],
        **kwargs: str,
    ) -> None:
        if not traces:
            raise ValueError("an area layer needs at least one trace")
        PlotlyPlot._validate_scatter_positions(scatter_positions, len(traces))

        super().__init__(traces[0], layout, plot_type, **kwargs)
        # Copied, not aliased: a caller mutating its list afterwards would
        # silently change this layer's selectors on the next render -- the
        # same wrong-element failure the required parameter exists to end.
        self._traces = list(traces)
        self._scatter_positions = list(scatter_positions)

    def render(self) -> dict:
        """Build the base layer schema, then add the step convention.

        ``line.shape`` and a fill are independent attributes in plotly, so a
        band can be a staircase: a stacked step area is the standard way to
        draw a cumulative count that changes at discrete events. Read as a
        smoothly interpolated band it tells a reader the wrong thing about
        every interval -- that the value slid between samples when it in fact
        held and then jumped (#413).

        The two facts ride together rather than one displacing the other. An
        area that is also a staircase is still an area, so the layer keeps its
        area type and carries ``stepDirection`` alongside it; the core reads
        both, and announces the fill *and* what happens between samples.

        Returns
        -------
        dict
            The MAIDR layer schema, carrying ``stepDirection`` only when every
            band in the stack authored one shape MAIDR has a name for.
        """
        schema = super().render()

        # A stack cannot be split by direction the way the step layers are:
        # the bands of one `stackgroup` are one stack, and separating them
        # would leave the core summing a part of it and announcing that as the
        # total. So a mixed stack is expected here, and it says nothing rather
        # than describing one of its bands wrongly.
        direction = shared_step_direction(self._traces)
        if direction is not None:
            schema[MaidrKey.STEP_DIRECTION] = direction

        return schema

    def _get_selector(self) -> list[str]:
        """One selector per drawn band, in the order the bands are emitted.

        Reuses the scatter-family positions the subplot already assigns, since
        an area trace is a scatter trace and sits in the same ``scatterlayer``
        as the lines beside it.

        Positions are filtered by the same predicate that filters the data, so
        band *i* always addresses the element band *i* is drawn as. A band with
        no points is not merely empty in the schema -- plotly gives it no DOM
        node at all, so every later band shifts up one. Measured in Chromium
        with an empty band between two drawn ones: the ``scatterlayer`` holds
        two ``.trace.scatter`` nodes, ``nth-child(2)`` resolves to the *third*
        band and ``nth-child(3)`` to nothing. That is #316's misalignment, and
        this is the helper written to end it.

        Returns
        -------
        list of str
            One CSS selector per drawn band, in trace order.
        """
        _, drawn_positions = self._drawn_line_series(
            self._traces, self._scatter_positions
        )
        return self._scatter_line_selectors(self._traces, drawn_positions)

    def _extract_plot_data(self) -> list[list[dict]]:
        """Return one series of ``{x, y}`` per drawn band, ``z`` its name.

        Shares the single pass with :meth:`_get_selector` rather than walking
        the traces again -- see ``_drawn_line_series`` for why the pass cannot
        simply be repeated.

        A ``groupnorm`` stack is rescaled to the shares plotly draws. The
        layer is typed ``stacked_normalized_area`` for it, and the values
        underneath were the untouched inputs -- a reader heard ``30`` on a
        chart whose axis runs 0..1 and whose band top sits at ``0.75`` (#691),
        the area half of what #409 was for ``barnorm``. The core normalises
        nothing: ``AreaTrace`` sums whatever values it is given, so a
        normalised layer has to arrive already carrying shares. Gated on the
        type rather than on the setting alone so a plain or stacked area is
        emitted exactly as before.
        """
        bands, _ = self._drawn_line_series(self._traces, self._scatter_positions)
        if self.type != PlotType.NORMALIZED_AREA:
            return bands

        scale = groupnorm_scale(self._traces)
        if scale is None:
            return bands
        return normalised_bands(bands, scale)
