"""
``ax.hlines`` and ``ax.vlines`` drew a schedule and registered nothing (#568).

Both draw one segment per row and hand back a single ``LineCollection``
whose ``get_segments()`` gives both ends exactly -- a collection stores its
ends rather than serialising a path, so there is nothing to invert and
nothing to round. Measured on matplotlib 3.9.4::

    ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])
    [[0, 1], [5, 1]]   [[2, 2], [7, 2]]   [[4, 3], [6, 3]]

Three lanes at 1, 2 and 3 running 0-5, 2-7 and 4-6: the same chart
``broken_barh`` draws and the same layer it emits, from a call shaped the
other way round -- **one call draws every lane**.

What is *not* a schedule is decided by the rule xability/maidr#1100 settled
for Observable's `rule` mark and #1122 for Vega-Lite's: if every segment
shares an end, that end is the frame or the baseline rather than anything
measured. A lollipop's stems all start at zero; reference lines all span the
same interval; and a single segment cannot be told from either, since one
end trivially agrees with itself.

The decision is made in the **patch**, before anything registers. A layer
that refuses at extraction takes the whole figure with it, which is the
defect #564 was about -- so a declined call registers nothing at all and the
rest of the figure reads as it always did.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

import maidr
from maidr.core.figure_manager import FigureManager
from maidr.exception import UnsupportedPlotError


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _layers(fig) -> list:
    try:
        return [plot.type.value for plot in FigureManager.get_maidr(fig).plots]
    except UnsupportedPlotError:
        return []


def _schema(fig) -> dict:
    plots = FigureManager.get_maidr(fig).plots
    assert len(plots) == 1
    return plots[0].schema


def _rendered(fig) -> dict:
    maidr.render(fig)._repr_html_()
    return _schema(fig)


def _spans(schema) -> list:
    return [
        [(point["start"], point["end"]) for point in lane]
        for lane in schema["data"]["points"]
    ]


def test_horizontal_lines_read_as_the_schedule_they_draw():
    fig, ax = plt.subplots()
    ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])

    schema = _rendered(fig)
    assert schema["type"] == "gantt"
    assert schema["data"]["lanes"] == [1.0, 2.0, 3.0]
    assert _spans(schema) == [[(0.0, 5.0)], [(2.0, 7.0)], [(4.0, 6.0)]]


def test_vertical_lines_read_the_same_way_with_the_axes_exchanged():
    # The lanes run along x and the intervals down y. `GanttTrace` navigates
    # lanes and intervals rather than x and y, so the two need no orientation
    # to tell them apart -- only which axis the lanes were laid out on.
    fig, ax = plt.subplots()
    ax.vlines([1, 2, 3], [0, 2, 4], [5, 7, 6])

    schema = _rendered(fig)
    assert schema["type"] == "gantt"
    assert schema["data"]["lanes"] == [1.0, 2.0, 3.0]
    assert _spans(schema) == [[(0.0, 5.0)], [(2.0, 7.0)], [(4.0, 6.0)]]


def test_a_lane_is_named_by_the_tick_the_author_put_inside_it():
    fig, ax = plt.subplots()
    ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])
    ax.set_yticks([1, 2, 3], labels=["design", "build", "ship"])

    schema = _rendered(fig)
    assert schema["data"]["lanes"] == ["design", "build", "ship"]
    assert [point["x"] for lane in schema["data"]["points"] for point in lane] == [
        "design",
        "build",
        "ship",
    ]


def test_an_unlabelled_lane_keeps_its_position():
    # Left alone, matplotlib picks the ticks and several land on a lane --
    # none of which is its name. The position is always true.
    fig, ax = plt.subplots()
    ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])

    assert _rendered(fig)["data"]["lanes"] == [1.0, 2.0, 3.0]


def test_a_lollipops_stems_register_nothing():
    # Every segment starts at the baseline. Read as spans they announce
    # "0 to 8" where the chart means "8", and the markers at their tips
    # already carry that.
    fig, ax = plt.subplots()
    ax.vlines([1, 2, 3], 0, [5, 7, 6])

    assert _layers(fig) == []
    assert len(maidr.render(fig)._repr_html_()) > 0


def test_reference_lines_register_nothing():
    # Every segment is the same interval, which no row of the data states.
    fig, ax = plt.subplots()
    ax.hlines([1, 2, 3], 0, 5)

    assert _layers(fig) == []


def test_a_single_span_registers_nothing():
    # One segment cannot be told from either of the two above: a single end
    # trivially agrees with itself. The same cost the rule pays on the other
    # two adapters, paid here for the same reason.
    fig, ax = plt.subplots()
    ax.hlines([1], [0], [5])

    assert _layers(fig) == []


def test_a_chart_beside_a_lollipop_is_untouched():
    # What deciding in the patch buys: a declined call registers nothing, so
    # it cannot refuse at extraction and take the figure with it.
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    ax.vlines([0, 1], 0, [1, 2])

    assert _layers(fig) == ["bar"]
    assert len(maidr.render(fig)._repr_html_()) > 0


def test_the_spans_are_highlighted_through_the_collection_that_drew_them():
    # One selector over the whole collection, not one per lane: there is one
    # artist, and `GanttTrace` slices a flat element list into lanes by their
    # lengths.
    fig, ax = plt.subplots()
    ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])

    selectors = _rendered(fig)["selectors"]
    assert len(selectors) == 1
    assert selectors[0].endswith("> path")
    assert "maidr-" in selectors[0]


def test_a_lane_drawn_twice_out_of_order_is_left_unhighlighted():
    # `hlines([1, 2, 1], ...)` draws lane 1, then lane 2, then lane 1 again.
    # The element count still matches, so the core would not withdraw the
    # selectors itself -- it slices the flat list by lane length and would
    # hand lane 1's second interval to lane 2. Withheld rather than wrong.
    fig, ax = plt.subplots()
    ax.hlines([1, 2, 1], [0, 2, 6], [5, 7, 9])

    schema = _rendered(fig)
    assert schema["data"]["lanes"] == [1.0, 2.0]
    assert _spans(schema) == [[(0.0, 5.0), (6.0, 9.0)], [(2.0, 7.0)]]
    assert schema["selectors"] == []


def test_a_lane_drawn_twice_in_a_row_keeps_its_highlighting():
    # Consecutive, so the flat order and the lane order agree. This is what
    # makes the test above a check on the ordering rather than on repeats.
    fig, ax = plt.subplots()
    ax.hlines([1, 1, 2], [0, 6, 2], [5, 9, 7])

    schema = _rendered(fig)
    assert _spans(schema) == [[(0.0, 5.0), (6.0, 9.0)], [(2.0, 7.0)]]
    assert len(schema["selectors"]) == 1


@pytest.mark.parametrize("draw", ["acorr", "xcorr"])
def test_a_correlogram_is_not_claimed_by_the_span_reading(draw):
    # These draw through `vlines`, so without a patch of their own they
    # inherit whatever their segments say -- and every one of them runs from
    # the baseline to the correlation, which is the lollipop shape rather
    # than a schedule of intervals. They are read as `lollipop` by their own
    # patch now (#577); pinned here so the span patch cannot start claiming
    # them and announcing "0 to 0.6" where the chart means "0.6".
    import numpy as np

    # Long enough for the default `maxlags=10`, and deterministic.
    first = np.sin(np.arange(40, dtype=float))
    fig, ax = plt.subplots()
    if draw == "acorr":
        ax.acorr(first)
    else:
        ax.xcorr(first, first[::-1])

    assert _layers(fig) == ["lollipop"]
    assert len(maidr.render(fig)._repr_html_()) > 0


def test_broken_barh_still_reads_as_it_did():
    # The other call that draws this chart, and the one `GanttPlot` is shaped
    # for. Both emit the same layer; only the artist they hand over differs.
    fig, ax = plt.subplots()
    ax.broken_barh([(0, 3), (5, 1)], (10, 9))
    ax.broken_barh([(3, 5)], (20, 9))

    schema = _rendered(fig)
    assert schema["type"] == "gantt"
    assert _spans(schema) == [[(0.0, 3.0), (5.0, 6.0)], [(3.0, 8.0)]]


def _all_schemas(fig) -> list:
    maidr.render(fig)._repr_html_()
    return [plot.schema for plot in FigureManager.get_maidr(fig).plots]


@pytest.mark.parametrize("spans_first", [True, False])
def test_a_broken_barh_beside_an_hlines_keeps_its_own_lane(spans_first):
    # `gantt._lane_of` used to match on `isinstance(plot, GanttPlot)`, and
    # `SpanPlot` subclasses `GanttPlot`. So a `broken_barh` following an
    # `hlines` on the same axes appended its `PolyCollection` to the span
    # layer, which reads its lanes from the segments it was handed and never
    # looks at `_collections`: the lane was drawn, accepted without error,
    # and announced nowhere. Measured as three lanes read for the four drawn.
    #
    # Parametrised over the drawing order because only one of the two was
    # ever broken -- the reverse order registered two layers all along -- and
    # a fix that made them agree by breaking the other would pass a
    # single-order test.
    fig, ax = plt.subplots()
    if spans_first:
        ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])
        ax.broken_barh([(0, 3)], (10, 9))
    else:
        ax.broken_barh([(0, 3)], (10, 9))
        ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])

    schemas = _all_schemas(fig)
    assert len(schemas) == 2

    lanes = [schema["data"]["lanes"] for schema in schemas]
    assert sorted(len(lane) for lane in lanes) == [1, 3]
    # Every drawn interval is announced by one layer or the other.
    drawn = sorted(
        (point["start"], point["end"])
        for schema in schemas
        for lane in schema["data"]["points"]
        for point in lane
    )
    assert drawn == [(0.0, 3.0), (0.0, 5.0), (2.0, 7.0), (4.0, 6.0)]


def test_two_broken_barh_calls_still_merge_into_one_chart():
    # The reason `_lane_of` exists, and the behaviour the fix above must not
    # cost: `broken_barh` draws *one* lane per call, so a two-lane schedule
    # is two calls that have to become one layer. Asserted beside the mixed
    # case so narrowing the lookup any further would fail here.
    fig, ax = plt.subplots()
    ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])
    ax.broken_barh([(0, 3)], (10, 9))
    ax.broken_barh([(2, 4)], (20, 9))

    schemas = _all_schemas(fig)
    assert len(schemas) == 2
    assert sorted(len(schema["data"]["lanes"]) for schema in schemas) == [2, 3]


def test_two_hlines_calls_stay_two_charts():
    # The deliberate asymmetry with `broken_barh`, pinned so it reads as a
    # decision rather than an oversight. One `hlines` call already draws a
    # whole schedule, so merging a second in would join two complete charts
    # into one neither call made.
    fig, ax = plt.subplots()
    ax.hlines([1, 2], [0, 2], [5, 7])
    ax.hlines([4, 5], [1, 3], [6, 8])

    schemas = _all_schemas(fig)
    assert len(schemas) == 2
    assert [schema["data"]["lanes"] for schema in schemas] == [
        [1.0, 2.0],
        [4.0, 5.0],
    ]


def test_a_schedule_whose_tasks_share_a_start_is_declined():
    # The cost of the shared-end rule, stated rather than left to be found.
    # These are three real tasks all beginning on day 0, and nothing in the
    # geometry separates them from a lollipop's stems -- which are also one
    # shared start and differing ends, and which read as spans would announce
    # "0 to 8" for a chart that means "8". Declining is the side that never
    # announces a measurement the chart does not make.
    fig, ax = plt.subplots()
    ax.hlines([1, 2, 3], [0, 0, 0], [5, 7, 6])

    assert _layers(fig) == []
    assert len(maidr.render(fig)._repr_html_()) > 0


def test_an_hlines_and_a_vlines_share_an_axes_and_keep_their_own_lane_axis():
    # `patch/spanplot.py` claims exactly this, and until now nothing checked
    # it. The substantive half is not that two layers appear -- it is that
    # each names its lanes off the axis *it* laid them out on, since the two
    # calls run in opposite directions and `SpanPlot` is told which by
    # `SPANS_ALONG_X` alone. Given different tick labels on x and y, a layer
    # reading the wrong axis would come back with the other one's names, or
    # with bare numbers when the position matched no tick.
    fig, ax = plt.subplots()
    ax.set_yticks([1, 2, 3], labels=["alpha", "beta", "gamma"])
    ax.set_xticks([10, 20], labels=["left", "right"])
    ax.hlines([1, 2, 3], [0, 2, 4], [5, 7, 6])
    ax.vlines([10, 20], [0, 1], [4, 9])

    schemas = _all_schemas(fig)
    assert [schema["data"]["lanes"] for schema in schemas] == [
        ["alpha", "beta", "gamma"],
        ["left", "right"],
    ]


def test_one_unreadable_segment_declines_the_whole_call():
    # The asymmetry with `GanttPlot._corners`, which drops a bad path and
    # keeps the rest of its lane. `read_spans` returns None for the call
    # instead, so a chart is never announced as a subset of itself -- a
    # reader given two of three tasks has no way to know a third existed.
    # Documented on the class; pinned here so the trade-off enforces itself.
    import numpy as np

    fig, ax = plt.subplots()
    ax.hlines([1, 2, 3], [0, 2, np.nan], [5, 7, 6])

    assert _layers(fig) == []
    # And the figure still renders, as a picture rather than nothing.
    assert len(maidr.render(fig)._repr_html_()) > 0


def test_a_computed_baseline_is_still_a_lollipop():
    # Review asked whether float noise could dodge the decline, and it could.
    # `tops * 0.1 - tops / 10` is elementwise zero in arithmetic and
    # `[5.55e-17, 0.0, 0.0, 0.0]` in floats, so an exact comparison saw four
    # stems that no longer shared a baseline and read them as a schedule --
    # announcing "0 to 8" for a chart that means "8". The comparison is now
    # made against the chart's own extent instead.
    import numpy as np

    tops = np.array([3.0, 8.0, 5.0, 9.0])
    baseline = tops * 0.1 - tops / 10.0
    assert len(set(baseline.tolist())) > 1, "fixture must actually be noisy"

    fig, ax = plt.subplots()
    ax.vlines([1, 2, 3, 4], baseline, tops)

    assert _layers(fig) == []


def test_a_schedule_laid_out_in_epoch_seconds_still_reads():
    # The shared-end tolerance is a fraction of the chart's extent, so it
    # had to be checked that scaling it up does not make a real schedule's
    # differing ends look shared. Here the extent is 700 and the tolerance
    # 7e-7, while the starts differ by 200.
    #
    # Not a test of the levelness tolerance, which stays absolute -- both
    # ends of an `hlines` segment are the *same* float, so that comparison
    # is exactly zero at any scale.
    base = 1_700_000_000.0
    fig, ax = plt.subplots()
    ax.hlines(
        [1, 2, 3],
        [base, base + 200, base + 400],
        [base + 500, base + 700, base + 600],
    )

    schema = _rendered(fig)
    assert schema["type"] == "gantt"
    assert _spans(schema) == [
        [(base, base + 500)],
        [(base + 200, base + 700)],
        [(base + 400, base + 600)],
    ]


def test_a_segment_that_is_not_level_is_still_refused():
    # The tolerance became relative, not absent. A collection whose segment
    # slopes across lanes is not an interval in one, and the whole layer is
    # declined rather than the segment flattened onto a lane it never sat in.
    from matplotlib.collections import LineCollection

    from maidr.core.plot.spanplot import read_spans

    sloped = LineCollection([[[0, 1], [5, 2]], [[2, 3], [7, 3]]])
    assert read_spans(sloped, along_x=True) is None


def test_a_stem_plot_is_not_claimed_by_the_span_reading():
    # `stem` draws the lollipop shape and reaches `vlines` the same way
    # `acorr`/`xcorr` do, so review asked where it lands. It is read by its
    # own patch, as the `lollipop` its marks make (#574) -- pinned here so
    # the span patch cannot start claiming it and announcing the stems as a
    # schedule of intervals.
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3, 4], [3, 8, 5, 9])

    assert _layers(fig) == ["lollipop"]
    assert len(maidr.render(fig)._repr_html_()) > 0
