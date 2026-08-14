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
from maidr.plotly.plotly_plot import PlotlyPlot, domain_interval
from maidr.plotly.plotly_plot_factory import PlotlyPlotFactory
from maidr.plotly.step_shape import (
    is_connected_line_trace,
    is_scatter_family_trace,
    is_step_trace,
    renders_through_webgl,
)
from maidr.util.dependencies import (
    MAIDR_JS_FILENAME,
    maidr_bundled_files_dependency,
    maidr_bundled_relative_dir,
    maidr_html_dependency,
    maidr_js_cdn_url,
    schema_trace_types,
    warn_if_bundle_cannot_render,
    warn_if_bundle_is_stale,
)
from maidr.util.environment import Environment
from maidr.util.iframe_utils import wrap_in_iframe_plotly


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
_PLACED_BY_DOMAIN = frozenset({"pie"})

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

        for trace in traces:
            if trace.get("type") not in _PLACED_BY_DOMAIN:
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

        Every scatter-family trace is assigned a selector index from its
        position within the subplot, not within the layer it lands in — see
        :meth:`PlotlyPlot._scatter_line_selector`. Because of that, all
        scatter/lines traces are built here rather than left to
        :class:`PlotlyPlotFactory`, which cannot know those positions.
        """
        fig_dict = self._fig.to_dict()
        layout = fig_dict.get("layout", {})
        traces = fig_dict.get("data", [])
        # Plotly's own default is `relative`, which stacks. Defaulting to
        # `group` here meant a figure that plotly drew stacked was announced
        # as *dodged* -- not a lost relationship but an inverted one, telling
        # a reader the bars sit side by side when they sit on top of each
        # other, so every segment means something other than what is said and
        # the totals a stack is read for are absent (#390).
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
            connected_traces = [
                t for t in group_traces if is_connected_line_trace(t)
            ]
            box_traces = [
                t for t in group_traces if t.get("type") == "box"
            ]
            pie_traces = [
                t for t in group_traces if t.get("type") == "pie"
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
            position_of = {
                id(t): index
                for renderer in (svg_scatter, gl_scatter)
                for index, t in enumerate(renderer)
            }

            merged: set[int] = set()

            # Grouped / stacked bars
            if len(bar_traces) > 1 and barmode in _COMBINED_BARMODES:
                from maidr.core.enum.plot_type import PlotType
                from maidr.plotly.grouped_bar import PlotlyGroupedBarPlot

                plot_type = (
                    PlotType.DODGED if barmode == "group" else PlotType.STACKED
                )
                plot = PlotlyGroupedBarPlot(
                    bar_traces, layout, plot_type, **axis_kwargs
                )
                plot.row_index = row
                plot.col_index = col
                self._plots.append(plot)
                merged.update(id(t) for t in bar_traces)

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
                line_traces = [
                    t for t in renderer_traces if not is_step_trace(t)
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
                    box_traces, layout, **axis_kwargs
                )
                plot.row_index = row
                plot.col_index = col
                self._plots.append(plot)
                merged.update(id(t) for t in box_traces)

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

            # Remaining traces
            for trace in group_traces:
                if id(trace) in merged:
                    continue
                plot = PlotlyPlotFactory.create(
                    trace, layout, **axis_kwargs
                )
                if plot is not None:
                    plot.row_index = row
                    plot.col_index = col
                    self._plots.append(plot)

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
        parent_source_snippet = """
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
                } catch (_) { /* cross-origin or missing parent */ }
                if (window.console) {
                    console.warn(
                        'maidr: use_cdn=False requires maidr.init_notebook() ' +
                        'to be called once per notebook session, or the bundle ' +
                        'to be available on window.parent.__maidrJsSource.'
                    );
                }
                return false;
            })();
        """

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
                loader = f"""
                    var existing = document.querySelector(
                        'script[src="{js_cdn_url}"]'
                    );
                    if (!existing) {{
                        var s = document.createElement('script');
                        s.src = '{js_cdn_url}';
                        s.onerror = function() {{{parent_source_snippet}}};
                        document.head.appendChild(s);
                    }}
                """
            else:
                rel_dir = maidr_bundled_relative_dir()
                bundled_js_rel = f"{rel_dir}/{MAIDR_JS_FILENAME}"
                loader = f"""
                    var existing = document.querySelector(
                        'script[src="{js_cdn_url}"]'
                    );
                    if (!existing) {{
                        var s = document.createElement('script');
                        s.src = '{js_cdn_url}';
                        s.onerror = function() {{
                            var fb = document.createElement('script');
                            fb.src = '{bundled_js_rel}';
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
        iframe_in_notebook = use_iframe and (
            Environment.is_notebook() or Environment.is_shiny()
        )

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

        if use_iframe and (
            Environment.is_flask()
            or Environment.is_notebook()
            or Environment.is_shiny()
        ):
            base_html = wrap_in_iframe_plotly(base_html)

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
