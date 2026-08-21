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


def test_broken_barh_still_reads_as_it_did():
    # The other call that draws this chart, and the one `GanttPlot` is shaped
    # for. Both emit the same layer; only the artist they hand over differs.
    fig, ax = plt.subplots()
    ax.broken_barh([(0, 3), (5, 1)], (10, 9))
    ax.broken_barh([(3, 5)], (20, 9))

    schema = _rendered(fig)
    assert schema["type"] == "gantt"
    assert _spans(schema) == [[(0.0, 3.0), (5.0, 6.0)], [(3.0, 8.0)]]
