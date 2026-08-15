"""Plotly area charts, which arrive as scatter traces carrying a stackgroup.

`px.area` produces a `Scatter`, and the only thing separating it from a line
is `stackgroup`. The adapter had no area handling at all, so every one of them
fell through to `line` -- a reader was not told the bands are filled, that they
stack, or what the running total at each x is, which is the reason someone
draws this chart rather than a multi-line one (#392).
"""

from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list
from maidr.plotly.step_shape import is_scatter_family_trace

#: The values ``groupnorm`` takes when plotly rescales a stack to a common
#: total -- its own switch for a 100% stacked area, and the counterpart of
#: ``barnorm`` on the bar path.
_NORMALISING_GROUPNORMS = frozenset({"percent", "fraction"})


def is_area_trace(trace: dict) -> bool:
    """Whether plotly fills this trace down to a baseline.

    ``stackgroup`` is the whole signal, and it is structural rather than a
    display string: plotly stacks traces that share one and leaves traces with
    an empty one alone. Measured in Chromium -- a trace with ``stackgroup``
    set resolves to ``fill: "tonexty"`` and its calcdata carries an ``s`` key
    holding the series' own value, while a plain line resolves to
    ``fill: "none"`` and has no ``s`` at all.

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    bool
        True when the trace is drawn as a filled band.
    """
    return bool(trace.get("stackgroup")) and is_scatter_family_trace(trace)


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

    def _get_selector(self) -> list[str]:
        """One selector per band, in the order the bands are emitted.

        Reuses the scatter-family positions the subplot already assigns, since
        an area trace is a scatter trace and sits in the same ``scatterlayer``
        as the lines beside it.
        """
        return self._scatter_line_selectors(self._traces, self._scatter_positions)

    def _extract_plot_data(self) -> list[list[dict]]:
        data: list[list[dict]] = []
        for trace in self._traces:
            xs = as_list(trace.get("x"))
            ys = as_list(trace.get("y"))
            fill = str(trace.get("name", ""))
            series: list[dict] = []
            for x, y in zip(xs, ys):
                point = {
                    MaidrKey.X.value: self._to_native(x),
                    MaidrKey.Y.value: self._to_native(y),
                }
                # Omitted rather than emitted blank, matching every sibling
                # extractor -- `PlotlyPlot._line_series_with_positions` and
                # the matplotlib `AreaPlot` both guard the same way. A single
                # unnamed band is the ordinary `px.area(...)` call with no
                # `color=`, and its traces carry `name: ""`.
                if fill:
                    point[MaidrKey.Z.value] = fill
                series.append(point)
            data.append(series)
        return data
