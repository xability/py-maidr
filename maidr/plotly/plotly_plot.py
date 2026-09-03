from __future__ import annotations

import base64
import logging
import math
import re
import uuid
from abc import ABC, abstractmethod
from datetime import date
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType

# This is the import that makes the cycle: `step_shape` reads its trace arrays
# through `as_list`, defined below, and so imports this module back. It does so
# inside the function rather than here. Moving either import to the other's
# level closes the cycle and breaks both — see `step_shape._trace_point_count`.
from maidr.plotly.step_shape import renders_through_webgl

_logger = logging.getLogger(__name__)

#: A year-first date, leniently spelled. Plotly accepts single digits and
#: leading whitespace, so the shape is matched loosely here and the parts are
#: checked separately -- see :meth:`PlotlyPlot._looks_like_date`.
_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?(?:[ T].*)?$")

#: Date units coarsest first, the order :func:`_iso_dates` tries them in.
#: No hour on its own: ``2024-01-01T12`` is ISO 8601 but reads as nothing to
#: a listener, where ``2024-01-01T12:00`` is a time.
_DATE_UNITS = ("D", "m", "s", "ms", "us", "ns")


class PlotlyPlot(ABC):
    """
    Abstract base class for Plotly plots managed by the MAIDR system.

    Parameters
    ----------
    trace : dict
        The Plotly trace dictionary containing plot data.
    layout : dict
        The Plotly layout dictionary containing axes and title info.
    plot_type : PlotType
        The type of the plot to be created, as defined in the PlotType enum.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        plot_type: PlotType,
        *,
        xaxis_name: str = "xaxis",
        yaxis_name: str = "yaxis",
    ) -> None:
        self._trace = trace
        self._layout = layout
        self.type = plot_type
        self._xaxis_name = xaxis_name
        self._yaxis_name = yaxis_name
        self.row_index: int = 0
        self.col_index: int = 0
        self._schema: dict = {}
        # Set by `_drawn_line_series`; see it for why the pass is cached.
        self._line_series_cache: (
            tuple[list[dict], list[int], tuple[list[list[dict]], list[int]]] | None
        ) = None

    @staticmethod
    def _to_native(val: Any) -> Any:
        """Convert numpy scalars to native Python types.

        A date is spelled as the ISO string plotly's own ``to_json`` writes
        for it, rather than unwrapped: ``.item()`` on a ``datetime64`` gives a
        ``datetime`` at microsecond resolution and an epoch *integer* at
        nanosecond, and neither is what the schema wants -- the first cannot
        be serialised at all and the second announces a date as
        ``1704067200000000000`` (#699). The ``datetime64`` check comes before
        ``.item()`` for that reason, and ``date`` covers ``datetime`` and
        ``pandas.Timestamp`` with it.

        Parameters
        ----------
        val : Any
            The value to convert.

        Returns
        -------
        Any
            A native Python type if the input was a numpy scalar, an ISO
            string if it was a date, otherwise the original value.
        """
        if isinstance(val, np.datetime64):
            return str(np.datetime_as_string(val, unit="auto"))
        if isinstance(val, date):
            return val.isoformat()
        if hasattr(val, "item"):
            return val.item()
        return val

    def render(self) -> dict:
        """Generate the MAIDR schema for this plot layer."""
        data = self._extract_plot_data()
        schema = {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: self.type,
            MaidrKey.TITLE: self._get_title(),
            MaidrKey.AXES: self._extract_axes_data(),
            MaidrKey.DATA: data,
        }
        selector = self._get_selector()
        if selector:
            schema[MaidrKey.SELECTOR] = selector
        return schema

    def _subplot_css_prefix(self) -> str:
        """Return a CSS prefix that scopes selectors to this subplot.

        Plotly renders each subplot inside a ``<g class="subplot xy">``
        (or ``x2y2``, ``x3y3``, …) element.  This method converts the
        stored axis names into the corresponding CSS selector prefix so
        that selectors only match elements within a single subplot.
        """
        return subplot_css_prefix(self._xaxis_name, self._yaxis_name)

    def _scatter_line_selector(self, position: int) -> str:
        """
        Return the selector for one scatter trace's rendered line path.

        ``nth-child`` counts within the subplot's ``scatterlayer``, which
        holds *every* scatter-family trace on the subplot. So the index has
        to be a trace's position there, never its position within whichever
        MAIDR layer it was grouped into. Those two agree only while one layer
        owns every scatter trace on the subplot — which stopped being true
        once step traces were split out into their own layers.

        Parameters
        ----------
        position : int
            The trace's zero-based position among the subplot's
            scatter-family traces.

        Returns
        -------
        str
            A CSS selector scoped to this subplot and that one trace.
        """
        return (
            f"{self._subplot_css_prefix()}.scatterlayer > "
            f".trace.scatter:nth-child({position + 1}) path.js-line"
        )

    def _scatter_line_selectors(
        self, traces: list[dict], positions: list[int]
    ) -> list[str]:
        """
        Return one line selector per trace, or none when they are not SVG.

        A WebGL trace has no element to address, so a selector built for it
        would resolve to zero elements and the highlight would simply not
        appear — with nothing in the output to say why. Emitting no selector
        at all says the same thing honestly: this layer has no highlightable
        geometry, while its audio, braille and text are unaffected.

        The choice is all-or-nothing per layer rather than per trace, because
        the emitted list is positional — the frontend pairs selector *i* with
        series *i*. Dropping one entry from the middle would slide every later
        series onto the wrong element, which is worse than no highlight.

        Parameters
        ----------
        traces : list of dict
            The traces this layer covers, in series order.
        positions : list of int
            Each trace's zero-based position among the subplot's
            scatter-family traces, in the same order.

        Returns
        -------
        list of str
            One selector per series, or an empty list for a WebGL layer.
        """
        # `any`, not `all`: the renderer split upstream already guarantees a
        # homogeneous layer, so the two agree today. If that invariant ever
        # breaks, `any` fails closed -- no highlight -- while `all` would emit
        # a full set of selectors for a layer that is partly canvas, putting
        # every series after the gl trace on the wrong element.
        if any(renders_through_webgl(trace) for trace in traces):
            return []
        return [self._scatter_line_selector(position) for position in positions]

    def _line_series_with_positions(
        self, traces: list[dict], positions: list[int]
    ) -> tuple[list[list[dict]], list[int]]:
        """
        Build the drawn series and the positions they were drawn at, together.

        ``data`` and ``selector`` are paired positionally by the frontend, so
        they have to be filtered by the same predicate. They were not: a trace
        whose ``x``/``y`` came out empty was dropped from the data and still
        consumed a selector, which slid every later series onto its
        predecessor's element (#316). The audio, braille and text stayed
        correct, so only a sighted collaborator could see the wrong line
        highlighted -- the failure was invisible to the person using it.

        Returning both from one pass is the fix, and is what stops the two
        drifting apart again. The alternative, keeping the empty series so the
        lists stay parallel, would emit a zero-point series for the frontend
        to tolerate; dropping the position costs nothing and leaves ``data``
        exactly as it is today.

        An empty ``x``/``y`` is not exotic. It is what a series filtered to
        nothing produces, which is routine in a dashboard or a faceted export
        where one category has no rows in the current slice.

        Parameters
        ----------
        traces : list of dict
            The traces this layer covers, in series order.
        positions : list of int
            Each trace's zero-based position among the subplot's
            scatter-family traces, in the same order.

        Returns
        -------
        tuple of (list of list of dict, list of int)
            The non-empty series, and the positions of the traces that
            produced them -- index-aligned, and the same length.
        """
        series_list: list[list[dict]] = []
        drawn_positions: list[int] = []

        for trace, position in zip(traces, positions):
            x_values, y_values = paired_axes(trace)
            name = trace.get("name", "")

            series: list[dict] = []
            for x_value, y_value in zip(x_values, y_values):
                point: dict = {
                    MaidrKey.X: self._to_native(x_value),
                    MaidrKey.Y: self._to_native(y_value),
                }
                if name:
                    point[MaidrKey.Z] = name
                series.append(point)

            if series:
                series_list.append(series)
                drawn_positions.append(position)

        return series_list, drawn_positions

    def _drawn_line_series(
        self, traces: list[dict], positions: list[int]
    ) -> tuple[list[list[dict]], list[int]]:
        """
        Return ``_line_series_with_positions``, run once per layer.

        ``render()`` asks for the data and the selector as two separate steps,
        and both answers come out of the same pass. Running it a second time
        for the second caller is not merely wasteful — it assumes the pass can
        be repeated, and it cannot: ``as_list`` materialises a trace array with
        ``list(value)``, so a one-shot iterable is spent by the first walk and
        reads as empty on the second. The layer then reports its series and no
        selector at all, which is the silent no-highlight this pairing exists
        to prevent.

        ``Figure.to_dict()`` hands back lists, numpy arrays and typed-array
        specs, never an iterator, so the export path does not reach that. A
        caller constructing a layer directly does.

        Cached against the two lists by identity rather than unconditionally,
        so a caller passing different traces gets an answer for those traces
        instead of the previous ones. Identity rather than equality because a
        layer always hands over the same two objects it stored in ``__init__``,
        so the check is free where it matters and never walks the points to
        decide whether to walk the points.

        One entry, deliberately — not a memoizer. It exists so that the two
        halves of a single ``render()`` share one pass, and a layer only ever
        asks about one pair. Alternating between two pairs would recompute
        every time, correctly; if that ever becomes a real call pattern, this
        wants replacing rather than widening.

        Parameters
        ----------
        traces : list of dict
            The traces this layer covers, in series order.
        positions : list of int
            Each trace's zero-based position among the subplot's
            scatter-family traces, in the same order.

        Returns
        -------
        tuple of (list of list of dict, list of int)
            The non-empty series and the positions they were drawn at.
        """
        cached = self._line_series_cache
        if cached is not None and cached[0] is traces and cached[1] is positions:
            return cached[2]

        drawn = self._line_series_with_positions(traces, positions)
        self._line_series_cache = (traces, positions, drawn)
        return drawn

    @staticmethod
    def _validate_scatter_positions(positions: list[int], trace_count: int) -> None:
        """
        Reject a position list that cannot describe these traces.

        Requiring positions closes the hole where a caller supplied none. It
        leaves a second one with the same failure mode: a list that is simply
        wrong. The emitted selector list is positional — the frontend pairs
        selector *i* with series *i* — so a length mismatch slides every later
        series onto another element, a negative index builds ``nth-child(0)``
        or lower and matches nothing, and a repeat points two series at one
        element. None of those raise on their own; they highlight the wrong
        geometry, which is the outcome this whole parameter exists to prevent.

        The guard is not exhaustive, and cannot be: a position beyond the
        subplot's actual scatter-trace count is well-formed by every rule
        here, so ``scatter_position=99`` on a two-trace subplot constructs
        happily and simply matches nothing at render time. Only
        ``PlotlyMaidr._extract_plots`` knows that total, so an upper bound
        would have to live there rather than in this class.

        Parameters
        ----------
        positions : list of int
            Zero-based positions among the subplot's scatter-family traces.
        trace_count : int
            How many traces this layer covers.

        Raises
        ------
        TypeError
            If ``positions`` is not a list/tuple, or any entry is not an int.
        ValueError
            If the length disagrees with ``trace_count``, or any position is
            negative or repeated.
        """
        # Type-checked before anything else, because the value most likely to
        # arrive here wrongly is ``None`` -- it was this parameter's default
        # until it became required, so a caller migrating off that default is
        # exactly who passes it explicitly. Left unchecked it surfaced as
        # "object of type 'NoneType' has no len()" or "'<' not supported
        # between instances of 'NoneType' and 'int'", neither of which names
        # the argument at fault.
        if not isinstance(positions, (list, tuple)):
            raise TypeError(
                f"scatter positions must be a list of int, got {positions!r}"
            )

        if len(positions) != trace_count:
            plural = "" if trace_count == 1 else "s"
            raise ValueError(
                f"expected {trace_count} scatter position{plural} to match "
                f"{trace_count} trace{plural}, got {len(positions)}: {positions}"
            )
        if any(not isinstance(position, int) for position in positions):
            raise TypeError(f"scatter positions must all be int, got {positions!r}")

        if any(position < 0 for position in positions):
            raise ValueError(f"scatter positions must be >= 0, got {positions}")
        if len(set(positions)) != len(positions):
            raise ValueError(f"scatter positions must be unique, got {positions}")

    # --- Which order plotly draws a categorical axis in ------------------
    #
    # Lifted here from `PlotlyHeatmapPlot`, unchanged, because every one of
    # these is about an *axis* rather than about a heatmap -- and the bar
    # family needs the same answers (#495). `_to_native` is reached through
    # `self`, so the heatmap's own override still applies to a heatmap and
    # the base's to everything else.

    @staticmethod
    def _looks_numeric(value: Any) -> bool:
        """Whether plotly would read a label as a number rather than a name.

        Numeric strings count: plotly resolves a linear axis for ``"1"`` just
        as it does for ``1``, and for ``"1e10"``.

        ``nan`` and ``inf`` do not, in either spelling. Python parses both,
        where the JavaScript coercion plotly tests with does not -- measured,
        a heatmap over ``['nan', 'inf', 'zeta']`` gets a *category* axis and
        honours its ``categoryarray``. Reading them as numbers here would
        decline a sort plotly applies.

        Parameters
        ----------
        value : Any
            One axis label.

        Returns
        -------
        bool
            True when the label parses as a finite number.
        """
        if isinstance(value, bool):
            return False
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _looks_like_date(value: Any) -> bool:
        """Whether plotly would read a label as a date rather than a name.

        A date axis ignores ``categoryorder`` exactly as a linear one does --
        measured, ISO dates with an array declared came out drawn
        chronologically and ``_categories`` empty -- so an order applied to
        one would reorder a chart plotly draws by time.

        Year-first and hyphen-separated is the whole shape, and plotly checks
        that the parts make a real day rather than that they look like one --
        so this parses them rather than matching a stricter pattern. Measured::

            2024-03-01           date        2024/03/01     category
            2024-03              date        03-01-2024     category
            2024-03-01 12:00     date        Mar 2024       category
            2024-03-01T12:00:00  date        Q1             category
            2024-3-1             date        2024-13-45     category
            ' 2024-03-01'        date        2024-02-30     category
                                             2024-04-31     category

        The last two columns are why a tighter regex was the wrong tool: it
        missed single digits and leading whitespace, which plotly accepts --
        the direction that *applies* an order plotly ignores -- and it let
        through impossible days, which plotly rejects.

        Parameters
        ----------
        value : Any
            One axis label.

        Returns
        -------
        bool
            True when the label parses as a date.
        """
        if not isinstance(value, str):
            return False

        match = _ISO_DATE.match(value.strip())
        if match is None:
            return False

        year, month, day = match.groups()
        try:
            # A year and month alone is a date to plotly, so the day defaults
            # to one that every month has.
            date(int(year), int(month), int(day) if day else 1)
        except ValueError:
            return False
        return True

    def _axis_runs_backwards(self, axis_name: str) -> bool:
        """Whether plotly draws an axis from its high end to its low one.

        True only when the author asked for a reversed axis. On y that means
        the first category is drawn at the top -- the idiom for showing a
        matrix in reading order -- where plotly ordinarily numbers a heatmap's
        rows from the bottom. On x it means the columns run right to left.

        Read from the declared layout rather than a resolved one, because
        there is no browser here to resolve it. That is why ``autorange`` is
        usable: it still carries the author's ``"reversed"`` verbatim, where
        the rendered figure would report a plain ``True`` for both the
        default and the reversed case.

        Parameters
        ----------
        axis_name : str
            The layout key for the axis, e.g. ``"yaxis"`` or ``"xaxis2"``.

        Returns
        -------
        bool
            True when the axis runs backwards.
        """
        axis = self._layout.get(axis_name, {})
        if not isinstance(axis, dict):
            return False

        if axis.get("autorange") == "reversed":
            return True

        axis_range = axis.get("range")
        if isinstance(axis_range, (list, tuple)) and len(axis_range) >= 2:
            try:
                return float(axis_range[0]) > float(axis_range[1])
            except (TypeError, ValueError):
                return False

        return False

    def _drawn_category_order(self, axis_name: str, labels: list) -> list[int] | None:
        """Where each of an axis's drawn categories sits in the trace's labels.

        ``categoryorder`` sorts a categorical axis and leaves the trace's own
        ``x``, ``y`` and ``z`` exactly as the author wrote them, so the labels
        alone do not say what the chart shows. This resolves the sort from the
        declared layout, in the order plotly lays the categories out from the
        axis origin -- left for x, bottom for y. It says nothing about a
        reversed axis, which flips the drawn direction without touching the
        order; :meth:`_axis_runs_backwards` answers that.

        Only the forms a declared spec can answer exactly are resolved:
        ``"array"`` with a ``categoryarray`` (which is what plotly express's
        ``category_orders`` compiles to) and the two ``"category"`` sorts. The
        aggregate orders -- ``total``, ``sum``, ``mean``, ``min``, ``max``,
        ``median`` -- are declined. They do apply to a heatmap, measured, but
        resolving them means reimplementing plotly's own aggregation and
        tie-breaking offline, and a sort that is subtly not plotly's would
        leave the chart confidently wrong in the same way reading the trace's
        order does. Leaving the sort unapplied is the smaller error.

        Parameters
        ----------
        axis_name : str
            The layout key for the axis, e.g. ``"xaxis"``.
        labels : list
            The labels the trace carries, in its own order.

        Returns
        -------
        list[int] | None
            Indices into ``labels`` in drawn order, or None to decline.
        """
        axis = self._layout.get(axis_name, {})
        if not isinstance(axis, dict):
            return None

        # Only a categorical axis has categories to put in an order. Plotly
        # infers the axis *type* first, and both the types it can infer here
        # ignore ``categoryorder`` and ``categoryarray`` outright: a *linear*
        # axis from numeric-looking labels, drawn in numeric order, and a
        # *date* axis from ISO dates, drawn chronologically. Applying a
        # declared order to either would reorder a chart plotly did not.
        # Declaring ``type: "category"`` is what makes it categorical again,
        # and then the order is honoured.
        #
        # One such label is enough, rather than all of them: measured, a mixed
        # set like ``[1, 3, 'b']`` still resolves linear. That is the
        # conservative reading where plotly's own rule is a proportion, and it
        # errs toward leaving a sort unapplied rather than inventing one.
        #
        # What "from the axis origin" means on y is measured rather than
        # assumed by analogy with the heatmap. An **unsorted** horizontal bar
        # written ['charlie', 'alpha', 'bravo'] draws its tick labels top to
        # bottom as `bravo, alpha, charlie` -- so the trace's own order, which
        # py-maidr has always emitted for such a chart, is bottom-to-top on
        # screen. Bottom-up is the order already shipping, and a sorted chart
        # matches it rather than flipping.
        if axis.get("type") != "category" and any(
            self._looks_numeric(label) or self._looks_like_date(label)
            for label in labels
        ):
            return None

        order = axis.get("categoryorder")
        declared = as_list(axis.get("categoryarray"))
        # Measured: plotly resolves ``categoryorder`` to ``"array"`` whenever
        # ``categoryarray`` is non-empty and no order was declared, and draws
        # in it -- so a figure that sets only the array is still sorted. An
        # order that *was* declared wins over the array, empty or not.
        if order is None and declared:
            order = "array"

        if order == "array":
            if not declared:
                return None
            # Through ``_to_native`` because ``labels`` came through it too: it
            # floats an integer, so a categoryarray of ``3`` compared raw would
            # never match a label of ``3.0`` and the sort would be declined
            # without a word. Both sides normalise the same way or neither can.
            drawn = [str(self._to_native(v)) for v in declared]
        elif order in ("category ascending", "category descending"):
            drawn = sorted(str(v) for v in labels)
            if order == "category descending":
                drawn.reverse()
        else:
            return None

        if len(drawn) != len(labels):
            # A ``categoryarray`` naming categories the trace does not carry
            # makes plotly draw empty columns, which ``points`` has no way to
            # say. Inventing or dropping one would be worse than leaving the
            # sort unapplied.
            return None

        position: dict[str, int] = {}
        for index, label in enumerate(labels):
            position.setdefault(str(label), index)
        # A repeated label leaves no unambiguous cell to send a category to.
        if len(position) != len(labels):
            return None

        resolved = []
        for name in drawn:
            index = position.get(name)
            if index is None:
                return None
            resolved.append(index)

        # A ``categoryarray`` that repeats an entry can name every label the
        # right number of times without being a permutation of them, which
        # would emit one column's values twice and lose another's.
        if len(set(resolved)) != len(labels):
            return None

        return resolved

    def _get_selector(self) -> str:
        """Return a CSS selector for Plotly SVG elements."""
        return ""

    def _get_title(self) -> str:
        """Extract the plot title from the layout.

        For subplots created with ``make_subplots(subplot_titles=...)``,
        Plotly stores the per-subplot titles as annotations.  This method
        matches annotations to the current subplot's y-axis domain so
        each subplot gets its own title instead of the figure-level one.
        """
        subplot_title = self._get_subplot_annotation_title()
        if subplot_title:
            return subplot_title

        title = self._layout.get("title", "")
        if isinstance(title, dict):
            return title.get("text", "")
        return str(title) if title else ""

    def _title_anchor(self) -> tuple[float, float]:
        """Return the point on the page a subplot title annotation sits at.

        ``make_subplots`` puts each subplot's title centred over the top of
        that subplot, so the pair is the horizontal midpoint and the top edge
        of whatever rectangle the subplot occupies. A cartesian subplot's
        rectangle is the product of its two axis domains, which is what this
        reads. A plot placed some other way — a pie, which has no axis pair at
        all and so would read the layout defaults here and land at the middle
        of the figure whatever column it is really in — overrides this with
        the rectangle it does have.

        Returns
        -------
        tuple of (float, float)
            The ``(x_mid, y_top)`` of this subplot, as fractions of the
            figure.
        """
        x_domain = domain_interval(self._layout.get(self._xaxis_name, {}), "domain")
        y_domain = domain_interval(self._layout.get(self._yaxis_name, {}), "domain")
        return (x_domain[0] + x_domain[1]) / 2, y_domain[1]

    def _get_subplot_annotation_title(self) -> str | None:
        """Find the annotation that serves as this subplot's title.

        Plotly ``make_subplots`` places title annotations at the top of
        each subplot.  This matches annotations against the point
        :meth:`_title_anchor` reports for this plot, so a plot type that is
        not placed by an axis pair only has to say where it sits, not repeat
        the matching.
        """
        annotations = self._layout.get("annotations", [])
        if not annotations:
            return None

        x_mid, y_top = self._title_anchor()

        for ann in annotations:
            if ann.get("xref") != "paper" or ann.get("yref") != "paper":
                continue
            ann_y = ann.get("y", 0)
            ann_x = ann.get("x", 0)
            # Subplot title annotations sit just above the y-domain top
            if abs(ann_y - y_top) < 0.05 and abs(ann_x - x_mid) < 0.1:
                text = ann.get("text", "")
                if text:
                    return text
        return None

    @staticmethod
    def _axis_config(
        label: str | None = None,
        *,
        min: float | None = None,
        max: float | None = None,
        tick_step: float | None = None,
        format: dict | None = None,
    ) -> dict:
        """Build a canonical per-axis ``AxisConfig`` dict (only non-None keys)."""
        cfg: dict = {}
        if label is not None:
            cfg[MaidrKey.LABEL] = label
        if min is not None:
            cfg[MaidrKey.MIN] = min
        if max is not None:
            cfg[MaidrKey.MAX] = max
        if tick_step is not None:
            cfg[MaidrKey.TICK_STEP] = tick_step
        if format is not None:
            cfg[MaidrKey.FORMAT] = format
        return cfg

    def _extract_axes_data(self) -> dict:
        """Extract axes labels and format configuration as per-axis
        ``AxisConfig`` objects.

        ``format`` is nested inside each ``AxisConfig`` — never emitted as a
        sibling of ``x``/``y``/``z``.
        """
        xaxis = self._layout.get(self._xaxis_name, {})
        yaxis = self._layout.get(self._yaxis_name, {})

        x_label = xaxis.get("title", "")
        if isinstance(x_label, dict):
            x_label = x_label.get("text", "")

        y_label = yaxis.get("title", "")
        if isinstance(y_label, dict):
            y_label = y_label.get("text", "")

        format_config = self._extract_format(xaxis, yaxis) or {}

        return {
            MaidrKey.X: self._axis_config(
                label=str(x_label) if x_label else "X",
                format=format_config.get("x"),
            ),
            MaidrKey.Y: self._axis_config(
                label=str(y_label) if y_label else "Y",
                format=format_config.get("y"),
            ),
        }

    @staticmethod
    def _extract_format(xaxis: dict, yaxis: dict) -> dict[str, dict[str, Any]] | None:
        """Extract format configuration from Plotly axis settings.

        Parses ``tickformat``, ``tickprefix``, and ``ticksuffix`` from
        each axis and converts to MAIDR-compatible format dicts.
        """
        result: dict[str, dict[str, Any]] = {}

        x_fmt = PlotlyPlot._parse_axis_format(xaxis)
        if x_fmt:
            result["x"] = x_fmt

        y_fmt = PlotlyPlot._parse_axis_format(yaxis)
        if y_fmt:
            result["y"] = y_fmt

        return result if result else None

    @staticmethod
    def _parse_axis_format(axis: dict) -> dict[str, Any] | None:
        """Parse a single Plotly axis dict into a MAIDR format config.

        Handles Plotly's d3-format ``tickformat`` strings as well as
        ``tickprefix`` / ``ticksuffix`` for currency and percent.
        """
        tickformat = axis.get("tickformat", "")
        prefix = axis.get("tickprefix", "")
        suffix = axis.get("ticksuffix", "")

        # Check for date axis type even without tickformat/prefix/suffix
        if not tickformat and not prefix and not suffix:
            if axis.get("type") == "date":
                return {"type": "date", "dateFormat": None}
            return None

        # Currency via prefix ($, €, £, ¥)
        currency_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
        for symbol, code in currency_map.items():
            if symbol in prefix or symbol in tickformat:
                decimals = _extract_decimals(tickformat)
                return {"type": "currency", "decimals": decimals, "currency": code}

        # Percent via suffix or tickformat
        if suffix == "%" or (tickformat and "%" in tickformat):
            decimals = _extract_decimals(tickformat)
            return {"type": "percent", "decimals": decimals}

        # Scientific notation
        if tickformat and re.search(r"\.?\d*[eE]", tickformat):
            decimals = _extract_decimals(tickformat)
            return {"type": "scientific", "decimals": decimals}

        # Number with comma separator
        if tickformat and "," in tickformat:
            decimals = _extract_decimals(tickformat)
            return {"type": "number", "decimals": decimals}

        # Fixed decimal (e.g., ".2f")
        match = re.search(r"\.(\d+)f", tickformat) if tickformat else None
        if match:
            return {"type": "fixed", "decimals": int(match.group(1))}

        # Date format
        if axis.get("type") == "date":
            return {"type": "date", "dateFormat": tickformat or None}

        return None

    @abstractmethod
    def _extract_plot_data(self) -> list | dict:
        """Extract specific data from the Plotly trace."""
        raise NotImplementedError()

    @property
    def schema(self) -> dict:
        """Return the MAIDR schema of the plot as a dictionary.

        The emitted ``axes`` payload follows the canonical per-axis form —
        keys ⊆ ``{x, y, z}``; each value is an ``AxisConfig`` dict with
        optional ``label``, ``min``, ``max``, ``tickStep``, and ``format``
        fields. ``format``/``min``/``max``/``tickStep``/``fill``/``level``
        never appear as siblings of ``x``/``y``/``z``.
        """
        if not self._schema:
            self._schema = self.render()
        return self._schema


def domain_interval(box: Any, key: str) -> tuple[float, float]:
    """
    Return one ``domain`` interval, as fractions of the figure.

    Plotly places a *cartesian* subplot by giving each of its axes a
    ``domain`` interval, and a *domain* trace — ``go.Pie`` has no axes at all
    — by giving the trace's own ``domain`` an ``x`` and a ``y`` interval.
    Both are fractions of the same figure and are read the same way, so both
    are read here: :class:`~maidr.plotly.plotly_maidr.PlotlyMaidr` uses it to
    order subplots into a grid, and
    :class:`~maidr.plotly.pie.PlotlyPiePlot` to find where its own rectangle
    sits on the page.

    Parameters
    ----------
    box : Any
        A layout axis, whose ``domain`` holds the interval, or a trace's
        ``domain``, whose ``x`` and ``y`` hold one each. Anything that is not
        a dict is treated as absent.
    key : str
        The key holding the interval.

    Returns
    -------
    tuple of (float, float)
        The interval's start and end, rounded so that two subplots plotly
        placed together compare equal. An absent or malformed interval is
        the whole figure, ``(0.0, 1.0)`` — the first row and column, and the
        span a figure that was never split into subplots actually has.
    """
    whole = (0.0, 1.0)

    if not isinstance(box, dict):
        return whole

    interval = box.get(key, list(whole))
    if not isinstance(interval, (list, tuple)) or len(interval) < 2:
        return whole

    try:
        return round(float(interval[0]), 6), round(float(interval[1]), 6)
    except (TypeError, ValueError):
        return whole


#: The values of ``trace.visible`` that mean plotly drew nothing. ``False``
#: hides a trace outright; ``"legendonly"`` is what clicking a legend entry
#: sets, so a reader reaches it by ordinary use rather than an exotic figure.
_HIDDEN = (False, "legendonly")


def is_drawn(trace: dict) -> bool:
    """
    Return whether plotly drew this trace at all.

    Plotly renders no group whatsoever for a hidden trace -- measured across
    bar, scatter, pie, box and violin: two traces with one hidden produce a
    single group in the layer. So a hidden trace must be dropped before
    anything reads it, for two reasons at once.

    It must not be *announced*: describing it tells a reader about marks that
    are not on the chart, with nothing saying the series is switched off. And
    it must not take a *slot*: every selector scoped by position among its
    layer-mates would be pushed onto a group that does not exist, and a
    selector matching nothing loses the highlight silently while the audio,
    braille and text stay correct.

    Parameters
    ----------
    trace : dict
        A plotly trace dictionary.

    Returns
    -------
    bool
        ``True`` unless ``visible`` says otherwise. An absent ``visible`` is
        plotly's default of drawn.
    """
    return trace.get("visible") not in _HIDDEN


def subplot_css_prefix(xaxis_name: str, yaxis_name: str) -> str:
    """
    Return the CSS prefix scoping selectors to one subplot.

    Module level as well as a method, because a layer built from several
    traces needs the prefix *before* it has a plot to ask -- its selectors are
    computed while the traces are still being grouped.

    Parameters
    ----------
    xaxis_name, yaxis_name : str
        Layout keys for the pair, e.g. ``"xaxis"`` / ``"yaxis2"``.

    Returns
    -------
    str
        e.g. ``".subplot.xy "``, with the trailing space every caller
        concatenates onto.
    """
    # "xaxis" -> "x", "xaxis2" -> "x2", "xaxis3" -> "x3"
    x_ref = xaxis_name.replace("xaxis", "x")
    y_ref = yaxis_name.replace("yaxis", "y")
    return f".subplot.{x_ref}{y_ref} "


def colorbar_title(trace: dict) -> str:
    """The title the author gave the colour bar, or an empty string.

    Plotly accepts the title either as a string or as a ``{"text": ...}``
    block, and the trace may carry no ``colorbar`` at all. Read in one place
    because three layers name their third axis from it -- a heatmap, a
    choropleth and a two-dimensional histogram contour -- and a fourth
    spelling of the same three cases is how they drift apart.
    """
    colorbar = trace.get("colorbar")
    if not isinstance(colorbar, dict):
        return ""
    title = colorbar.get("title", "")
    if isinstance(title, dict):
        title = title.get("text", "")
    return str(title) if title else ""


def as_list(value: Any) -> list:
    """
    Return a plotly data array as a plain list.

    ``Figure.to_dict()`` hands back the arrays the author supplied, plus two
    shapes they never wrote: a numeric array is exported as the
    ``{"dtype": ..., "bdata": ...}`` base64 typed-array spec plotly.js
    consumes, and a non-numeric one stays a numpy array. ``plotly.express``
    produces one or the other for every column it plots, so every extractor
    reads its trace arrays through here -- iterating the spec directly walks
    its two keys and emits ``"dtype"`` and ``"bdata"`` as the data.

    A multi-dimensional array carries its extents alongside the buffer and is
    restored to nested lists, so a heatmap's ``z`` still arrives as rows.

    A date column is one of the arrays that stays numpy, and it is spelled
    here as the ISO strings plotly's own ``to_json`` writes, since the
    ``datetime64`` scalars it would otherwise decompose into serialise as
    nothing the schema can hold -- see :meth:`PlotlyPlot._to_native` (#699).

    A plain list or tuple is handed back as a list, so a hand-built
    ``go.Bar(y=[1, 2, 3])`` travels this path unchanged. An absent array
    becomes an empty list rather than staying ``None``: every caller reads a
    trace key that may simply not be there, and one empty answer for "no
    array" saves each of them a null check.

    Parameters
    ----------
    value : Any
        A plotly data array, a typed-array spec, or None.

    Returns
    -------
    list
        The array's entries, or an empty list.
    """
    if value is None:
        return []

    if isinstance(value, dict):
        return _decode_typed_array(value)

    # A string is iterable, so without this it would decompose into one
    # single-character entry per letter instead of being rejected.
    if isinstance(value, str):
        return []

    if isinstance(value, np.ndarray) and value.dtype.kind == "M":
        return _iso_dates(value)

    try:
        return list(value)
    except TypeError:
        return []


def _iso_dates(values: np.ndarray) -> list[str]:
    """
    Spell a ``datetime64`` array as ISO strings.

    One unit for the whole array, the coarsest that loses nothing of any
    entry: a daily series reads ``2024-01-01`` rather than the
    ``2024-01-01T00:00:00.000000`` plotly's verbatim rule writes, and an
    hourly one ``2024-01-01T12:00`` throughout. Numpy's ``unit="auto"``
    chooses per entry, which would spell the midnight and the noon of one
    series differently.

    Parameters
    ----------
    values : np.ndarray
        An array of ``datetime64`` values, at any resolution.

    Returns
    -------
    list[str]
        One ISO string per entry; ``NaT`` stays ``"NaT"``.
    """
    # NaT is unequal to everything including itself, so it is excused from
    # the comparison rather than forcing the finest unit on every real entry.
    real = ~np.isnat(values)
    for unit in _DATE_UNITS:
        coarse = values.astype(f"datetime64[{unit}]")
        if np.array_equal(coarse[real], values[real]):
            return np.datetime_as_string(coarse).tolist()
    return np.datetime_as_string(values).tolist()


def _decode_typed_array(spec: dict) -> list:
    """
    Decode one exported ``{"dtype": ..., "bdata": ...}`` typed-array spec.

    Parameters
    ----------
    spec : dict
        The exported spec. ``shape`` is present only for an array of more
        than one dimension, and names its extents as a comma-separated
        string.

    Returns
    -------
    list
        The buffer's entries, nested when ``shape`` says so. Anything that
        will not decode comes back empty rather than as something worse.

    Notes
    -----
    Failure is logged, not swallowed. An empty layer is a safer answer than a
    garbled one, but silence here would be the same fault this decoder exists
    to fix: a chart that draws correctly while its accessible layer is wrong
    and nothing says so. The log is what turns "the plot reads as empty" into
    something diagnosable.
    """
    dtype = spec.get("dtype")
    bdata = spec.get("bdata")
    if dtype is None or bdata is None:
        _logger.warning(
            "maidr: typed array names no %s; reporting no data for it.",
            "dtype" if dtype is None else "bdata",
        )
        return []

    try:
        array = np.frombuffer(base64.b64decode(bdata), dtype=dtype)
        shape = spec.get("shape")
        if shape is not None:
            extents = shape.split(",") if isinstance(shape, str) else shape
            # Three ways this raises, and the clauses below cover all of
            # them: an unknown `dtype` is a TypeError, base64 that will not
            # decode is a `binascii.Error` (a ValueError), and a `shape` that
            # is not integral, or does not multiply out to the buffer's
            # length, is a ValueError from `int()` or from `reshape`.
            #
            # `OverflowError` is listed for an extent too large to be a
            # dimension. numpy 2.4 answers that with a ValueError, so it is
            # unreachable on the version pinned here — but the project accepts
            # numpy>=1.26, and the cost of being wrong about one release in
            # that range is an uncaught exception taking down the whole
            # figure, which is what this decoder exists to prevent.
            array = array.reshape([int(extent) for extent in extents])
        return array.tolist()
    except (TypeError, ValueError, OverflowError) as error:
        _logger.warning(
            "maidr: could not decode a typed array (dtype=%r, shape=%r): %s; "
            "reporting no data for it.",
            dtype,
            spec.get("shape"),
            error,
        )
        return []


def _extract_decimals(fmt: str) -> int | None:
    """Extract decimal places from a d3-format / Plotly tickformat string."""
    if not fmt:
        return None
    match = re.search(r"\.(\d+)", fmt)
    return int(match.group(1)) if match else None


def paired_axes(trace: dict) -> tuple:
    """Return a trace's ``x`` and ``y`` arrays, generating whichever is absent.

    Both are optional in plotly, and it fills in the missing one with
    ``0, 1, 2, ...``. Measured in Chromium rather than assumed, in both
    directions:

    ===========================================  ===========  ===========
    trace                                        calcdata x   calcdata y
    ===========================================  ===========  ===========
    ``go.Scatter(y=[1,2,3], mode="lines")``      ``0,1,2``    ``1,2,3``
    ``go.Bar(y=[3,1,2])``                        ``0,1,2``    ``3,1,2``
    ``go.Bar(x=[3,1,2], orientation="h")``       ``3,1,2``    ``0,1,2``
    ``go.Scatter(x=[3,1,2], mode="lines")``      ``3,1,2``    ``0,1,2``
    ===========================================  ===========  ===========

    Each of those draws normally -- one ``path.js-line`` or three bars.
    Reading the absent array through :func:`as_list`, which answers ``[]``,
    and pairing the two with ``zip`` yielded nothing, so every such trace
    announced a layer of the right type carrying no data at all (#418).
    Omitting one axis is how most quick plots are written, so this was not a
    corner.

    Symmetric rather than keyed by which axis carries the magnitudes: a
    horizontal bar puts its values on ``x`` and needs ``y`` generated, and
    naming one of them "the value axis" here would make every caller decide
    an orientation question it does not otherwise ask.

    Generated only when an array is missing entirely. A short one is left
    short, because plotly pairs the two positionally and draws only as far
    as the shorter reaches -- truncating is its behaviour, not an error to
    repair here.

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    tuple of (list, list)
        The ``x`` and ``y`` arrays, in that order.
    """
    xs = as_list(trace.get("x"))
    ys = as_list(trace.get("y"))
    # Absent, not merely empty. Plotly draws the two cases differently and
    # measurably: with `y` absent it generates `0, 1, 2` and draws normally,
    # while `y: []` comes back as one null point and draws nothing at all.
    # `as_list` answers `[]` for both, so the raw key is the only thing that
    # tells them apart -- and reading it wrongly would invent points for a
    # trace plotly leaves blank.
    if trace.get("y") is None:
        return xs, list(range(len(xs)))
    if trace.get("x") is None:
        return list(range(len(ys))), ys
    return xs, ys


def draws_marks(trace: dict) -> bool:
    """Whether this trace puts any geometry in its layer.

    The empty sibling of :func:`~maidr.plotly.plotly_plot.is_drawn`, which
    answers the same question for a *hidden* trace. Both end the same way:
    plotly renders no group for it, so every trace after it shifts up one in
    the layer and a selector numbered by declaration lands on the wrong
    element or on none (#412, and #400 for the hidden case).

    Measured in Chromium -- three line traces with an empty one in the middle
    produce two ``.trace.scatter`` nodes, and ``nth-child(2)`` resolves to
    the *third* trace.

    Asked through ``paired_axes`` so it agrees with the extraction: a trace
    that omits one axis is drawn, because plotly generates the missing array
    for it, and only a trace with nothing left after pairing is absent from
    the layer.

    Parameters
    ----------
    trace : dict
        A plotly trace dictionary.

    Returns
    -------
    bool
        True when plotly gives this trace a group of its own.
    """
    xs, ys = paired_axes(trace)
    return bool(xs) and bool(ys)


def subplot_block(trace: dict, key: str, default: str | None = None) -> str:
    """Return the layout key naming this trace's subplot *block*.

    Some traces are placed by neither an axis pair nor a ``domain`` of their
    own, but by a rectangle plotly writes under a named block --
    ``layout.polar``, ``layout.polar2``, ``layout.geo`` -- which the trace
    addresses by name. That name is what tells two of them in one grid apart,
    and for a polar trace it is also the class plotly gives its ``<g>``.

    The field and the default are separate because they do not always agree:
    a polar trace names its block under ``subplot`` and defaults to
    ``"polar"``, while a choropleth names its under ``geo`` and defaults to
    the same word.

    Parameters
    ----------
    trace : dict
        One trace of the figure.
    key : str
        The trace field naming its block.
    default : str, optional
        The block a trace naming none belongs to. Defaults to ``key``.

    Returns
    -------
    str
        The block name.
    """
    return str(trace.get(key) or default or key)
