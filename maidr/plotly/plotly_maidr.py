from __future__ import annotations

import json
import os
import tempfile
import uuid
import webbrowser
from collections import defaultdict
from typing import Any, Literal, cast

from htmltools import HTML, HTMLDocument, Tag, tags

from maidr.core.enum.maidr_key import MaidrKey
from maidr.plotly.candlestick import is_ohlc_trace, layer_position
from maidr.plotly.plotly_plot import subplot_block
from maidr.plotly.gauge import draws_a_dial
from maidr.plotly.hierarchy import has_one_root, is_hierarchy_trace
from maidr.plotly.area import is_area_trace
from maidr.plotly.contour import is_contour_trace
from maidr.plotly.splom import is_splom_trace, splom_panels
from maidr.plotly.histogram2d import is_histogram2d_trace
from maidr.plotly.histogram2dcontour import is_histogram2dcontour_trace
from maidr.plotly.grouped_histogram import is_histogram_trace
from maidr.plotly.trendline import is_trendline_trace
from maidr.plotly.plotly_plot import (
    PlotlyPlot,
    domain_interval,
    draws_marks,
    is_drawn,
    subplot_css_prefix,
)
from maidr.plotly.violin import (
    PlotlyViolinBoxPlot,
    PlotlyViolinKdePlot,
    collect_violins,
    is_violin_trace,
)
from maidr.plotly.plotly_plot_factory import PlotlyPlotFactory
from maidr.plotly.step_shape import (
    is_connected_line_trace,
    is_scatter_family_trace,
    is_step_trace,
    renders_through_webgl,
)
from maidr.util.bundle_capability import (
    schema_trace_types,
    warn_if_bundle_cannot_render,
)
from maidr.util.bundle_freshness import warn_if_bundle_is_stale
from maidr.util.dependencies import (
    MAIDR_JS_FILENAME,
    OFFLINE_FALLBACK_REPORT,
    inline_bundle_tags,
    maidr_bundled_files_dependency,
    maidr_bundled_relative_dir,
    maidr_html_dependency,
)
from maidr.util.cdn import (
    bundled_cdn_url,
    maidr_js_cdn_url,
)
from maidr.util.environment import Environment
from maidr.util.iframe_utils import chart_title_of, wrap_in_iframe_plotly


#: The layout keys that hold a subplot *block* -- a rectangle plotly writes
#: for a subplot that has no cartesian axis pair, and that a trace addresses
#: by name. ``polar``/``polar2`` for the two polar traces, ``geo``/``geo2``
#: for a choropleth. Collected into the figure's row and column universe
#: exactly as ``xaxis``/``yaxis`` domains are.
_SUBPLOT_BLOCK_PREFIXES = ("polar", "geo")


#: Trace types placed by their own ``domain`` rectangle that maidr renders as
#: a layer. Plotly has other domain traces -- ``table``, ``sunburst``,
#: ``treemap``, ``indicator`` -- and maidr draws no layer for any of them, so
#: their rectangles are deliberately not folded into the figure's row and
#: column universe by :meth:`PlotlyMaidr._subplot_domain_starts`. Folding them
#: in would move the cartesian subplots sitting beside them: a bar to the right
#: of a ``go.Table`` in a 1x2 grid would go from column 0, the only column
#: maidr has anything to put in, to column 1 behind an empty cell.
#:
#: Add a type here when maidr learns to render it, not before.
_PLACED_BY_DOMAIN = frozenset(
    {
        "pie",
        "funnelarea",
        "indicator",
        "treemap",
        "sunburst",
        "icicle",
        "sankey",
        "parcoords",
        "parcats",
        "choropleth",
    }
)


def _occupies_a_cell(trace: dict) -> bool:
    """Report whether this trace's ``domain`` rectangle belongs in the grid.

    Membership in :data:`_PLACED_BY_DOMAIN` is the type-level half of the
    question. The other half is whether maidr renders the trace at all: the
    grid describes what maidr can describe, so a trace it draws no layer for
    occupies no cell -- reserving one would both add an empty cell to tab
    through and shift every renderable subplot beside it into a different
    column.

    Only ``indicator`` splits on that. A pie and a funnelarea are always
    read; an indicator is read only when it draws a dial, so a
    ``mode="number"`` one is a domain trace that renders nothing, exactly
    like a ``go.Table``.

    Parameters
    ----------
    trace : dict
        One trace of the figure.

    Returns
    -------
    bool
        True when the trace's rectangle should join the column universe.
    """
    kind = trace.get("type")
    if kind not in _PLACED_BY_DOMAIN:
        return False
    if kind == "indicator":
        return draws_a_dial(trace)
    if is_hierarchy_trace(trace):
        return has_one_root(trace)
    return True

#: Every trace type plotly places by a ``domain`` rectangle rather than by a
#: cartesian axis pair. These share the default ``("x", "y")`` trace group with
#: each other simply because none of them names an axis -- not because any of
#: them has a claim on ``layout.xaxis``/``yaxis``. Used to decide whether a pie
#: may take those titles for its own dimension names; see ``_extract_plots``.
_DOMAIN_TRACE_TYPES = frozenset(
    {
        "pie",
        "funnelarea",
        "sunburst",
        "treemap",
        "icicle",
        "indicator",
        "table",
        "sankey",
        "parcats",
        "parcoords",
    }
)


def _carries_data(plot: Any) -> bool:
    """Report whether a built plot has anything for a reader to navigate.

    A trace that draws nothing forms no layer. #421 established that for the
    line and area families, by excluding an undrawn trace from their groupings
    with ``draws_marks()`` -- which does more than this, because it also keeps
    the *positions* of the surviving series contiguous, something a later
    filter cannot recover. Every other family appended unconditionally, so an
    empty pie, sankey, hierarchy, polar or parcoords became a layer with an
    empty payload (#636).

    That is not a harmless no-op. It is a cell the reader can tab into and
    find nothing in, and for the line-family types it is worse: `LineTrace`
    dereferences an undefined point on an empty series and throws, which
    propagates out of `Figure` and takes the whole render down
    (xability/maidr#905). `ParallelTrace` and `RadarTrace` are both built on
    it.

    Asked of the *rendered* payload rather than of the trace, so one question
    covers all three shapes maidr emits: a list of points, a list of series,
    and a mapping. `plot.schema` is memoised, so this costs no extra work.

    A mapping needs the extra step, because two of them look alike at the top
    level and mean opposite things. A gauge's is
    ``{"value": 0, "min": -1, "max": 1}`` -- a full reading whose first field
    happens to be falsy -- and an empty heatmap's is ``{"points": []}``, a
    field with nothing in it. So a mapping carries data when any of its values
    is a scalar or a non-empty collection.

    One level, deliberately. ``{"points": [[]]}`` -- a heatmap of one empty
    row -- is kept, because recursing to decide that a nested structure is
    "really" empty is guessing at a shape rather than reading it, and dropping
    a layer that should have shipped is the more damaging of the two mistakes.

    Parameters
    ----------
    plot : PlotlyPlot
        A built plot.

    Returns
    -------
    bool
        True when the payload holds something for a reader to navigate. A
        payload that is neither a list nor a mapping is kept, for the same
        reason: an unfamiliar shape is not evidence of emptiness.
    """
    data = plot.schema.get(MaidrKey.DATA)
    if isinstance(data, (list, tuple)):
        return bool(data)
    if isinstance(data, dict):
        return any(_holds_something(value) for value in data.values())
    return data is not None


def _holds_something(value: Any) -> bool:
    """Report whether one field of a mapping payload has anything in it."""
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return value is not None


def _is_domain_trace(trace: dict) -> bool:
    """Report whether plotly places this trace by a domain rather than an axis.

    Parameters
    ----------
    trace : dict
        One trace of the figure.

    Returns
    -------
    bool
        True when the trace carries no cartesian axis pair. A trace with no
        ``type`` at all is a ``scatter``, which is cartesian.
    """
    return trace.get("type") in _DOMAIN_TRACE_TYPES


#: Plotly's own default when a figure sets no ``barmode``. It stacks -- and
#: it is the value `px.bar(color=...)` leaves behind, so it is the ordinary
#: way a stacked bar chart arrives rather than an exotic one.
_PLOTLY_DEFAULT_BARMODE = "relative"

#: The barmodes under which plotly *combines* several bar traces into one
#: chart, and so the ones MAIDR merges into a single layer. ``relative`` is
#: plotly's name for a stack that lets negative values run below the axis.
#:
#: ``overlay`` is deliberately absent: those bars are drawn over one another
#: rather than joined, so separate layers is the honest reading.
_COMBINED_BARMODES = frozenset({"group", "stack", "relative"})


class PlotlyMaidr:
    """
    Handles rendering Plotly figures as accessible MAIDR HTML.

    Preserves the full Plotly interactive experience (hover, zoom, pan,
    click events) while layering MAIDR accessibility features (sonification,
    braille, data table) on top via the MAIDR JS library.

    Parameters
    ----------
    fig : plotly.graph_objects.Figure
        The Plotly figure to make accessible.
    """

    def __init__(self, fig: Any) -> None:
        self._fig = fig
        self._plots: list[PlotlyPlot] = []
        self.maidr_id = str(uuid.uuid4())
        self._extract_plots()

    @staticmethod
    def _trace_axis_ref(trace: dict) -> tuple[str, str]:
        """Return layout axis keys for a trace.

        Plotly traces reference their subplot axes via ``xaxis`` and
        ``yaxis`` fields containing values like ``"x"``, ``"x2"``,
        ``"y3"``, etc.  This converts them to layout keys such as
        ``"xaxis"``, ``"xaxis2"``, ``"yaxis3"``.
        """
        xref = trace.get("xaxis", "x")
        yref = trace.get("yaxis", "y")

        # "x" -> "xaxis", "x2" -> "xaxis2"
        x_key = "xaxis" + xref[1:] if xref else "xaxis"
        y_key = "yaxis" + yref[1:] if yref else "yaxis"

        return x_key, y_key

    @staticmethod
    def _subplot_domain_starts(
        layout: dict, traces: list[dict]
    ) -> tuple[list[float], list[float]]:
        """Collect the fractional start of every subplot in the figure.

        Plotly's ``make_subplots`` places a *cartesian* subplot by giving each
        of its axes a ``domain``, and a *domain* trace -- ``go.Pie`` has no
        axes at all -- by giving the trace itself a ``domain`` rectangle.
        Both are fractions of the same figure, so the two are collected
        together: a figure mixing a pie with a cartesian subplot has to order
        their columns against each other, not each against its own kind.

        Only the domain traces maidr renders are collected -- see
        :data:`_PLACED_BY_DOMAIN`. The grid this builds is the grid the user
        navigates, and a trace maidr draws no layer for occupies no cell in
        it: reserving one would both add an empty cell to tab through and
        shift every renderable subplot beside it into a different column.

        Parameters
        ----------
        layout : dict
            The Plotly figure layout.
        traces : list of dict
            Every trace in the figure.

        Returns
        -------
        tuple of (list of float, list of float)
            The unique x starts left to right, giving column indices, and the
            unique y starts top to bottom, giving row indices -- a higher y
            start sits higher on the page, so it is the lower row index.
        """
        x_starts: set[float] = set()
        y_starts: set[float] = set()

        for key, val in layout.items():
            if key.startswith("xaxis") and isinstance(val, dict):
                x_starts.add(_domain_start(val, "domain"))
            if key.startswith("yaxis") and isinstance(val, dict):
                y_starts.add(_domain_start(val, "domain"))

            # A polar or geo subplot is placed like a cartesian one -- by a
            # rectangle `make_subplots` wrote into the layout -- but under
            # its own key rather than an axis pair, so it needs its own
            # branch. Without it a `[bar, polar]` grid collected one x start
            # and collapsed to a single cell holding both layers, and two
            # polar subplots side by side collected none at all. A geo
            # subplot is the same shape: `layout.geo.domain`, named by the
            # trace's `geo` rather than by an axis pair.
            if key.startswith(_SUBPLOT_BLOCK_PREFIXES) and isinstance(val, dict):
                domain = val.get("domain")
                if isinstance(domain, dict):
                    x_starts.add(_domain_start(domain, "x"))
                    y_starts.add(_domain_start(domain, "y"))

        for trace in traces:
            if not _occupies_a_cell(trace):
                continue
            domain = trace.get("domain")
            if isinstance(domain, dict):
                x_starts.add(_domain_start(domain, "x"))
                y_starts.add(_domain_start(domain, "y"))

        return sorted(x_starts), sorted(y_starts, reverse=True)

    @staticmethod
    def _grid_position(
        x_starts: list[float],
        y_starts: list[float],
        start: tuple[float, float],
    ) -> tuple[int, int]:
        """Return the grid cell one subplot's domain start pair addresses.

        Parameters
        ----------
        x_starts, y_starts : list of float
            The figure's subplot starts, as :meth:`_subplot_domain_starts`
            ordered them.
        start : tuple of (float, float)
            This subplot's own x and y domain start.

        Returns
        -------
        tuple of (int, int)
            The ``(row, col)`` of the cell, falling back to the first row or
            column for a start the figure does not place.
        """
        x_start, y_start = start

        col = x_starts.index(x_start) if x_start in x_starts else 0
        row = y_starts.index(y_start) if y_start in y_starts else 0

        return row, col

    @staticmethod
    def _axis_domain_start(
        layout: dict, xaxis_name: str, yaxis_name: str
    ) -> tuple[float, float]:
        """Return where a cartesian subplot's axis pair starts in the figure."""
        return (
            _domain_start(layout.get(xaxis_name, {}), "domain"),
            _domain_start(layout.get(yaxis_name, {}), "domain"),
        )

    @staticmethod
    def _trace_domain_start(trace: dict) -> tuple[float, float]:
        """Return where a domain trace's own rectangle starts in the figure.

        A domain trace carries no ``xaxis``/``yaxis``, so this -- not the axis
        names its group was keyed by, which are the defaults for every one of
        them -- is what tells two pies of a grid apart. A trace plotly never
        placed covers the whole figure, which is the first cell.
        """
        domain = trace.get("domain")
        return _domain_start(domain, "x"), _domain_start(domain, "y")

    @staticmethod
    def _block_domain_start(layout: dict, name: str) -> tuple[float, float]:
        """Return where a named subplot *block* starts in the figure.

        A polar or geo trace carries neither an axis pair nor a ``domain`` of
        its own, so neither of the two helpers above can place it. Its
        rectangle is written into the layout under the subplot it names --
        ``layout.polar``, ``layout.polar2``, ``layout.geo``, ... -- which is
        what tells two of them in one grid apart.

        Parameters
        ----------
        layout : dict
            The Plotly figure layout.
        name : str
            The layout key naming the subplot, as the trace spells it.

        Returns
        -------
        tuple of (float, float)
            The x and y start of that subplot. One plotly never placed covers
            the whole figure, which is the first cell.
        """
        block = layout.get(name)
        domain = block.get("domain") if isinstance(block, dict) else None
        return _domain_start(domain, "x"), _domain_start(domain, "y")

    def _extract_plots(self) -> None:
        """Extract PlotlyPlot instances from all traces in the figure.

        Groups traces by their subplot position (axis pair), then applies
        merging rules within each group:

        * Multiple bar traces that plotly combines -- ``barmode`` of
          ``'group'``, ``'stack'`` or ``'relative'`` -- are merged into a
          single :class:`PlotlyGroupedBarPlot`. ``'overlay'`` is not combined:
          those bars are drawn over one another rather than joined, so they
          stay separate layers.
        * Scatter/lines traces are split by *renderer* first — SVG traces
          apart from canvas-painted ``scattergl`` ones — because a layer's
          selector list is all-or-nothing, so a mixed layer could only claim a
          highlight for every series or for none. The groups are built in
          first-seen order, so the emitted layers still follow plotly's own
          trace order. Grouping is coarse rather than interleaved: traces
          alternating ``svg, gl, svg`` emit ``[svg, svg]`` then ``[gl]``,
          because both SVG traces belong to one merged layer. That is
          inherent to merging at all, and matches how
          :func:`~maidr.plotly.step_shape.group_by_direction` already behaves
          for alternating step conventions.
        * Within a renderer they are split into staircases and plain lines by
          ``line.shape``: a step merged into the line layer would be
          announced as interpolating between samples, which is the one thing
          piecewise-constant data does not do. The plain lines then merge into
          a single :class:`PlotlyMultiLinePlot` (matching ``MultiLinePlot``),
          or become one :class:`PlotlyLinePlot` when there is only one.
        * The staircases are split again by step convention, one
          :class:`PlotlyStepPlot` per convention, because a MAIDR layer
          carries a single ``stepDirection`` for all of its series.
        * Multiple box traces are merged into a single
          :class:`PlotlyMultiBoxPlot` (matching ``BoxPlot``).
        * Pie traces stay one layer each, but are built here rather than by
          the factory so every pie carries its position among the figure's
          pie traces — the only thing its selector can be scoped by.
        * Waterfall traces stay one layer each for the same reason, scoped by
          their position among the subplot's waterfall traces.

        Every scatter-family trace is assigned a selector index from its
        position within the subplot, not within the layer it lands in — see
        :meth:`PlotlyPlot._scatter_line_selector`. Because of that, all
        scatter/lines traces are built here rather than left to
        :class:`PlotlyPlotFactory`, which cannot know those positions.
        """
        fig_dict = self._fig.to_dict()
        layout = fig_dict.get("layout", {})
        # Dropped once, here, rather than in each branch below. Plotly renders
        # no group at all for a hidden trace, so one that is `visible=False`
        # or `"legendonly"` is not on the chart: reading it announces marks
        # nobody can see, and letting it occupy a position pushes its
        # neighbours' selectors onto groups that do not exist. Filtering at
        # the source means every downstream reader -- bar merging, line
        # grouping, pie and candlestick positions, the subplot grid -- sees
        # only what was drawn, and none of them has to remember to ask.
        traces = [trace for trace in fig_dict.get("data", []) if is_drawn(trace)]
        # Plotly's own default is `relative`, which stacks. Defaulting to
        # `group` here meant a figure that plotly drew stacked was announced
        # as *dodged* -- not a lost relationship but an inverted one, telling
        # a reader the bars sit side by side when they sit on top of each
        # other, so every segment means something other than what is said and
        # the totals a stack is read for are absent (#390).
        # `or` rather than `get(key, default)`: the key is absent when unset
        # today, but a future plotly could export it as an explicit `None`, and
        # every barmode plotly accepts is a non-empty string, so nothing valid
        # is falsy here.
        barmode = layout.get("barmode") or _PLOTLY_DEFAULT_BARMODE

        # Group traces by their subplot axis pair
        axis_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for trace in traces:
            axis_pair = self._trace_axis_ref(trace)
            axis_groups[axis_pair].append(trace)

        x_starts, y_starts = self._subplot_domain_starts(layout, traces)

        # Process each subplot group independently
        for (xaxis_name, yaxis_name), group_traces in axis_groups.items():
            axis_kwargs = {
                "xaxis_name": xaxis_name,
                "yaxis_name": yaxis_name,
            }
            row, col = self._grid_position(
                x_starts,
                y_starts,
                self._axis_domain_start(layout, xaxis_name, yaxis_name),
            )

            bar_traces = [
                t for t in group_traces if t.get("type") == "bar"
            ]
            # An area trace is a scatter trace that plotly fills, so it is a
            # "connected line" by every structural test -- and left in the
            # line grouping it would be emitted twice, once as its own layer
            # and once inside the multi-line one. Split out here, before any
            # of the line/step machinery sees the group.
            # A trace that draws nothing forms no layer. Plotly gives it no
            # group, so there is nothing to announce and nothing to highlight,
            # and the core does worse than ignore such a layer: a series with
            # no points makes `LineTrace.text` dereference an undefined point
            # and throw, which propagates out of `Figure` and takes the whole
            # render with it (#421, and xability/maidr#905 for the core half).
            #
            # The multi-trace paths already reach this answer inside
            # `_drawn_line_series`, which drops an undrawn series and its
            # position together. Excluding them here means a lone one reaches
            # it too, rather than bypassing it through the single-trace
            # branches below.
            area_traces = [
                t for t in group_traces if is_area_trace(t) and draws_marks(t)
            ]
            connected_traces = [
                t
                for t in group_traces
                if is_connected_line_trace(t)
                and not is_area_trace(t)
                and draws_marks(t)
            ]
            box_traces = [
                t for t in group_traces if t.get("type") == "box"
            ]
            pie_traces = [
                t for t in group_traces if t.get("type") == "pie"
            ]
            funnelarea_traces = [
                t for t in group_traces if t.get("type") == "funnelarea"
            ]
            # Only the indicators that draw a dial. One that draws none is
            # not a chart to navigate, and letting it take a position here
            # would push its dial-drawing neighbours onto trace groups that
            # do not exist -- the same reason `is_drawn` filters hidden
            # traces at the source.
            # Every indicator, because every one of them takes a `.trace`
            # group in the layer -- see `PlotlyGaugePlot._get_selector`. The
            # ones that draw no dial are skipped when the layers are built,
            # not when the positions are counted.
            indicator_traces = [
                t for t in group_traces if t.get("type") == "indicator"
            ]

            # `nth-child` counts within the subplot's SVG `scatterlayer`, so a
            # scatter trace's selector index is its position *there* — not its
            # position within the MAIDR layer it lands in. The two agree only
            # while one layer owns every scatter trace on the subplot, which
            # splitting steps out ends.
            #
            # A `scattergl` trace is painted into a shared `<canvas>` and never
            # appears in the `scatterlayer` at all. Verified in a browser
            # rather than assumed: with a gl trace declared before an svg one,
            # the `scatterlayer` holds exactly one child and it is the svg
            # trace, at `nth-child(1)`; `nth-child(2)` matches nothing.
            # Counting gl traces here therefore pushed every svg sibling one
            # position along, onto a selector that matched nothing — so a
            # single gl trace silently broke its neighbours' highlighting too.
            scatter_family = [
                t for t in group_traces if is_scatter_family_trace(t)
            ]
            svg_scatter = [
                t for t in scatter_family if not renders_through_webgl(t)
            ]
            gl_scatter = [t for t in scatter_family if renders_through_webgl(t)]

            # Each trace's index *within its own renderer*. For an SVG trace
            # that is its position in the `scatterlayer`, which is what
            # `nth-child` counts. A `scattergl` trace never enters that layer
            # at all -- verified in a browser: with a gl trace declared before
            # an svg one, the `scatterlayer` holds exactly one child and it is
            # the svg trace, at `nth-child(1)`, while `nth-child(2)` matches
            # nothing. Numbering the two renderers together therefore pushed
            # every svg trace one place along, onto a selector that matched
            # nothing, so one gl trace silently broke its neighbours'
            # highlighting as well as its own.
            #
            # The gl indices are never rendered -- a WebGL layer emits no
            # selectors (see `PlotlyPlot._scatter_line_selectors`) -- but they
            # still have to be well-formed, because the layer classes validate
            # the list they are handed. Numbering gl traces from their own
            # zero keeps them unique and correct-by-construction rather than
            # padding with a placeholder, which collided the moment two gl
            # traces shared a subplot.
            # Numbered by what plotly *draws*, not by what was declared.
            # A trace with nothing to plot gets no group in the layer at all
            # -- measured in Chromium, three traces with an empty one in the
            # middle produce two `.trace.scatter` nodes -- so every trace
            # after it shifts up one. Numbering by declaration therefore
            # handed the third trace `nth-child(3)`, which matches nothing,
            # while `nth-child(2)` reached it instead (#412).
            #
            # An undrawn trace is numbered after the drawn ones rather than
            # skipped. Its index is never rendered, because
            # `_line_series_with_positions` drops the series and its position
            # together, but the layer classes validate the list they are
            # handed and a duplicate or a gap would fail that check. Counting
            # them from the end keeps every index unique and
            # correct-by-construction, which is what the gl numbering above
            # does for the same reason.
            position_of: dict[int, int] = {}
            for renderer in (svg_scatter, gl_scatter):
                drawn = [t for t in renderer if draws_marks(t)]
                undrawn = [t for t in renderer if not draws_marks(t)]
                for index, t in enumerate(drawn):
                    position_of[id(t)] = index
                for offset, t in enumerate(undrawn):
                    position_of[id(t)] = len(drawn) + offset

            # Undrawn scatter-family traces are marked handled up front, so
            # the fallback loop at the end does not build a layer for one that
            # the groupings above deliberately skipped. Scoped to the scatter
            # family because `draws_marks` reads `x`/`y`: a pie carries neither
            # and draws perfectly well, so asking it globally would drop every
            # pie in the figure.
            merged: set[int] = {
                id(t) for t in scatter_family if not draws_marks(t)
            }

            # `barnorm` only means anything for a stack: plotly scales each
            # category's segments to a common total, so the values are shares
            # rather than counts. Read as a plain `stacked_bar` a reader is
            # told nothing about that, and is left to suppose the equal totals
            # are a property of the data rather than of the chart (#338).
            def _combined_type() -> Any:
                from maidr.core.enum.plot_type import PlotType
                from maidr.plotly.barnorm import barnorm_scale

                if barmode == "group":
                    return PlotType.DODGED
                # Asked of the same function that does the rescaling, rather
                # than of a second copy of the value list. Two copies is how
                # #409 comes back: a `barnorm` one of them recognised and the
                # other did not would type the layer
                # `stacked_normalized_bar` while leaving its values the raw
                # counts -- the type and the numbers contradicting each other
                # again, and silently, which is the defect this pair of
                # readings was reconciled to end.
                if barnorm_scale(layout.get("barnorm")) is not None:
                    return PlotType.NORMALIZED
                return PlotType.STACKED

            # Filled bands, one layer per stack group. `px.area` produces a
            # `Scatter` whose only mark of being an area is `stackgroup`, and
            # with that unread every one of them fell through to `line` --
            # so a reader was told neither that the bands are filled nor that
            # they stack, which is the reason the chart is drawn at all
            # (#392).
            if area_traces:
                from maidr.plotly.area import (
                    PlotlyAreaPlot,
                    area_plot_type,
                    area_stack_groups,
                )

                for stack in area_stack_groups(area_traces):
                    plot = PlotlyAreaPlot(
                        stack,
                        layout,
                        area_plot_type(stack),
                        scatter_positions=[position_of[id(t)] for t in stack],
                        **axis_kwargs,
                    )
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)
                merged.update(id(t) for t in area_traces)

            # Grouped / stacked bars
            if len(bar_traces) > 1 and barmode in _COMBINED_BARMODES:
                from maidr.plotly.grouped_bar import PlotlyGroupedBarPlot

                plot = PlotlyGroupedBarPlot(
                    bar_traces, layout, _combined_type(), **axis_kwargs
                )
                plot.row_index = row
                plot.col_index = col
                self._plots.append(plot)
                merged.update(id(t) for t in bar_traces)

            # Grouped / stacked histograms. Plotly combines these exactly as
            # it combines bars, and bins them jointly -- one grid computed
            # from every trace's values together. Left as one layer each they
            # were announced as independent distributions binned on grids of
            # their own, so a reader was told neither that the bars stack nor
            # what the bins are (#394).
            histogram_traces = [t for t in group_traces if is_histogram_trace(t)]
            if len(histogram_traces) > 1 and barmode in _COMBINED_BARMODES:
                from maidr.plotly.grouped_histogram import (
                    PlotlyGroupedHistogramPlot,
                )

                plot = PlotlyGroupedHistogramPlot(
                    histogram_traces, layout, _combined_type(), **axis_kwargs
                )
                # A categorical group declines rather than half-describing
                # itself, and is left to the factory one trace at a time.
                if plot._extract_plot_data():
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)
                    merged.update(id(t) for t in histogram_traces)

            # Lines and steps are grouped within one renderer, never across
            # two. A layer's selector list is positional and all-or-nothing
            # (see `PlotlyPlot._scatter_line_selectors`), so a layer holding
            # both a canvas trace and an SVG one could only describe every
            # series or none of them. Merging them meant a single `scattergl`
            # line took the highlight away from every ordinary line beside it.
            # Splitting first keeps each layer homogeneous: the SVG traces
            # keep working selectors, and the WebGL ones honestly claim none.
            #
            # Grouped in first-seen order rather than SVG-then-WebGL, so the
            # emitted layers still follow the order plotly declared the traces
            # in — the same property `group_by_direction` preserves. A fixed
            # order would reorder the layers of any figure that declares a gl
            # trace before its svg ones, pulling MAIDR's navigation order out
            # of step with plotly's own trace and legend order.
            renderer_groups: dict[bool, list[dict]] = {}
            for trace in connected_traces:
                renderer_groups.setdefault(
                    renders_through_webgl(trace), []
                ).append(trace)

            for renderer_traces in renderer_groups.values():
                # A staircase is a scatter/lines trace whose ``line.shape``
                # makes plotly draw risers instead of interpolating, so it has
                # to be split out here: merged into the multi-line layer it
                # would be announced as an interpolated line.
                step_traces = [
                    t for t in renderer_traces if is_step_trace(t)
                ]
                # A `plotly.express` trendline is a fitted curve, not drawn
                # data, and nothing structural says so -- same `type`, same
                # `mode`, no `name`, the scatter's own colour. Merged into the
                # multi-line layer it was announced as one more series of the
                # user's data, so a reader was told a model's prediction was a
                # measurement (#343).
                #
                # Split before the line branches rather than typed afterwards,
                # because a layer carries one type for every series it holds:
                # a trendline sharing a layer with the lines beside it could
                # only be `line` or make them all `smooth`.
                unstepped = [t for t in renderer_traces if not is_step_trace(t)]
                trendline_traces = [t for t in unstepped if is_trendline_trace(t)]
                line_traces = [
                    t for t in unstepped if not is_trendline_trace(t)
                ]

                # Multi-line
                if len(line_traces) > 1:
                    from maidr.plotly.multiline import PlotlyMultiLinePlot

                    plot = PlotlyMultiLinePlot(
                        line_traces,
                        layout,
                        scatter_positions=[
                            position_of[id(t)] for t in line_traces
                        ],
                        **axis_kwargs,
                    )
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)
                    merged.update(id(t) for t in line_traces)

                # A lone line is built here rather than left to the factory
                # below, so it too gets a position-scoped selector. The factory
                # cannot know the trace's position among its subplot's scatter
                # traces, and its unscoped selector would also match a step
                # trace's path.
                elif len(line_traces) == 1:
                    from maidr.plotly.line import PlotlyLinePlot

                    only_line = line_traces[0]
                    plot = PlotlyLinePlot(
                        only_line,
                        layout,
                        scatter_position=position_of[id(only_line)],
                        **axis_kwargs,
                    )
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)
                    merged.add(id(only_line))

                # Fitted trends, as their own layer. One layer for all of them
                # rather than one each: `px.scatter(..., color=...,
                # trendline="ols")` fits per colour group, and those are the
                # same kind of thing navigated together, exactly as the
                # multi-line layer holds the series they were fitted to.
                #
                # Built through `PlotlyMultiLinePlot` at any count, including
                # one, so a lone trendline gets a position-scoped selector.
                # The lone-line branch below uses `PlotlyLinePlot` instead,
                # whose unscoped form would also match the scatter's own
                # elements.
                if trendline_traces:
                    from maidr.core.enum.plot_type import PlotType
                    from maidr.plotly.multiline import PlotlyMultiLinePlot

                    plot = PlotlyMultiLinePlot(
                        trendline_traces,
                        layout,
                        scatter_positions=[
                            position_of[id(t)] for t in trendline_traces
                        ],
                        plot_type=PlotType.SMOOTH,
                        **axis_kwargs,
                    )
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)
                    merged.update(id(t) for t in trendline_traces)

                # Steps, one layer per step convention. A MAIDR layer carries a
                # single ``stepDirection`` for all of its series, so merging an
                # ``hv`` trace with a ``vh`` one would describe one of them
                # wrongly. Single-trace groups go through here too rather than
                # falling to the factory below, so their selector is scoped by
                # position among the subplot's scatter traces.
                if step_traces:
                    from maidr.plotly.step import PlotlyStepPlot
                    from maidr.plotly.step_shape import group_by_direction

                    for direction_group in group_by_direction(step_traces):
                        plot = PlotlyStepPlot(
                            direction_group,
                            layout,
                            scatter_positions=[
                                position_of[id(t)]
                                for t in direction_group
                            ],
                            **axis_kwargs,
                        )
                        plot.row_index = row
                        plot.col_index = col
                        self._plots.append(plot)
                    merged.update(id(t) for t in step_traces)

            # Multi-box
            if len(box_traces) > 1:
                from maidr.plotly.multibox import PlotlyMultiBoxPlot

                plot = PlotlyMultiBoxPlot(
                    box_traces,
                    layout,
                    layer_positions=[
                        layer_position(group_traces, t) for t in box_traces
                    ],
                    **axis_kwargs,
                )
                plot.row_index = row
                plot.col_index = col
                self._plots.append(plot)
                merged.update(id(t) for t in box_traces)

            # A lone box is built here rather than left to the factory for
            # one reason: the factory sees a single trace and cannot know
            # what shares its `boxlayer`. A `go.Candlestick` declared first
            # draws its own `path.box` group there, so the box's group is
            # not necessarily the first (#395).
            elif len(box_traces) == 1:
                from maidr.plotly.box import PlotlyBoxPlot

                plot = PlotlyBoxPlot(
                    box_traces[0],
                    layout,
                    layer_position=layer_position(group_traces, box_traces[0]),
                    **axis_kwargs,
                )
                plot.row_index = row
                plot.col_index = col
                self._plots.append(plot)
                merged.update(id(t) for t in box_traces)

            # A scatterplot matrix. One trace, `n` dimensions, and an
            # `n` by `n` grid of scatters -- which is what MAIDR's subplot
            # grid is, so each panel becomes an ordinary scatter layer at
            # its own position. Built here rather than in the factory
            # because the factory returns one plot per trace and this one
            # expands into many, each needing a grid position the factory
            # cannot know (#666).
            splom_traces = [t for t in group_traces if is_splom_trace(t)]
            for splom in splom_traces:
                for panel_row, panel_col, plot in splom_panels(splom):
                    plot.row_index = row + panel_row
                    plot.col_index = col + panel_col
                    self._plots.append(plot)
            merged.update(id(t) for t in splom_traces)

            # Pies, one layer each. Plotly draws them into a figure-level
            # ``pielayer`` instead of a subplot group, so a pie's selector is
            # scoped by its position among the *pie* traces rather than by an
            # axis pair -- which a pie does not carry at all, and which is why
            # every pie in a figure lands in this one group. Only this loop
            # knows those positions, so pies are built here rather than left
            # to ``PlotlyPlotFactory``, which sees one trace and has to assume
            # it is the only one.
            #
            # That one group is a fact about the selector, not about the grid:
            # a pie is placed by its own ``domain`` rectangle, so its cell is
            # read from there. Taking the group's cell instead collapsed every
            # pie of a grid into the first one, stacked as layers of a single
            # subplot.
            if pie_traces:
                from maidr.plotly.pie import PlotlyPiePlot

                # A pie has no axes of its own, so it names its dimensions from
                # ``layout.xaxis``/``yaxis`` when nothing else has claimed them.
                # A cartesian trace with no explicit axis pair shares this same
                # default group, and those titles describe *its* axes -- letting
                # the pie borrow them would announce a bar's "Month" against a
                # pie's slice labels.
                #
                # Only a *cartesian* trace claims them. The other domain traces
                # land in this group for the same reason a pie does -- they
                # carry no axis pair either -- so a pie beside a `go.Sunburst`
                # still owns the titles, and falling back to the generic pair
                # there would lose a label the author did write.
                pie_owns_axes = all(
                    _is_domain_trace(trace) for trace in group_traces
                )

                for position, pie_trace in enumerate(pie_traces):
                    plot = PlotlyPiePlot(
                        pie_trace,
                        layout,
                        pie_position=position,
                        borrows_axis_titles=pie_owns_axes,
                        **axis_kwargs,
                    )
                    plot.row_index, plot.col_index = self._grid_position(
                        x_starts,
                        y_starts,
                        self._trace_domain_start(pie_trace),
                    )
                    self._plots.append(plot)
                merged.update(id(t) for t in pie_traces)

            # Funnelareas, one layer each, for every reason the pies above
            # are: their own figure-level layer, their own ``domain``
            # rectangle for the grid cell, and a position among that layer's
            # trace groups that only this loop knows.
            #
            # Numbered among the *funnelarea* traces rather than alongside the
            # pies: the two layers are siblings under ``main-svg``, so a pie
            # does not shift a funnelarea's group index. Measured in Chromium
            # on a figure holding one of each -- each layer held exactly its
            # own trace at ``nth-child(1)``.
            if funnelarea_traces:
                from maidr.plotly.funnelarea import PlotlyFunnelareaPlot

                # Same question the pies answer, and the same answer: a
                # funnelarea draws no axes, so it may name its dimensions from
                # ``layout.xaxis``/``yaxis`` only when no cartesian trace has
                # claimed them.
                funnelarea_owns_axes = all(
                    _is_domain_trace(trace) for trace in group_traces
                )

                for position, funnelarea_trace in enumerate(funnelarea_traces):
                    plot = PlotlyFunnelareaPlot(
                        funnelarea_trace,
                        layout,
                        pie_position=position,
                        borrows_axis_titles=funnelarea_owns_axes,
                        **axis_kwargs,
                    )
                    plot.row_index, plot.col_index = self._grid_position(
                        x_starts,
                        y_starts,
                        self._trace_domain_start(funnelarea_trace),
                    )
                    self._plots.append(plot)
                merged.update(id(t) for t in funnelarea_traces)

            # Polar traces, one layer each, and every question about one is
            # asked of its own polar subplot rather than of the trace group.
            # A polar trace names no axis pair, so `group_traces` is keyed by
            # the cartesian defaults and holds *every* polar trace of the
            # figure however many subplots they are spread over -- which is
            # the same trap `_trace_domain_start` exists for on the pie side.
            #
            # A `scatterpolar` is numbered among the scatter traces of its
            # own subplot, because that is what one `.scatterlayer` holds --
            # a `barpolar` draws into that subplot's `.barlayer` and shifts
            # nothing there, and a trace in the *next* subplot is numbered
            # from one again.
            polar_traces = [
                t for t in group_traces if t.get("type") in ("scatterpolar", "barpolar")
            ]
            if polar_traces:
                # `PlotType` is imported here rather than at module level
                # because `_extract_plots` already imports it locally
                # further down, which makes the name local to the whole
                # function -- a module-level reference above that point is
                # an unbound local, not the module's.
                from maidr.core.enum.plot_type import PlotType
                from maidr.plotly.polar import PlotlyPolarPlot, subplot_name

                scatter_positions: dict[str, int] = {}
                for polar_trace in polar_traces:
                    name = subplot_name(polar_trace)
                    is_scatter = polar_trace.get("type") == "scatterpolar"
                    plot = PlotlyPolarPlot(
                        polar_trace,
                        layout,
                        PlotType.RADAR if is_scatter else PlotType.POLAR_AREA,
                        trace_position=scatter_positions.get(name, 0),
                        **axis_kwargs,
                    )
                    if is_scatter:
                        scatter_positions[name] = scatter_positions.get(name, 0) + 1
                    polar_row, polar_col = self._grid_position(
                        x_starts,
                        y_starts,
                        self._block_domain_start(layout, name),
                    )
                    plot.row_index = polar_row
                    plot.col_index = polar_col
                    self._plots.append(plot)
                merged.update(id(t) for t in polar_traces)

            # Parallel coordinates, one layer each. Placed by its own
            # `domain` rectangle like a pie, because a `parcoords` names no
            # axis pair either.
            from maidr.plotly.parcoords import is_parcoords_trace

            parcoords_traces = [t for t in group_traces if is_parcoords_trace(t)]
            if parcoords_traces:
                from maidr.plotly.parcoords import PlotlyParcoordsPlot

                for parcoords_trace in parcoords_traces:
                    plot = PlotlyParcoordsPlot(
                        parcoords_trace,
                        layout,
                        **axis_kwargs,
                    )
                    plot.row_index, plot.col_index = self._grid_position(
                        x_starts,
                        y_starts,
                        self._trace_domain_start(parcoords_trace),
                    )
                    self._plots.append(plot)
                merged.update(id(t) for t in parcoords_traces)

            # Choropleth maps, one layer each. Placed by its own `domain`
            # rectangle -- a `geo` subplot's, which plotly writes onto the
            # trace like a pie's.
            from maidr.plotly.choropleth import is_choropleth_trace

            choropleth_traces = [
                t for t in group_traces if is_choropleth_trace(t)
            ]
            if choropleth_traces:
                from maidr.plotly.choropleth import PlotlyChoroplethPlot

                for choropleth_trace in choropleth_traces:
                    plot = PlotlyChoroplethPlot(
                        choropleth_trace, layout, **axis_kwargs
                    )
                    plot.row_index, plot.col_index = self._grid_position(
                        x_starts,
                        y_starts,
                        self._block_domain_start(
                            layout, subplot_block(choropleth_trace, "geo")
                        ),
                    )
                    self._plots.append(plot)
                merged.update(id(t) for t in choropleth_traces)

            # Parallel sets, one layer each. Placed by its own `domain`
            # rectangle like a pie, because a `parcats` names no axis pair.
            from maidr.plotly.parcats import is_parcats_trace

            parcats_traces = [t for t in group_traces if is_parcats_trace(t)]
            if parcats_traces:
                from maidr.plotly.parcats import PlotlyParcatsPlot

                for parcats_trace in parcats_traces:
                    plot = PlotlyParcatsPlot(parcats_trace, layout, **axis_kwargs)
                    plot.row_index, plot.col_index = self._grid_position(
                        x_starts,
                        y_starts,
                        self._trace_domain_start(parcats_trace),
                    )
                    self._plots.append(plot)
                merged.update(id(t) for t in parcats_traces)

            # Sankeys, one layer each. Only this loop knows whether the
            # figure holds a second one, which is what decides whether
            # either can be addressed -- see `PlotlySankeyPlot._get_selector`.
            sankey_traces = [t for t in group_traces if t.get("type") == "sankey"]
            if sankey_traces:
                from maidr.plotly.sankey import PlotlySankeyPlot

                for sankey_trace in sankey_traces:
                    plot = PlotlySankeyPlot(
                        sankey_trace,
                        layout,
                        addressable=len(sankey_traces) == 1,
                        **axis_kwargs,
                    )
                    plot.row_index, plot.col_index = self._grid_position(
                        x_starts,
                        y_starts,
                        self._trace_domain_start(sankey_trace),
                    )
                    self._plots.append(plot)
                merged.update(id(t) for t in sankey_traces)

            # Hierarchies, one layer each. Each painting has its own
            # figure-level layer, so a trace is numbered among its own kind
            # -- a treemap does not shift a sunburst's group index.
            for kind in ("treemap", "sunburst", "icicle"):
                same_kind = [t for t in group_traces if t.get("type") == kind]
                if not same_kind:
                    continue

                from maidr.plotly.hierarchy import PlotlyHierarchyPlot

                for position, hierarchy_trace in enumerate(same_kind):
                    if has_one_root(hierarchy_trace):
                        plot = PlotlyHierarchyPlot(
                            hierarchy_trace,
                            layout,
                            hierarchy_position=position,
                            **axis_kwargs,
                        )
                        plot.row_index, plot.col_index = self._grid_position(
                            x_starts,
                            y_starts,
                            self._trace_domain_start(hierarchy_trace),
                        )
                        self._plots.append(plot)
                merged.update(id(t) for t in same_kind)

            # Gauges, one layer each, for the reasons the pies are: their
            # own figure-level layer, their own ``domain`` rectangle for the
            # grid cell, and a position among that layer's trace groups.
            if indicator_traces:
                from maidr.plotly.gauge import PlotlyGaugePlot

                for position, indicator_trace in enumerate(indicator_traces):
                    if not draws_a_dial(indicator_trace):
                        # No dial to read, but its group still counts above.
                        continue
                    plot = PlotlyGaugePlot(
                        indicator_trace,
                        layout,
                        gauge_position=position,
                        **axis_kwargs,
                    )
                    plot.row_index, plot.col_index = self._grid_position(
                        x_starts,
                        y_starts,
                        self._trace_domain_start(indicator_trace),
                    )
                    self._plots.append(plot)
                merged.update(id(t) for t in indicator_traces)

            # OHLC series, one layer each. Built here rather than left to
            # `PlotlyPlotFactory` for the same reason a lone line is: the
            # selector needs the trace's position among its DOM layer-mates,
            # and only this loop knows what else is on the subplot.
            #
            # Layer-mates rather than traces, because plotly appends one group
            # per trace to the layer that trace's *type* draws into. A
            # `candlestick` shares `g.boxlayer` with every `go.Box` beside it
            # -- which draws a `path.box` of its own -- while an `ohlc` gets
            # `g.ohlclayer` to itself. Counting either one against all the
            # subplot's traces would scope the selector to nothing.
            ohlc_traces = [t for t in group_traces if is_ohlc_trace(t)]
            if ohlc_traces:
                from maidr.plotly.candlestick import PlotlyCandlestickPlot

                for ohlc_trace in ohlc_traces:
                    plot = PlotlyCandlestickPlot(
                        ohlc_trace,
                        layout,
                        layer_position=layer_position(group_traces, ohlc_trace),
                        **axis_kwargs,
                    )
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)
                merged.update(id(t) for t in ohlc_traces)

            # Violins, as one `violin_box` + `violin_kde` pair for the whole
            # subplot however many traces they came from -- the grouping the
            # browser-side plotly adapter uses, and the one the matplotlib
            # path produces per axes.
            #
            # Both layers are built from a single list of violins so they
            # cannot fall out of step: the box's row `i` and the KDE's curve
            # `i` have to be the same violin, and computing each layer's
            # grouping separately is how that quietly stops being true.
            violin_traces = [t for t in group_traces if is_violin_trace(t)]
            if violin_traces:
                violins = collect_violins(
                    violin_traces,
                    subplot_css_prefix(xaxis_name, yaxis_name),
                )

                if violins:
                    for layer in (
                        PlotlyViolinBoxPlot(
                            violin_traces, layout, violins, **axis_kwargs
                        ),
                        PlotlyViolinKdePlot(
                            violin_traces, layout, violins, **axis_kwargs
                        ),
                    ):
                        layer.row_index = row
                        layer.col_index = col
                        self._plots.append(layer)
                merged.update(id(t) for t in violin_traces)

            # Funnels, one layer each, for the reason the waterfalls below
            # are: plotly appends one `.trace.bars` group per funnel trace to
            # the subplot's `funnellayer`, so a trace's selector is scoped by
            # its position among those.
            funnel_traces = [t for t in group_traces if t.get("type") == "funnel"]
            if funnel_traces:
                from maidr.plotly.funnel import PlotlyFunnelPlot

                for funnel_trace in funnel_traces:
                    plot = PlotlyFunnelPlot(
                        funnel_trace,
                        layout,
                        layer_position=layer_position(group_traces, funnel_trace),
                        **axis_kwargs,
                    )
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)
                merged.update(id(t) for t in funnel_traces)

            # Waterfalls, one layer each, built here rather than left to
            # the factory for the reason the candlesticks above are: plotly
            # appends one `.trace.bars` group per waterfall trace to the
            # subplot's `waterfalllayer`, so a trace's selector is scoped by
            # its position among *those* traces -- which the factory, seeing
            # one trace at a time, cannot know.
            waterfall_traces = [
                t for t in group_traces if t.get("type") == "waterfall"
            ]
            if waterfall_traces:
                from maidr.plotly.waterfall import PlotlyWaterfallPlot

                for waterfall_trace in waterfall_traces:
                    plot = PlotlyWaterfallPlot(
                        waterfall_trace,
                        layout,
                        layer_position=layer_position(group_traces, waterfall_trace),
                        **axis_kwargs,
                    )
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)
                merged.update(id(t) for t in waterfall_traces)

            # Contours, one layer each. Built here rather than left to
            # the factory for the reason the waterfalls above are: plotly
            # appends one `g.contour` group per trace to the subplot's
            # `contourlayer`, and a `histogram2dcontour` takes one there too
            # -- so a contour's selector is scoped by its position among
            # *those* traces, which the factory, seeing one trace at a time,
            # cannot know. `layer_position` knows which types share a layer.
            contour_traces = [
                t
                for t in group_traces
                if is_contour_trace(t) or is_histogram2dcontour_trace(t)
            ]
            if contour_traces:
                from maidr.plotly.contour import PlotlyContourPlot
                from maidr.plotly.histogram2dcontour import (
                    PlotlyHistogram2dContourPlot,
                )

                for contour_trace in contour_traces:
                    # The two read alike from the grid onwards -- see
                    # `PlotlyHistogram2dContourPlot` -- and draw into the same
                    # `contourlayer`, so they are numbered together.
                    build = (
                        PlotlyHistogram2dContourPlot
                        if is_histogram2dcontour_trace(contour_trace)
                        else PlotlyContourPlot
                    )
                    plot = build(
                        contour_trace,
                        layout,
                        layer_position=layer_position(group_traces, contour_trace),
                        **axis_kwargs,
                    )
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)
                merged.update(id(t) for t in contour_traces)

            # Remaining traces
            for trace in group_traces:
                if id(trace) in merged:
                    continue
                if trace.get("type") == "heatmap" or is_histogram2d_trace(
                    trace
                ):
                    # The image-drawing traces. Plotly appends one
                    # `<g class="hm">` per trace to the subplot's
                    # `heatmaplayer`, in declaration order, counting a
                    # `go.Heatmap` and a `histogram2d` together -- so a
                    # selector naming an image is scoped by its trace's
                    # position among *both* kinds (#647). The factory sees
                    # one trace at a time and cannot know that; only this
                    # figure-wide pass does.
                    #
                    # Built inside this loop rather than hoisted above it,
                    # unlike the contours, so that neither kind's layer
                    # moves ahead of whatever was declared before it. That
                    # is what the hoist cost while the `histogram2d` block
                    # lived up there: a scatter declared first was announced
                    # second.
                    #
                    # A 2-D histogram is a heatmap whose grid it has to bin
                    # for itself; from the grid onwards the two read alike,
                    # which is why one extends the other.
                    from maidr.plotly.heatmap import PlotlyHeatmapPlot
                    from maidr.plotly.histogram2d import PlotlyHistogram2dPlot

                    build = (
                        PlotlyHistogram2dPlot
                        if is_histogram2d_trace(trace)
                        else PlotlyHeatmapPlot
                    )
                    plot = build(
                        trace,
                        layout,
                        layer_position=layer_position(group_traces, trace),
                        **axis_kwargs,
                    )
                else:
                    plot = PlotlyPlotFactory.create(
                        trace, layout, **axis_kwargs
                    )
                if plot is not None:
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)

        self._plots = [plot for plot in self._plots if _carries_data(plot)]

    def render(self, use_cdn: bool | Literal["auto"] = "auto") -> Tag:
        """Return the maidr plot inside an iframe.

        Parameters
        ----------
        use_cdn : bool or {"auto"}, default="auto"
            * ``True``: reference the public jsDelivr CDN only.
            * ``False``: reference the bundled ``maidr.js`` assets.
            * ``"auto"`` (default): attempt the CDN first and fall back
              to the bundled copy client-side if the CDN request fails.
        """
        return self._create_html_tag(use_iframe=True, use_cdn=use_cdn)

    def show(
        self,
        renderer: Literal["auto", "ipython", "browser"] = "auto",
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> object:
        """Display the accessible Plotly plot.

        Parameters
        ----------
        renderer : {"auto", "ipython", "browser"}, default="auto"
            Renderer to use.
        use_cdn : bool or {"auto"}, default="auto"
            See :meth:`render` for the three possible modes.
        """
        # Proactively stash the bundled ``maidr.js`` and KaTeX source on
        # the parent notebook ``window`` so the iframe bootstrap below
        # can inject them inline when the CDN is unavailable.  Mirrors the
        # matplotlib ``Maidr.show()`` behaviour (see ``maidr/core/maidr.py``)
        # and is required because ``Tag.get_html_string()`` drops any
        # ``HTMLDependency`` children during iframe serialisation.
        if use_cdn is not True and Environment.is_notebook():
            try:
                from maidr.api import init_notebook

                init_notebook(use_cdn=use_cdn, force=True)
            except Exception:
                # Never block show() on notebook init; the iframe
                # bootstrap will surface a helpful console warning if
                # the bundle is unreachable.
                pass

        html = self._create_html_tag(use_iframe=True, use_cdn=use_cdn)

        if renderer == "auto":
            _renderer = cast(
                Literal["ipython", "browser"], Environment.get_renderer()
            )
        else:
            _renderer = renderer

        if _renderer == "browser" and not Environment.is_notebook():
            return self._open_plot_in_browser(use_cdn=use_cdn)

        return html.show(_renderer)

    def save_html(
        self,
        file: str,
        *,
        lib_dir: str | None = "lib",
        include_version: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> str:
        """Save the accessible HTML representation to a file.

        Parameters
        ----------
        file : str
            Destination HTML file path.
        lib_dir : str | None, default="lib"
            Folder (relative to ``file``) used for static dependencies.
        include_version : bool, default=True
            Whether to stamp the dependency folder name with a version.
        use_cdn : bool or {"auto"}, default="auto"
            See :meth:`render` for the three possible modes.  When set
            to ``False`` or ``"auto"`` the bundled MAIDR JS assets are
            copied into ``lib_dir`` alongside the saved HTML.
        """
        html = self._create_html_doc(use_iframe=False, use_cdn=use_cdn)
        return html.save_html(file, libdir=lib_dir, include_version=include_version)

    def destroy(self) -> None:
        """Clean up resources."""
        del self._plots
        del self._fig

    def _figure_metadata(self) -> dict:
        """
        Extract figure-wide metadata for the top-level MAIDR schema.

        Maps Plotly's figure-level layout title onto the top-level MAIDR
        schema fields used by multi-panel figures:

        - ``layout.title.text`` -> ``title``
        - ``layout.title.subtitle.text`` -> ``subtitle`` (Plotly's native
          subtitle, the analog of ggplot2's ``labs(subtitle=...)``;
          authorable since plotly.js 2.35)

        Only authored values are emitted, so figures without figure-level
        text keep their existing schema unchanged. Whitespace-only strings
        count as unauthored, matching the maidr JS engine's trimmed
        "authored" check. Plotly has no figure-level caption concept, so
        ``caption`` is never emitted.

        Reads ``self._fig.layout.title`` directly rather than going through
        ``Figure.to_dict()``, which would re-serialize every trace's data
        arrays just to reach two layout strings. ``getattr`` guards keep
        this safe on plotly versions whose ``Title`` object predates
        ``subtitle``.

        Returns
        -------
        dict
            A sparse mapping with optional ``title`` and ``subtitle`` keys.
        """
        metadata: dict = {}

        layout_title = getattr(self._fig.layout, "title", None)

        title_text = str(getattr(layout_title, "text", None) or "").strip()
        if title_text:
            metadata[MaidrKey.TITLE] = title_text

        subtitle = getattr(layout_title, "subtitle", None)
        subtitle_text = str(getattr(subtitle, "text", None) or "").strip()
        if subtitle_text:
            metadata[MaidrKey.SUBTITLE] = subtitle_text

        return metadata

    def _flatten_maidr(self) -> dict:
        """Build the MAIDR schema from all extracted plots.

        Groups plots by their ``(row_index, col_index)`` position to
        construct a subplot grid matching the Plotly figure layout.
        """
        # Collect schemas with their grid positions
        plot_entries = []
        for plot in self._plots:
            plot_entries.append(
                {
                    "schema": plot.schema,
                    "row": plot.row_index,
                    "col": plot.col_index,
                }
            )

        max_row = max((e["row"] for e in plot_entries), default=0)
        max_col = max((e["col"] for e in plot_entries), default=0)
        is_multi_subplot = max_row > 0 or max_col > 0

        # Build the grid
        subplot_grid: list[list[dict]] = [
            [{} for _ in range(max_col + 1)] for _ in range(max_row + 1)
        ]

        # Group by position
        position_groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for entry in plot_entries:
            pos = (entry["row"], entry["col"])
            position_groups[pos].append(entry["schema"])

        for (row, col), layers in position_groups.items():
            cell: dict = {
                "id": str(uuid.uuid4()),
                "layers": layers,
            }
            if is_multi_subplot:
                selector_id = f"axes_{uuid.uuid4()}"
                cell["selector"] = f'g[id="{selector_id}"]'
            subplot_grid[row][col] = cell

        # Fill empty cells
        for r in range(len(subplot_grid)):
            for c in range(len(subplot_grid[r])):
                if not subplot_grid[r][c]:
                    subplot_grid[r][c] = {
                        "id": str(uuid.uuid4()),
                        "layers": [],
                    }

        return {
            "id": self.maidr_id,
            **self._figure_metadata(),
            "subplots": subplot_grid,
        }

    def _get_plotly_html(self) -> str:
        """Get Plotly's interactive HTML div.

        Returns the chart as an interactive HTML fragment that includes
        plotly.js from CDN.  This preserves all native Plotly features
        (hover, zoom, pan, click events, etc.).
        """
        return self._fig.to_html(
            full_html=False,
            include_plotlyjs="cdn",
        )

    def _build_init_script(
        self,
        schema: dict,
        use_cdn: bool | Literal["auto"] = "auto",
        iframe_in_notebook: bool = False,
    ) -> str:
        """Build JS that bridges Plotly's SVG with MAIDR.

        After Plotly renders its chart into the DOM as an SVG, this
        script injects the MAIDR schema into the SVG element and, when
        CDN mode is requested, dynamically loads the MAIDR JS library.
        When ``use_cdn=False`` outside an iframe the bundle is already
        loaded by an :class:`htmltools.HTMLDependency` so no loader is
        emitted.  In ``"auto"`` mode the loader attempts the CDN first
        and falls back to the bundled copy on ``onerror``.

        When ``iframe_in_notebook=True`` the loader instead pulls the
        bundled source strings from ``window.parent.__maidrJsSource`` /
        ``window.parent.__maidrMathCssSource`` (populated by
        :func:`maidr.api.init_notebook`).  Relative ``lib/maidr-.../``
        paths do not resolve inside a srcdoc iframe, and
        ``HTMLDependency`` children are stripped by
        ``Tag.get_html_string()``, so the parent-window stash is the
        only reliable offline fallback in notebooks.

        Parameters
        ----------
        schema : dict
            The MAIDR schema to inject into the SVG element.
        use_cdn : bool or {"auto"}, default="auto"
            See :meth:`render` for mode descriptions.
        iframe_in_notebook : bool, default=False
            ``True`` when the emitted HTML will be wrapped in a
            notebook/Shiny srcdoc iframe.  Switches the loader to use
            the parent-window source strings instead of relative paths.
        """
        dom_wiring = f"""
            var maidrSchema = {json.dumps(schema, indent=2)};

            var _maidrDone = false;
            function initMaidr() {{
                if (_maidrDone) return;
                var svg = document.querySelector('svg.main-svg');
                if (!svg) {{
                    requestAnimationFrame(initMaidr);
                    return;
                }}
                _maidrDone = true;

                svg.setAttribute('id', maidrSchema.id);
                svg.setAttribute('maidr', JSON.stringify(maidrSchema));
            __LOADER__
            }}

            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', initMaidr);
            }} else {{
                requestAnimationFrame(initMaidr);
            }}
        """

        # Snippet that pulls the bundled JS and KaTeX source from the
        # parent notebook window.  Reused by ``use_cdn=False`` (primary
        # loader) and ``use_cdn="auto"`` (CDN onerror fallback).
        #
        # KaTeX travels as a string because ``maidr.js`` resolves
        # ``maidr-math.css`` against the URL it was loaded from, and an
        # inline script inside a srcdoc iframe has no URL to offer it.
        def parent_source(
            on_missing: str, on_unreachable: str | None = None
        ) -> str:
            """Return the parent-window loader, reporting failure as told.

            The two ``use_cdn`` modes reach this for different reasons and so
            need different advice. Under ``False`` the caller asked for the
            bundle and the fix is ``init_notebook()``; under ``"auto"`` the
            CDN was simply unreachable and the fix is ``use_cdn=False``.
            Sharing one message would send half the callers somewhere useless.

            Built by placeholder replacement rather than as an f-string,
            unlike everything else in this file: the JS body is full of
            literal braces, and an f-string would need every one of them
            doubled -- which is how a template like this acquires a
            mismatched brace that only shows up as broken JS in a browser.

            Parameters
            ----------
            on_missing : str
                JS run when the parent is readable but holds no stash.
            on_unreachable : str or None, optional
                JS run when the parent could not be read at all -- a
                cross-origin frame, or no parent. ``None`` reuses
                ``on_missing``, which is right only where the two have the
                same answer; under ``"auto"`` they do not, and reporting a
                missing stash for an unreachable parent sends the reader
                looking in the wrong place. ``None`` rather than ``""`` so
                that "same answer" and "say nothing" stay distinguishable
                if a caller ever wants the latter.

            Returns
            -------
            str
                The loader, as JS.
            """
            return """
            (function() {
                try {
                    var jsSrc = window.parent && window.parent.__maidrJsSource;
                    var mathCss = window.parent && window.parent.__maidrMathCssSource;
                    if (mathCss) {
                        var style = document.createElement('style');
                        style.textContent = mathCss;
                        document.head.appendChild(style);
                        // maidr.js looks for a <link> carrying this attribute
                        // to decide whether the rules are already present; a
                        // <style> never matches, and the miss is reported to
                        // the console as maths rendering unstyled.
                        var mark = document.createElement('link');
                        mark.setAttribute('data-maidr-math', '');
                        document.head.appendChild(mark);
                    }
                    if (jsSrc) {
                        var s = document.createElement('script');
                        s.text = jsSrc;
                        document.head.appendChild(s);
                        return true;
                    }
                    __ON_MISSING__
                    return false;
                } catch (_) {
                    __ON_UNREACHABLE__
                    return false;
                }
            })();
        """.replace("__ON_MISSING__", on_missing).replace(
                "__ON_UNREACHABLE__",
                on_missing if on_unreachable is None else on_unreachable,
            )

        # ``use_cdn=False``: the caller asked for the bundle, so the fix is
        # to stash it, not to change the mode.
        notebook_stash_missing = """
                if (window.console) {
                    console.warn(
                        'maidr: use_cdn=False requires maidr.init_notebook() ' +
                        'to be called once per notebook session, or the bundle ' +
                        'to be available on window.parent.__maidrJsSource.'
                    );
                }
        """

        parent_source_snippet = parent_source(notebook_stash_missing)

        if use_cdn is False:
            if iframe_in_notebook:
                # Iframe path: HTMLDependency would be dropped by
                # ``Tag.get_html_string()``.  Pull the bundled source
                # strings from the parent window instead.
                loader = parent_source_snippet
            else:
                # Non-iframe path: ``maidr.js`` is already in the DOM
                # via ``HTMLDependency`` (emitted by htmltools as a
                # regular ``<script src>``).  Nothing to do here.
                loader = ""
        elif use_cdn == "auto":
            # Resolved lazily and only on the CDN paths: ``use_cdn=False``
            # must never touch the network.
            js_cdn_url = maidr_js_cdn_url()
            if iframe_in_notebook:
                # Iframe path: try the CDN first, fall back to the
                # parent-window source on ``onerror``.  Relative
                # ``lib/`` paths cannot be resolved inside srcdoc.
                # Under "auto" the CDN was simply unreachable, so the
                # stash being empty too means there is no source left --
                # which is what ``reportNoRuntime`` is for. Under
                # ``use_cdn=False`` the same miss means something else
                # (see ``parent_source``), hence the separate wording.
                auto_parent_source = parent_source(
                    "reportNoRuntime('the notebook page has no stashed copy');",
                    "reportNoRuntime('the parent page is unreachable');",
                )
                loader = f"""
{OFFLINE_FALLBACK_REPORT}
                    var existing = document.querySelector(
                        'script[src="{js_cdn_url}"]'
                    );
                    if (!existing) {{
                        var s = document.createElement('script');
                        s.src = '{js_cdn_url}';
                        s.onerror = function() {{{auto_parent_source}}};
                        document.head.appendChild(s);
                    }}
                """
            else:
                rel_dir = maidr_bundled_relative_dir()
                bundled_js_rel = f"{rel_dir}/{MAIDR_JS_FILENAME}"
                loader = f"""
{OFFLINE_FALLBACK_REPORT}
                    var existing = document.querySelector(
                        'script[src="{js_cdn_url}"]'
                    );
                    if (!existing) {{
                        var s = document.createElement('script');
                        s.src = '{js_cdn_url}';
                        s.onerror = function() {{
                            var fb = document.createElement('script');
                            fb.src = '{bundled_js_rel}';
                            // The relative path resolves wherever the host
                            // serves the copied bundle -- save_html -- and
                            // cannot inside a srcdoc iframe nobody serves
                            // those files for. Without this the chart is an
                            // image with no runtime and nothing said.
                            fb.onerror = function() {{
                                reportNoRuntime(
                                    'the bundled copy at {bundled_js_rel} '
                                    + 'did not load'
                                );
                            }};
                            document.head.appendChild(fb);
                        }};
                        document.head.appendChild(s);
                    }}
                """
        else:
            js_cdn_url = maidr_js_cdn_url()
            loader = f"""
                var existing = document.querySelector(
                    'script[src="{js_cdn_url}"]'
                );
                if (!existing) {{
                    var s = document.createElement('script');
                    s.src = '{js_cdn_url}';
                    document.head.appendChild(s);
                }}
            """

        body = dom_wiring.replace("__LOADER__", loader)
        return f"(function() {{{body}}})();"

    def _create_html_tag(
        self,
        use_iframe: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> Tag:
        """Create HTML with interactive Plotly chart and MAIDR accessibility.

        The output includes:

        1. The interactive Plotly chart (plotly.js loaded from CDN)
        2. A bridge script that waits for Plotly to render, injects the
           MAIDR schema into the SVG, and (in online mode) loads the
           MAIDR JS bundle.

        No MAIDR stylesheet is emitted: the accessibility UI is styled at
        runtime, and KaTeX -- the one stylesheet with rules in it -- is
        fetched by ``maidr.js`` from wherever it was itself loaded.

        Parameters
        ----------
        use_iframe : bool, default=True
            Wrap the rendered output in a sandboxed iframe for
            notebook / Shiny / Flask environments.
        use_cdn : bool or {"auto"}, default="auto"
            See :meth:`render` for mode descriptions.
        """
        # Decide whether the iframe-in-notebook "load-once" fast path
        # applies.  ``Tag.get_html_string()`` (used by
        # :func:`wrap_in_iframe_plotly`) silently drops
        # ``HTMLDependency`` children, so for iframe renders we must
        # not rely on htmltools to inject the bundled script.  Instead
        # the init script evaluates the JS source which
        # :func:`maidr.api.init_notebook` has stashed on
        # ``window.__maidrJsSource`` in the parent document.  Mirrors
        # the matplotlib ``_inject_plot`` logic.
        #
        # The parent-window stash only exists in a notebook, because
        # ``init_notebook()`` returns early everywhere else.  Any other
        # iframed render -- Shiny, Flask -- carries the bundle inline
        # instead; see ``iframe_inline_bundle``.
        in_notebook = Environment.is_notebook()
        will_iframe = use_iframe and (
            Environment.is_flask() or in_notebook or Environment.is_shiny()
        )
        iframe_in_notebook = will_iframe and in_notebook
        iframe_inline_bundle = will_iframe and not in_notebook

        schema = self._flatten_maidr()

        # Same question the matplotlib path asks: can the copy that will
        # run actually draw these layers (#358)? Version distance cannot
        # answer it, and this needs no network.
        # Kept in step with the `use_cdn` branching in the use_cdn branches below, where
        # `warn_if_bundle_is_stale` is called: these are two readings of the
        # same decision in two places, and the schema this one needs is not
        # available down there. Change one and check the other.
        if use_cdn is not True:
            warn_if_bundle_cannot_render(
                schema_trace_types(schema), bundle_is_primary=use_cdn is False
            )

        plotly_div = self._get_plotly_html()
        init_script = self._build_init_script(
            schema, use_cdn=use_cdn, iframe_in_notebook=iframe_in_notebook
        )

        children: list[Any] = []
        if use_cdn is False:
            # Bundled copy is the only source; surface it if it has aged.
            warn_if_bundle_is_stale()
            if iframe_in_notebook:
                # ``HTMLDependency`` is dropped by ``get_html_string()``
                # during iframe serialisation; the init script's
                # parent-source loader carries both the JS and KaTeX, so
                # no extra children are needed here.
                pass
            elif iframe_inline_bundle:
                # An iframe outside a notebook: the dependency below would
                # be dropped by ``get_html_string()`` and there is no
                # parent stash to read, so the bundle travels inline.
                # These tags precede the init script, so ``maidr.js`` is
                # in the document by the time the loader would have run --
                # which is why the loader for this case is empty, exactly
                # as it is for the non-iframe dependency path.
                inline_tags = inline_bundle_tags()
                if inline_tags is None:
                    # Bundle unreadable; already warned.  A CDN tag is the
                    # only remaining source, and a chart that needs the
                    # network beats one that cannot be read at all.
                    inline_tags = [
                        tags.script(src=bundled_cdn_url(MAIDR_JS_FILENAME))
                    ]
                children.extend(inline_tags)
            else:
                # The dependency copies the whole bundle, so ``maidr.js``
                # finds ``maidr-math.css`` beside itself; no ``<link>``
                # needs emitting.
                children.append(maidr_html_dependency())
        elif use_cdn == "auto":
            # Published version is resolved by now, so the bundled
            # fallback's age is known for free.  Fallback, not primary.
            warn_if_bundle_is_stale(bundle_is_primary=False)
            if not iframe_in_notebook:
                # Copy the bundle alongside the HTML without auto-emitted
                # tags, so the JS loader's ``onerror`` path has something
                # to fall back to.
                children.append(maidr_bundled_files_dependency())
        children.append(tags.div(HTML(plotly_div)))
        children.append(tags.script(init_script, type="text/javascript"))

        base_html = tags.div(*children)

        # Same condition as ``will_iframe`` above, reused so the branch
        # that picks a source for ``maidr.js`` and the branch that wraps
        # the result cannot disagree about whether there is an iframe.
        if will_iframe:
            base_html = wrap_in_iframe_plotly(base_html, chart_title_of(schema))

        return base_html

    def _create_html_doc(
        self,
        use_iframe: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> HTMLDocument:
        """Create a full HTML document."""
        return HTMLDocument(
            self._create_html_tag(use_iframe, use_cdn=use_cdn), lang="en"
        )

    def _open_plot_in_browser(
        self, use_cdn: bool | Literal["auto"] = "auto"
    ) -> None:
        """Open the rendered HTML in a browser via a temp file.

        Parameters
        ----------
        use_cdn : bool or {"auto"}, default="auto"
            Bundle MAIDR JS assets next to the temp HTML file when
            ``False`` (or ``"auto"``) so the browser can load everything
            over ``file://`` without network access.
        """
        system_temp_dir = tempfile.gettempdir()
        static_temp_dir = os.path.join(system_temp_dir, "maidr")
        os.makedirs(static_temp_dir, exist_ok=True)

        temp_file_path = os.path.join(static_temp_dir, "maidr_plotly_plot.html")
        html_file_path = self.save_html(temp_file_path, use_cdn=use_cdn)
        webbrowser.open(f"file://{html_file_path}")


def _domain_start(box: Any, key: str) -> float:
    """
    Return where one ``domain`` interval starts, as a fraction of the figure.

    Parameters
    ----------
    box : Any
        A layout axis, whose ``domain`` holds the interval, or a trace's
        ``domain``, whose ``x`` and ``y`` hold one each.
    key : str
        The key holding the interval.

    Returns
    -------
    float
        The interval's start, rounded so that two subplots plotly placed
        together compare equal, or 0 for an interval that is absent or
        malformed -- the figure's own edge, which is the first row or column.
    """
    return domain_interval(box, key)[0]
