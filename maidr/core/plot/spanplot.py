from __future__ import annotations

import uuid

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection

from maidr.core.enum import MaidrKey
from maidr.core.plot.gantt import GanttPlot
from maidr.exception import ExtractionError

#: Key the patch passes the ``LineCollection`` its own call drew under.
DRAWN_SPANS = "_maidr_spans"

#: Key saying which way the spans run: ``True`` for ``hlines``.
SPANS_ALONG_X = "_maidr_spans_along_x"

#: How far apart a segment's two lane coordinates may be and still count as
#: level. Absolute, and deliberately left that way: the scale this wants is
#: the *magnitude* of the coordinates, where float spacing lives, and the
#: only scale available here is the spread of the lanes, which is a
#: different quantity -- three lanes a second apart at epoch scale spread by
#: 2 while their float spacing is nearer 2e-7. So a relative version built
#: from what this function knows would not answer the question it looks like
#: it answers. Unresolved rather than solved; it costs nothing today because
#: `hlines` and `vlines` give both ends of a segment the *same* float, so
#: the comparison is exactly zero and any tolerance passes. It would matter
#: only for a hand-built `LineCollection` at large magnitude.
_LEVEL_TOLERANCE = 1e-9

#: How close two of a chart's ends must be to count as the same end, as a
#: fraction of the extent the chart covers along the axis the intervals run
#: on. Relative because the question is about the chart's own scale, and
#: because the shared coordinate is often zero, which has no magnitude to be
#: relative to.
#:
#: Exact equality was not enough. `hlines` and `vlines` hand back the
#: caller's own floats untouched, so a literal baseline is bit-identical
#: across segments -- but a *computed* one need not be. Measured:
#: ``tops * 0.1 - tops / 10`` is elementwise zero in arithmetic and
#: ``[5.55e-17, 0.0, 0.0, 0.0]`` in floats, so four lollipop stems stopped
#: sharing a baseline and were read as a schedule announcing "0 to 8" for a
#: chart that means "8".
_SHARED_END_TOLERANCE = 1e-9


def _same_within(values: list, extent: float) -> bool:
    """
    Whether every value is the same coordinate, to the chart's own scale.

    Parameters
    ----------
    values : list of float
        The coordinates to compare.
    extent : float
        How far the chart reaches on the axis these lie on. Zero collapses
        the test to exact equality, which is the right answer when there is
        no scale to be relative to.

    Returns
    -------
    bool
        True when the values differ by no more than the tolerance.
    """
    return max(values) - min(values) <= abs(extent) * _SHARED_END_TOLERANCE


def read_spans(collection, along_x: bool) -> list | None:
    """
    Each segment as ``(lane, start, end)``, or ``None`` when this is not a
    set of spans.

    Parameters
    ----------
    collection : LineCollection or None
        The artist the call drew.
    along_x : bool
        True when the intervals run along x, as ``hlines`` draws them.

    Returns
    -------
    list of tuple or None
        One entry per segment, in draw order.
    """
    if not isinstance(collection, LineCollection):
        return None

    lane_axis = 1 if along_x else 0
    span_axis = 1 - lane_axis

    spans: list[tuple[float, float, float]] = []
    for segment in collection.get_segments():
        ends = np.asarray(segment, dtype=float)
        if ends.shape != (2, 2) or not np.all(np.isfinite(ends)):
            return None
        lane, other = ends[0][lane_axis], ends[1][lane_axis]
        if abs(lane - other) > _LEVEL_TOLERANCE:
            # Not level on its lane axis, so it is not an interval in one.
            return None
        spans.append((lane, ends[0][span_axis], ends[1][span_axis]))

    return spans or None


def states_an_interval(spans: list) -> bool:
    """
    Whether the spans measure something, rather than sharing a baseline.

    Parameters
    ----------
    spans : list of tuple
        Each segment as ``(lane, start, end)``.

    Returns
    -------
    bool
        True when neither end is the same on every segment.

    Notes
    -----
    This declines when *either* end is shared, not only when both are, and
    that costs one real schedule: several tasks that all begin on the same
    day, ``hlines([1, 2, 3], [0, 0, 0], [5, 7, 6])``, is turned away. The
    reason is that nothing in the geometry separates it from a lollipop's
    stems, which are also "one shared start, differing ends" and which read
    as spans announce "0 to 8" for a chart that means "8". One of the two has
    to lose, and announcing a measurement the chart does not make is the worse
    outcome -- so the shared-start schedule falls back to a static image,
    which is at least a picture.

    Recorded here as well as in :class:`SpanPlot`'s docstring because a reader
    who arrives at this function alone would otherwise see only a rule that
    looks stricter than it needs to be, and relax it. ``test_spanplot.py``
    pins the declined case for the same reason.
    """
    starts = [start for _, start, _ in spans]
    ends = [end for _, _, end in spans]
    # Judged against how far the chart reaches along the axis the intervals
    # run on. Exact equality would let a baseline the caller *computed* slip
    # through as "not shared" and turn a lollipop into a schedule; measured
    # on `vlines(x, tops * 0.1 - tops / 10, tops)`, which is zero in
    # arithmetic, `[5.55e-17, 0.0, 0.0, 0.0]` in floats, and read as a gantt
    # announcing "0 to 8" for a chart that means "8".
    extent = max(max(starts), max(ends)) - min(min(starts), min(ends))
    return not _same_within(starts, extent) and not _same_within(ends, extent)


def draws_a_schedule(collection, along_x: bool) -> bool:
    """
    Whether a call's collection is a set of measured intervals.

    Asked by the patch **before** the layer is registered, not by the layer
    when it is read. A layer that refuses at extraction takes the whole
    figure with it -- which is the defect #564 was about -- so a `vlines`
    that draws a lollipop's stems must register nothing at all, exactly as
    it did before this reading existed.

    Parameters
    ----------
    collection : LineCollection or None
        The artist the call drew.
    along_x : bool
        True when the intervals run along x.

    Returns
    -------
    bool
        True when the call drew a schedule.
    """
    spans = read_spans(collection, along_x)
    return spans is not None and states_an_interval(spans)


class SpanPlot(GanttPlot):
    """
    A schedule of intervals drawn by ``Axes.hlines`` or ``Axes.vlines``.

    The same chart ``broken_barh`` draws and the same layer it emits, from a
    call shaped the other way round: **one call draws every lane**, and hands
    back a single ``LineCollection`` whose ``get_segments()`` gives both ends
    of every segment exactly -- nothing inverted, nothing rounded, since a
    collection stores its ends rather than serialising a path.

    Measured on matplotlib 3.9.4::

        ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])
        [[0, 1], [5, 1]]   [[2, 2], [7, 2]]   [[4, 3], [6, 3]]

    Three lanes at 1, 2 and 3, running 0-5, 2-7 and 4-6.

    What is not a schedule
    ----------------------
    Three other charts wear these two calls, and the rule that separates them
    is the one xability/maidr#1100 settled for Observable's `rule` mark and
    #1122 for Vega-Lite's:

        if every line shares an end, that end is the frame or the baseline
        rather than anything measured, and the mark is handed back

    - ``vlines(x, 0, y)`` is a lollipop's stems: every segment starts at the
      baseline, and read as spans they announce "0 to 8" where the chart
      means "8" -- which the markers drawn at their tips already say.
    - ``hlines(y, 0, 5)`` is a set of reference lines drawn across the frame:
      every segment is the same interval, which no row of the data states.
    - A call holding one segment cannot be told from either, since a single
      end trivially agrees with itself. That is the cost the same rule pays
      on the other two adapters, and it is paid here for the same reason.

    A segment that is not level on its lane axis is not a span at all --
    ``hlines`` and ``vlines`` cannot draw one, but a caller may hand the
    layer a collection that does -- and the whole layer is declined rather
    than the one segment dropped, so a chart is never announced as a subset
    of itself.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        spans = kwargs.pop(DRAWN_SPANS, None)
        self._spans = spans if isinstance(spans, LineCollection) else None
        # `hlines` lays its intervals along x and its lanes down y, which is
        # what `GanttTrace` calls horizontal and what `broken_barh` draws.
        self._along_x = bool(kwargs.pop(SPANS_ALONG_X, True))
        super().__init__(ax, collections=[])

    def _extract_plot_data(self) -> dict:
        """
        Read the collection as intervals nested by the lane they sit in.

        Returns
        -------
        dict
            ``{"points": [[{"x", "start", "end"}, ...], ...], "lanes": [...]}``
            -- the same payload ``broken_barh`` produces.

        Raises
        ------
        ExtractionError
            When the call drew nothing this class can read as a schedule.
        """
        spans = read_spans(self._spans, self._along_x)
        if spans is None or not states_an_interval(spans):
            raise ExtractionError(self.type, self.ax)

        axis = self.ax.get_yaxis() if self._along_x else self.ax.get_xaxis()

        # Lanes in first-seen order, which is the order the segments were
        # drawn in and therefore the order the elements sit in the SVG.
        order: list[float] = []
        grouped: dict[float, list[tuple[float, float]]] = {}
        for lane, start, end in spans:
            if lane not in grouped:
                order.append(lane)
                grouped[lane] = []
            grouped[lane].append((start, end))

        lanes = [self._lane_name(lane, lane, axis) for lane in order]
        points = [
            [
                {MaidrKey.X: name, MaidrKey.START: start, MaidrKey.END: end}
                for start, end in grouped[lane]
            ]
            for lane, name in zip(order, lanes)
        ]

        if self._spans.get_gid() is None:
            self._spans.set_gid(f"maidr-{uuid.uuid4()}")

        self._elements.clear()
        self._elements.append(self._spans)

        self._contiguous = all(
            [lane for lane, _, _ in spans].count(lane) == len(grouped[lane])
            and self._runs_together(spans, lane)
            for lane in order
        )

        return {MaidrKey.POINTS: points, MaidrKey.LANES: lanes}

    @staticmethod
    def _runs_together(spans: list[tuple[float, float, float]], lane: float) -> bool:
        """
        Whether one lane's segments were drawn without another lane between.

        Parameters
        ----------
        spans : list of tuple
            Each segment as ``(lane, start, end)``, in draw order.
        lane : float
            The lane to check.

        Returns
        -------
        bool
            True when the lane's segments occupy consecutive draw positions.
        """
        at = [index for index, (drawn, _, _) in enumerate(spans) if drawn == lane]
        return at == list(range(at[0], at[0] + len(at)))

    def _get_selector(self) -> list[str]:
        """
        Return one selector addressing every drawn segment, in draw order.

        ``GanttTrace`` takes a flat element list and slices it into lanes by
        their lengths, so one selector over the whole collection is what this
        chart needs -- there is one collection, not one per lane.

        Withheld when a lane's segments are not consecutive in draw order.
        The count would still match, so the core would not withdraw them
        itself, and the slicing would then hand a lane somebody else's
        segments: ``hlines([1, 2, 1], ...)`` draws lane 1 twice with lane 2
        in between. Leaving the layer unhighlighted is what a schedule
        already does when its lanes do not follow row order.

        Returns
        -------
        list of str
            The selector, or empty when the order cannot be trusted.
        """
        if self._spans is None or self._spans.get_gid() is None:
            return []
        if not getattr(self, "_contiguous", False):
            return []
        return [f"g[id='{self._spans.get_gid()}'] > path"]
