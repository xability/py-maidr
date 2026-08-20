"""`Axes.broken_barh` is matplotlib's gantt chart, and it was read as nothing.

One call draws one lane: the `yrange` places it and each `(start, width)` in
`xranges` is an interval in that lane. So the shape the trace wants -- a lane
and the two ends of every interval in it -- is what the caller already wrote,
and the `PolyCollection`'s vertices give it back exactly.

Two things needed deciding rather than assuming, and both were measured.

**A chart is several calls, and it is still one chart.** Registering each call
as its own layer would hand a reader two one-lane charts to switch between
instead of one chart to move up and down inside -- and `points` is nested by
lane precisely so a single layer holds them all.

**A lane's name is not its position.** The chart matplotlib's own documentation
shows names its lanes *after* drawing them::

    ax.broken_barh([(110, 30), (150, 10)], (10, 9))
    ax.broken_barh([(10, 50), (100, 20)], (20, 9))
    ax.set_yticks([15, 25], labels=["Bill", "Jim"])

Extraction runs when the schema is first asked for, so ticks set afterwards are
in place by then. But the tick does not sit at the bar's centre: those bars span
10-19 and 20-29, so their centres are 14.5 and 24.5 while the ticks are at 15
and 25. The tick that names a lane is the one *inside* it.

And only an explicit tick counts. Left alone, matplotlib puts several inside
every bar -- measured, an unlabelled version of the chart above offers "8",
"10", "12", "14" and "16" for the lane spanning 10 to 19, none of which is that
lane's name. `set_yticks` installs a `FixedLocator`; automatic ticks are an
`AutoLocator`, and that is the difference between a name and an axis.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _schedule(named: bool = True):
    """The chart from matplotlib's own `broken_barh` documentation."""
    fig, ax = plt.subplots()
    ax.broken_barh([(110, 30), (150, 10)], (10, 9))
    ax.broken_barh([(10, 50), (100, 20), (130, 10)], (20, 9))
    if named:
        ax.set_yticks([15, 25], labels=["Bill", "Jim"])
    return fig, ax


def _layer(fig):
    """The one layer a figure emits, as its rendered schema."""
    plots = FigureManager.get_maidr(fig).plots
    assert len(plots) == 1
    return plots[0].schema


def _spans(schema) -> list[list[tuple]]:
    """The intervals a layer announces, nested by lane."""
    return [
        [(point["x"], point["start"], point["end"]) for point in lane]
        for lane in schema["data"]["points"]
    ]


def test_a_schedule_is_read_as_a_gantt() -> None:
    """The numbers, straight off the drawn polygons.

    A bar written `(110, 30)` is 110 to 140. Nothing is inverted through a
    scale and nothing is rounded, because the vertices are the corners.
    """
    fig, _ = _schedule()
    schema = _layer(fig)

    assert schema["type"] == PlotType.GANTT
    assert _spans(schema) == [
        [("Bill", 110.0, 140.0), ("Bill", 150.0, 160.0)],
        [("Jim", 10.0, 60.0), ("Jim", 100.0, 120.0), ("Jim", 130.0, 140.0)],
    ]


def test_two_calls_are_two_lanes_of_one_chart() -> None:
    """Not two charts.

    `GanttData.points` is nested by lane so that one layer holds the whole
    schedule; a layer per call would make the up and down arrows -- which are
    how a reader moves between lanes -- move between charts instead.
    """
    fig, _ = _schedule()
    schema = _layer(fig)

    assert schema["data"]["lanes"] == ["Bill", "Jim"]
    assert len(schema["data"]["points"]) == 2


def test_a_lane_is_named_by_the_tick_inside_it() -> None:
    """The tick at 15 names the lane spanning 10 to 19, whose centre is 14.5.

    An exact match against the centre finds nothing, which is why this is not
    written that way.
    """
    fig, _ = _schedule()

    assert _layer(fig)["data"]["lanes"] == ["Bill", "Jim"]


def test_an_unlabelled_lane_is_named_by_its_position() -> None:
    """The control, and the reason the locator is consulted at all.

    With no `set_yticks` the axis carries an `AutoLocator`, and several of its
    ticks fall inside every bar. Taking one would announce a lane called "12"
    or "14" depending on which was reached first; the centre is always true.
    """
    fig, _ = _schedule(named=False)

    assert _layer(fig)["data"]["lanes"] == [14.5, 24.5]


def test_a_single_automatic_tick_is_still_not_a_name() -> None:
    """Why the locator is asked as well as the count.

    "Exactly one tick inside" is not enough on its own. Widen the axis and an
    `AutoLocator` puts exactly one of its ticks inside the bar -- measured, a
    bar spanning 10 to 14 under `ylim=(0, 50)` has the single tick "10" in it.
    Taken as a name the lane would be called "10", which is the axis reading
    itself out, not anything the author said about this lane.

    `set_yticks` installs a `FixedLocator`; matplotlib's own choice is an
    `AutoLocator`, and that is the difference between a name and a coordinate.
    """
    fig, ax = plt.subplots()
    ax.broken_barh([(1, 3)], (10, 4))
    ax.broken_barh([(6, 2)], (20, 4))
    ax.set_ylim(0, 50)

    assert _layer(fig)["data"]["lanes"] == [12.0, 22.0]


def test_two_labelled_ticks_in_one_lane_name_neither() -> None:
    """Why "exactly one" rather than "the first".

    A lane holding two labelled ticks has no single one that names it, and
    taking whichever came first would announce a name chosen by tick order
    rather than by the author. The position is always true.
    """
    fig, ax = plt.subplots()
    ax.broken_barh([(1, 3)], (10, 20))
    ax.broken_barh([(6, 2)], (40, 4))
    ax.set_yticks([12, 25, 42], labels=["early", "late", "other"])

    assert _layer(fig)["data"]["lanes"] == [20.0, "other"]


def test_each_lane_gets_a_selector_of_its_own() -> None:
    """One per lane, in the order the lanes are announced.

    Each call leaves its own `PolyCollection`, so a lane is a group in the SVG
    and there is a real element to highlight -- unlike a chart drawn as one
    grob, where the values read and nothing lights up.
    """
    fig, _ = _schedule()
    schema = _layer(fig)

    assert len(schema["selectors"]) == len(schema["data"]["points"])
    assert all("path" in selector for selector in schema["selectors"])


def test_the_lane_decision_is_made_under_the_lock(monkeypatch) -> None:
    """The check-then-act, pinned at the invariant rather than by racing it.

    Deciding whether a lane already exists and then creating one is two steps.
    Unserialised, two threads drawing onto the same fresh axes can both find
    none and each call `create_maidr`, and the schedule splits into two
    one-lane charts -- silently, and only sometimes.

    Racing it does not make a test: eight threads through `broken_barh` pass
    just as readily without the lock as with it, because the window is a few
    bytecodes wide and the GIL rarely lands inside it. What can be asserted
    exactly is the invariant the lock exists for -- that the decision is taken
    while it is held -- so that is what this checks. Remove the `with` and it
    records False.

    `FigureManager._lock` cannot be borrowed for this: it is a plain `Lock`,
    and `create_maidr` takes it, so holding it across the decision would
    deadlock rather than race.
    """
    from maidr.patch import gantt as patch

    held: list[bool] = []
    original = patch._lane_of

    def spy(ax):
        held.append(patch._lanes.locked())
        return original(ax)

    monkeypatch.setattr(patch, "_lane_of", spy)

    _, ax = plt.subplots()
    ax.broken_barh([(1, 3)], (10, 4))
    ax.broken_barh([(6, 2)], (20, 4))

    assert held == [True, True]


def test_a_gantt_beside_another_chart_leaves_it_alone() -> None:
    """The neighbour test.

    A schedule drawn over something else must add a layer rather than replace
    or absorb one -- and the lane lookup must not mistake another axes' gantt
    for this one's.
    """
    fig, (left, right) = plt.subplots(1, 2)
    left.bar(["a", "b"], [1.0, 2.0])
    right.broken_barh([(1, 3)], (10, 4))
    right.broken_barh([(6, 2)], (20, 4))

    types = [plot.type for plot in FigureManager.get_maidr(fig).plots]

    assert types == [PlotType.BAR, PlotType.GANTT]
