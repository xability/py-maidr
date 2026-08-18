"""Tests for seaborn point plots.

``sns.pointplot`` draws a group estimate with the interval around it, and the
reader needs the same thing from it that ``Axes.errorbar`` exists to give:
whether two group means differ is answered by whether their intervals overlap.

Reading it is a different problem, though, because seaborn draws no
``ErrorbarContainer``. It draws the estimates as one line and each interval as
another, so before this the generic ``Axes.plot`` wrapper described a
four-category chart as *five* series -- the estimates, and four interval
polylines whose cap geometry reached the reader as data. These tests are
written against that: the intervals have to arrive as bounds, and the cap
geometry has to stop arriving at all.

The assertions are on drawn geometry rather than on the input frame, because
the estimate seaborn computes is a bootstrap by default and reproducing its
arithmetic here would test this file against itself.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot.pointplot import PointPlot  # noqa: E402
from maidr.patch.pointplot import _group_labels  # noqa: E402


#: Three groups whose observations differ enough per group that the intervals
#: are wide, distinct, and asymmetric -- so a reading that took the wrong
#: bound cannot coincide with the right one.
FRAME = pd.DataFrame(
    {
        "group": ["a"] * 6 + ["b"] * 6 + ["c"] * 6,
        "value": [
            1.0, 2.0, 3.0, 4.0, 9.0, 11.0,
            20.0, 21.0, 22.0, 23.0, 24.0, 30.0,
            5.0, 5.5, 6.0, 6.5, 7.0, 7.5,
        ],
    }
)


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _plots(fig):
    """
    Return the MAIDR plots registered for a figure, or an empty list.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    list
        The registered plots.
    """
    maidr_instance = FigureManager.figs.get(fig)
    return list(maidr_instance._plots) if maidr_instance else []


def _schema(fig) -> dict:
    """
    Return the layer schema of a figure's only plot.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    dict
        The MAIDR layer schema.
    """
    return _plots(fig)[0].render()


def test_a_point_plot_reads_as_an_error_bar_layer():
    """
    The estimates and their intervals travel together, in one layer.

    A point plot carries the same quantity ``Axes.errorbar`` does, so it emits
    the same layer type rather than a line layer that happens to sit beside
    some intervals -- the consumer then steps through lower, value and upper at
    each group with no special case for where the chart came from.
    """
    fig, ax = plt.subplots()
    sns.pointplot(FRAME, x="group", y="value", ax=ax)

    plots = _plots(fig)

    assert len(plots) == 1
    assert isinstance(plots[0], PointPlot)
    assert plots[0].type == PlotType.ERRORBAR


def test_the_interval_polylines_do_not_travel_as_series():
    """
    The regression that motivated patching ``pointplot`` by name.

    Left to the generic ``Axes.plot`` wrapper, a three-group chart announced
    four series: the estimates, and three interval polylines. Their vertices
    are not observations -- with ``capsize`` they carry NaN separators and cap
    offsets like ``1.95`` among the category names -- so a reader arrowing
    through the chart walked cap geometry believing it was data.
    """
    fig, ax = plt.subplots()
    sns.pointplot(FRAME, x="group", y="value", capsize=0.1, ax=ax)

    data = _schema(fig)["data"]

    # One entry per group, not one per drawn artist.
    assert len(data) == 3
    assert [point["x"] for point in data] == ["a", "b", "c"]
    assert not any(np.isnan(point["y"]) for point in data)


def test_the_bounds_are_the_interval_the_chart_drew():
    """
    Each group's bounds bracket its estimate, and differ between groups.

    Asserted as relations rather than as numbers because the default estimator
    is a bootstrap: pinning literals would make this a change-detector for
    seaborn's RNG rather than a test of what was read.
    """
    fig, ax = plt.subplots()
    sns.pointplot(FRAME, x="group", y="value", ax=ax)

    data = _schema(fig)["data"]

    for point in data:
        assert point["yMin"] < point["y"] < point["yMax"]

    # Group 'c' is tightly clustered and 'a' is not, so their intervals must
    # not come out the same width -- which they would if the bounds were being
    # synthesised rather than read.
    widths = [point["yMax"] - point["yMin"] for point in data]
    assert widths[0] > widths[2]


def test_caps_do_not_move_the_bounds():
    """
    ``capsize`` changes the drawn shape, and the interval is the same.

    Without caps an interval is a two-vertex line; with them it is an
    eight-vertex NaN-separated polyline whose caps sit *at* the bounds. Reading
    the extremes along the value axis is what makes those the same answer, and
    this is the test that says so.
    """
    fig, bare = plt.subplots()
    sns.pointplot(FRAME, x="group", y="value", errorbar="sd", ax=bare)

    fig_capped, capped = plt.subplots()
    sns.pointplot(FRAME, x="group", y="value", errorbar="sd", capsize=0.3, ax=capped)

    # `sd` rather than the default bootstrap, so the two draws are comparable
    # without depending on seaborn's RNG.
    for plain, with_caps in zip(_schema(fig)["data"], _schema(fig_capped)["data"]):
        assert plain["yMin"] == pytest.approx(with_caps["yMin"])
        assert plain["yMax"] == pytest.approx(with_caps["yMax"])


def test_groups_are_named_rather_than_numbered():
    """
    Seaborn places the groups at 0, 1, 2 and writes their names on the ticks.

    Emitting the positions would announce "0" where the chart says "a", which
    is the whole content of a categorical axis.
    """
    fig, ax = plt.subplots()
    sns.pointplot(FRAME, x="group", y="value", ax=ax)

    assert [point["x"] for point in _schema(fig)["data"]] == ["a", "b", "c"]


def test_a_horizontal_point_plot_reports_horz():
    """
    The categories can run along y, and the layer says which axis they use.

    Detected from the axes seaborn set up rather than from the caller's
    ``orient``, which is usually absent. Note the data stays orientation-
    invariant -- category in ``x``, magnitude in ``y`` -- while the axis labels
    stay screen-aligned, exactly as ``ErrorBarPlot`` emits them; both halves
    are asserted here because a change to either alone would transpose the
    announcement.
    """
    fig, ax = plt.subplots()
    sns.pointplot(FRAME, y="group", x="value", ax=ax)
    ax.set_xlabel("Response")  # the magnitude, on the real x axis
    ax.set_ylabel("Group")  # the category, on the real y axis

    schema = _schema(fig)

    assert schema["orientation"] == "horz"
    assert schema["axes"]["x"]["label"] == "Response"
    assert schema["axes"]["y"]["label"] == "Group"
    assert schema["data"][0]["x"] == "a"
    assert schema["data"][0]["yMin"] < schema["data"][0]["y"]


def test_native_scale_still_finds_the_category_axis():
    """
    Under ``native_scale`` the category axis is an ordinary numeric one.

    The string-category machinery seaborn normally leaves behind is the first
    signal the orientation is read from, and this is the case where it is
    silent -- so the intervals themselves have to answer it, by spanning the
    value axis and standing on a single coordinate of the other.
    """
    numeric = FRAME.assign(group=FRAME["group"].map({"a": 1, "b": 2, "c": 3}))

    fig, ax = plt.subplots()
    sns.pointplot(numeric, x="group", y="value", native_scale=True, ax=ax)

    schema = _schema(fig)

    assert schema["orientation"] == "vert"
    # Numeric groups keep their values: the ticks under `native_scale` are
    # renderings of the coordinates rather than names, so borrowing them would
    # replace a group with whatever rounding the formatter applied.
    assert [point["x"] for point in schema["data"]] == [1.0, 2.0, 3.0]


def test_a_symmetric_interval_does_not_flip_the_orientation():
    """
    ``errorbar='sd'`` draws bounds equidistant from the estimate.

    That symmetry defeats any rule that looks for the estimate sitting at the
    centre of its interval, because it then sits at the centre along *both*
    axes. The signals actually used are unaffected by it, and this is what
    holds them to that.
    """
    fig, ax = plt.subplots()
    sns.pointplot(FRAME, y="group", x="value", errorbar="sd", ax=ax)

    assert _schema(fig)["orientation"] == "horz"


def test_a_point_plot_with_no_interval_stays_a_line():
    """
    ``errorbar=None`` draws the estimates alone.

    There is no interval to carry, and an error bar layer whose bounds are all
    absent would announce an interval the chart does not draw -- so it travels
    as the line chart it is.
    """
    fig, ax = plt.subplots()
    sns.pointplot(FRAME, x="group", y="value", errorbar=None, ax=ax)

    schema = _schema(fig)

    assert schema["type"] == PlotType.LINE.value
    assert [point["x"] for point in schema["data"][0]] == ["a", "b", "c"]


def test_a_hue_keeps_its_intervals_as_a_grouped_error_bar():
    """
    A ``hue`` splits the chart into groups, and each group keeps its bounds.

    This replaces a test that pinned the gap. The layer used to fall back to
    ``line``, dropping the intervals rather than mis-assigning them, because
    the error bar layer carried a single flat series with no field naming the
    group -- so a reader of a grouped point plot was handed the means of a
    chart drawn to show the uncertainty around them. maidr 4.4.0 gave the
    grammar a grouped shape (xability/maidr#942) and the fallback went with
    it (#462).

    What the old test pinned still holds and is still asserted: the interval
    polylines do not travel as series of their own, and each series is named
    after its hue level rather than after whichever line index it landed on.
    """
    fig, ax = plt.subplots()
    frame = FRAME.assign(half=["x", "y"] * 9)
    sns.pointplot(frame, x="group", y="value", hue="half", dodge=True, ax=ax)

    schema = _schema(fig)

    assert schema["type"] == PlotType.ERRORBAR.value
    assert len(schema["data"]) == 2
    assert {point["z"] for series in schema["data"] for point in series} == {"x", "y"}

    # The half the fallback used to lose. Every point carries a bound, and
    # each bound belongs to the estimate it is emitted beside -- checked by
    # containment rather than by position, since pairing the wrong group's
    # interval to an estimate is the failure the fallback existed to avoid.
    for series in schema["data"]:
        for point in series:
            assert point["yMin"] <= point["y"] <= point["yMax"]

    # The grouping variable is named, so the reader hears "half" rather than
    # an unlabelled third axis.
    assert schema["axes"]["z"]["label"] == "half"


def test_three_groups_each_take_their_own_intervals():
    """Slicing the interval list per group has to generalise past two.

    Seaborn draws the polylines estimate-major -- every category of the
    first group, then of the second -- so each group takes a contiguous
    slice. With two groups an off-by-one in that arithmetic still lands
    inside the list and mis-pairs silently; a third group is what makes a
    wrong stride reach the wrong bounds visibly.

    Checked by containment rather than by index, because "did this group get
    its own intervals" is the question, and the estimate falling inside the
    bounds emitted beside it is what answers it.
    """
    frame = FRAME.assign(third=["x", "y", "z"] * 6)

    fig, ax = plt.subplots()
    sns.pointplot(frame, x="group", y="value", hue="third", dodge=True, ax=ax)

    schema = _schema(fig)

    assert schema["type"] == PlotType.ERRORBAR.value
    assert len(schema["data"]) == 3
    assert [series[0]["z"] for series in schema["data"]] == ["x", "y", "z"]
    for series in schema["data"]:
        for point in series:
            assert point["yMin"] <= point["y"] <= point["yMax"]


def test_a_legend_that_does_not_name_every_group_names_none():
    """Either the whole layer is grouped-and-named or none of it is.

    Naming only the groups the legend covers would leave the layer
    declaring an ``axes.z`` while some of its series carried no ``z`` --
    a shape the consumer has no reading for. The clean fallback is an
    unlabelled grouped chart, which is what the old ``line`` path gave.

    Driven through the guards directly rather than through a contrived
    seaborn state. A legend short at *registration* time is the case this
    protects against, and replacing the legend afterwards does not produce
    it: the names are read while the call is being patched, so a later
    ``ax.legend(...)`` leaves what was captured alone. Testing the guard is
    honest; staging a chart seaborn may never draw is not.
    """
    frame = FRAME.assign(half=["x", "y"] * 9)

    fig, ax = plt.subplots()
    sns.pointplot(frame, x="group", y="value", hue="half", dodge=True, ax=ax)

    # The reader: one name per drawn group, or nothing.
    assert _group_labels(ax, 2) == ["x", "y"]
    assert _group_labels(ax, 3) == []
    assert _group_labels(ax, 1) == []

    # The emitter, handed a short list: no `z` anywhere rather than on some
    # series only, and no `axes.z` declaring one that is not there.
    plot = _plots(fig)[0]
    plot._groups = ["x"]
    plot._schema = {}

    schema = plot.render()

    assert schema["type"] == PlotType.ERRORBAR.value
    assert len(schema["data"]) == 2
    assert "z" not in schema["axes"]
    assert not any("z" in point for series in schema["data"] for point in series)
    # The bounds are the point of the layer and survive the naming failure.
    for series in schema["data"]:
        for point in series:
            assert point["yMin"] <= point["y"] <= point["yMax"]


def test_a_group_whose_every_category_is_a_singleton_keeps_its_siblings():
    """One group with no drawable interval must not cost the others theirs.

    A hue level holding a single observation everywhere has nothing to
    estimate an interval from, and seaborn renders that as a polyline whose
    value coordinates are all NaN. The layer omits that group's bounds and
    keeps the rest, rather than falling back for the whole chart.
    """
    frame = pd.DataFrame(
        {
            "g": ["a", "a", "a", "b", "b", "b"] * 2,
            "half": ["x"] * 6 + ["y"] * 6,
            "v": [1.0, 2.0, 3.0, 8.0, 9.0, 10.0, 5.0, 5.0, 5.0, 7.0, 7.0, 7.0],
        }
    )

    fig, ax = plt.subplots()
    sns.pointplot(frame, x="g", y="v", hue="half", dodge=True, ax=ax)

    schema = _schema(fig)

    assert schema["type"] == PlotType.ERRORBAR.value
    assert len(schema["data"]) == 2
    # Every point is still reported, with or without a bound.
    assert all(len(series) == 2 for series in schema["data"])
    # The group that has intervals keeps them.
    assert any(
        "yMin" in point for series in schema["data"] for point in series
    )


def test_a_dodged_group_is_still_named_by_its_tick():
    """
    ``dodge`` shifts a series aside from the tick that names it.

    The point is drawn at 0.955 rather than at 1, and looking the label up by
    exact coordinate then misses -- so a dodged chart announced "-0.025" where
    it says "a". It is the same group either way, and the reader has no other
    way to know which.
    """
    fig, ax = plt.subplots()
    frame = FRAME.assign(half=["x", "y"] * 9)
    sns.pointplot(frame, x="group", y="value", hue="half", dodge=True, ax=ax)

    for series in _schema(fig)["data"]:
        assert [point["x"] for point in series] == ["a", "b", "c"]


def test_a_numeric_axis_is_not_snapped_to_its_ticks():
    """
    The guard on the rounding above: it must fire on category axes only.

    On a numeric axis the ticks are renderings of coordinates, so rounding to
    the nearest one would rename a measurement after whichever tick it fell
    closest to -- silently reporting a value the chart never drew.

    Every coordinate here sits off a tick, since one landing on a tick is
    already answered by the exact lookup and would prove nothing about the
    rounding.
    """
    fig, ax = plt.subplots()
    ax.plot([0.4, 10.4, 20.7], [1.0, 2.0, 3.0])

    data = _schema(fig)["data"][0]

    assert [point["x"] for point in data] == [0.4, 10.4, 20.7]


def test_the_intervals_are_tagged_for_highlighting():
    """
    One drawn element per point, in the order the points are emitted.

    That is the shape the consumer repeats across its lower, value and upper
    sections, so a mismatch here shows up as the highlight landing on the wrong
    group rather than as an error.
    """
    fig, ax = plt.subplots()
    sns.pointplot(FRAME, x="group", y="value", ax=ax)

    plot = _plots(fig)[0]
    plot.render()

    assert plot._support_highlighting is True
    assert len(plot.elements) == 3


def test_an_earlier_chart_on_the_same_axes_is_left_alone():
    """
    Only the lines this call drew are its own.

    A point plot over an existing line chart would otherwise sweep that line up
    as an estimate, describing another chart's data as this one's groups.
    """
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [10.0, 11.0, 12.0])
    sns.pointplot(FRAME, x="group", y="value", ax=ax)

    plots = _plots(fig)

    # The line layer registered first, then the point plot's own.
    assert [plot.type for plot in plots] == [PlotType.LINE, PlotType.ERRORBAR]
    assert len(plots[1].render()["data"]) == 3


def test_an_unrecognised_rendering_falls_back_to_describing_the_lines():
    """
    The split between estimates and intervals is verified, not assumed.

    It is a claim about another library's rendering: seaborn draws one estimate
    line and then one short polyline per group. Should that change, the counts
    stop matching, and the layer describes the drawn lines the way the generic
    wrapper did rather than reading bounds off artists that are not intervals.
    """
    from maidr.patch.pointplot import _pairs_up

    fig, ax = plt.subplots()
    (estimate,) = ax.plot([0, 1, 2], [1.0, 2.0, 3.0], marker="o")
    # One interval short of a group each -- the shape a changed renderer would
    # produce, and the one that must not be paired up.
    intervals = [
        ax.plot([index, index], [0.0, 1.0], marker="None")[0] for index in range(2)
    ]

    assert _pairs_up([estimate], intervals) is False
    assert _pairs_up([estimate], []) is True


def test_bounds_are_not_spelled_out_to_seventeen_digits():
    """
    A bound is computed, not authored, and comes off the drawn vertex raw.

    ``mean - sd`` for these two observations is ``0.07928932188134526`` -- a
    number a screen reader reads digit by digit, and one whose tail is an
    artifact of how it was arrived at rather than a measurement. ``ErrorBarPlot``
    already cuts its own bounds to twelve significant figures; a point plot's
    bounds are the same quantity reached the same way, so they are cut the same.
    """
    pair = pd.DataFrame({"g": ["a", "a"], "v": [0.1, 0.2]})

    fig, ax = plt.subplots()
    sns.pointplot(pair, x="g", y="v", errorbar="sd", ax=ax)

    point = _schema(fig)["data"][0]

    assert point["yMin"] == 0.0792893218813
    assert point["yMax"] == 0.220710678119


def test_a_group_of_one_carries_no_interval():
    """
    A single observation has nothing to estimate an interval from.

    Seaborn still draws the polyline, with the cap positions intact and the
    value coordinates NaN. Read as an interval it hands the reader the *cap's
    own width* -- roughly 0.05 either side of the group's position -- which is
    not a measurement and is not even in the units of the value axis.

    So the chart reads as the line of estimates it is. This was found by the
    ``native_scale`` case, where seaborn groups by every distinct value and
    every group therefore has one observation.
    """
    singles = pd.DataFrame({"g": ["a", "b", "c"], "v": [1.0, 2.0, 3.0]})

    fig, ax = plt.subplots()
    sns.pointplot(singles, x="g", y="v", capsize=0.2, ax=ax)

    schema = _schema(fig)

    assert schema["type"] == PlotType.LINE.value
    assert [point["y"] for point in schema["data"][0]] == [1.0, 2.0, 3.0]


def test_nothing_recognisable_still_describes_the_lines():
    """
    The one path that used to register no layer at all.

    Every other verification failure falls back to describing what was drawn,
    which is what the generic wrapper did; dropping the chart entirely is a
    worse answer than the one it already gave. Reached here by drawing lines
    that all look like intervals, which is what a renderer that stopped marking
    its estimates would produce.
    """
    fig, ax = plt.subplots()
    for index in range(2):
        ax.plot([0, 1], [index, index + 1], marker="None")

    plots = _plots(fig)

    assert len(plots) == 1
    assert plots[0].type == PlotType.LINE


def test_a_horizontal_dodge_names_its_groups():
    """
    The categories are drawn on y here, and they are named (#353).

    This replaces a test that pinned the gap. ``-0.025`` and ``0.975`` are
    where two hue levels were shifted to make room for each other around the
    ticks the chart writes ``a`` and ``b`` on, so a reader was given the
    offsets and no way to reach the names.

    The names moved from ``y`` to ``x`` when this chart stopped falling back
    to ``line`` (#462), and that is a change of key rather than of behaviour:
    an error bar layer carries the category as ``x`` in **both** orientations
    and lets ``orientation`` say which is on screen where -- the convention
    ``ErrorBarPlot`` documents and the single-series path has always used.
    ``test_a_horizontal_chart_names_its_groups_without_a_dodge`` draws with
    ``Axes.plot`` for exactly this reason.
    """
    frame = FRAME.assign(half=["x", "y"] * 9)

    fig, ax = plt.subplots()
    sns.pointplot(frame, y="group", x="value", hue="half", dodge=True, ax=ax)

    schema = _schema(fig)

    assert schema["type"] == PlotType.ERRORBAR.value
    assert schema["orientation"] == "horz"
    named = {point["x"] for series in schema["data"] for point in series}
    assert named == set(FRAME["group"].unique())

    # The value axis is still numeric: only the axis carrying the categories
    # is named, and naming both would have made the measurement a string.
    assert all(
        isinstance(point["y"], float)
        for series in schema["data"]
        for point in series
    )


def test_a_horizontal_chart_names_its_groups_without_a_dodge():
    """
    An undodged horizontal chart sits exactly on its ticks.

    The dodged case above exercises the rounding; this one exercises the exact
    lookup, so a fix that only ever rounded would still be caught. Drawn with
    ``Axes.plot`` because an undodged ``pointplot`` emits an error bar layer,
    which reads its categories by a different route.
    """
    fig, ax = plt.subplots()
    ax.plot([4.0, 5.0, 6.0], ["a", "b", "c"])

    schema = _schema(fig)
    points = [point for series in schema["data"] for point in series]

    assert [point["y"] for point in points] == ["a", "b", "c"]
    assert [point["x"] for point in points] == [4.0, 5.0, 6.0]


def test_a_vertical_chart_still_names_its_groups():
    """
    The axis this used to follow, unchanged.

    Following the category axis rather than x must not have cost the vertical
    case anything, which is what it was doing correctly all along.
    """
    fig, ax = plt.subplots()
    ax.plot(["a", "b", "c"], [4.0, 5.0, 6.0])

    schema = _schema(fig)
    points = [point for series in schema["data"] for point in series]

    assert [point["x"] for point in points] == ["a", "b", "c"]
    assert [point["y"] for point in points] == [4.0, 5.0, 6.0]


def test_a_numeric_axis_keeps_its_numbers():
    """
    The over-correction, guarded.

    A numeric axis has tick labels too, and they are formatted renderings of
    the numbers rather than names for them. Substituting one costs the value
    its type and its precision -- this chart reported ``"1.00"`` for an x of
    ``1.0`` before, which is a string where the frontend expects a number.
    """
    fig, ax = plt.subplots()
    ax.plot([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])

    schema = _schema(fig)
    points = [point for series in schema["data"] for point in series]

    assert [point["x"] for point in points] == [1.0, 2.0, 3.0]
    assert [point["y"] for point in points] == [4.0, 5.0, 6.0]


def test_a_measurement_near_a_tick_is_not_renamed_after_it():
    """
    Rounding is what recovers a dodged group, and it must not reach further.

    On a numeric axis a point at 1.98 is a measurement, not a group drawn
    beside the tick at 2. Nothing here may name it after that tick.
    """
    fig, ax = plt.subplots()
    ax.plot([0.02, 1.98, 3.01], [4.0, 5.0, 6.0])

    schema = _schema(fig)
    points = [point for series in schema["data"] for point in series]

    assert [point["x"] for point in points] == [0.02, 1.98, 3.01]


#: Two groups of five observations and one of a single observation -- ordinary
#: imbalanced categorical data, and the shape where only *some* groups have an
#: interval to draw.
MIXED = pd.DataFrame(
    {
        "g": ["a"] * 5 + ["b"] * 5 + ["c"] * 1,
        "v": [1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 11.0, 12.0, 13.0, 14.0, 7.0],
    }
)


def test_a_group_without_an_interval_does_not_cost_the_others_theirs():
    """
    Only some groups having an interval is the common case, not the exotic one.

    An imbalanced frame -- one category with a single observation among several
    larger ones -- draws intervals for the groups that have them and a NaN
    polyline for the group that does not. Dropping that polyline would leave the
    list one short of the estimates and shift every later group's interval onto
    the wrong estimate, so it stays in place and only its own bound is omitted.

    Before this, the count check failed and the layer fell back to describing
    every drawn line: four series for a three-group chart, one of them a pair of
    NaNs -- the exact rendering this module exists to remove.
    """
    fig, ax = plt.subplots()
    sns.pointplot(MIXED, x="g", y="v", ax=ax)

    schema = _schema(fig)
    data = schema["data"]

    assert schema["type"] == PlotType.ERRORBAR.value
    assert [point["x"] for point in data] == ["a", "b", "c"]
    # The two measurable groups keep their bounds, correctly paired.
    assert data[0]["yMin"] < data[0]["y"] < data[0]["yMax"]
    assert data[1]["yMin"] < data[1]["y"] < data[1]["yMax"]
    assert data[1]["yMin"] > data[0]["yMax"]
    # The single-observation group carries its estimate and no interval.
    assert data[2]["y"] == 7.0
    assert "yMin" not in data[2]
    assert "yMax" not in data[2]


def test_a_partial_interval_promises_no_highlight():
    """
    The selector resolves to one element per point, or the consumer drops it.

    A chart where only some groups have an interval has fewer drawn elements
    than points, so the selector resolves short and the consumer discards the
    whole result -- highlighting nothing while the schema said it would. Saying
    so is better than promising it; the announcement is unaffected either way.
    """
    fig, ax = plt.subplots()
    sns.pointplot(MIXED, x="g", y="v", ax=ax)

    plot = _plots(fig)[0]
    schema = plot.render()

    assert len(schema["data"]) == 3
    assert plot._support_highlighting is False
    assert not plot.elements
    assert "selectors" not in schema


def test_a_hue_level_missing_a_category_does_not_break_the_pairing():
    """
    Seaborn NaN-pads a hue level that never appears in some category.

    Which is what makes the pairing survive an unbalanced hue-by-category set:
    both estimate lines carry one vertex per category whether or not the data
    had one, so the counts still match and the chart does not fall back to
    describing the raw interval polylines.

    Pinned rather than assumed, because it is a claim about another library's
    rendering. Were seaborn to *omit* the point instead, the two estimate lines
    would differ in length, the pairing would fail, and the cap geometry this
    module exists to remove would travel as data again -- so this is the test
    that would say so.
    """
    # Hue level 'y' never appears in category 'c'.
    unbalanced = pd.DataFrame(
        {
            "g": ["a"] * 4 + ["b"] * 4 + ["c"] * 2,
            "half": ["x", "x", "y", "y", "x", "x", "y", "y", "x", "x"],
            "v": [1.0, 2.0, 5.0, 6.0, 10.0, 11.0, 14.0, 15.0, 20.0, 21.0],
        }
    )

    fig, ax = plt.subplots()
    sns.pointplot(unbalanced, x="g", y="v", hue="half", dodge=True, ax=ax)

    schema = _schema(fig)
    data = schema["data"]

    assert schema["type"] == PlotType.ERRORBAR.value
    # Two series, not two series plus six interval polylines.
    assert len(data) == 2
    assert all(len(series) == 3 for series in data)
    assert [point["x"] for point in data[1]] == ["a", "b", "c"]
    # The combination the data does not have arrives as a gap, which the
    # consumer names rather than reading out -- not as cap geometry.
    #
    # `None` rather than `NaN` since #429: a bare `NaN` is not JSON, so it
    # stopped the chart initialising at all, and the core has read `null` as
    # "positioned, no reading" since maidr 4.3.0 (xability/maidr#926). What
    # this case is really pinning is unchanged -- the padding survives, so
    # both estimate lines keep one vertex per category.
    assert data[1][2]["y"] is None


def test_an_estimate_line_without_a_marker_is_still_an_estimate():
    """
    The split tests the literal marker seaborn gives its interval lines.

    ``markers=""`` turns the estimate's own marker off, leaving it as the empty
    string -- while an interval line carries the string ``"None"``. Simplifying
    the check to ``if not line.get_marker()`` would therefore classify the
    estimates as intervals, the counts would stop matching, and the chart would
    fall back to describing every drawn line.

    This is the test that fails if someone makes that simplification.
    """
    fig, ax = plt.subplots()
    sns.pointplot(FRAME, x="group", y="value", marker="", ax=ax)

    schema = _schema(fig)

    assert schema["type"] == PlotType.ERRORBAR.value
    assert len(schema["data"]) == 3
    assert all("yMin" in point for point in schema["data"])
