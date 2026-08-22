"""
``seaborn.rugplot`` drew ticks that nothing read (#250).

A rug marks one short tick per observation against the frame -- the raw
data, which a density curve beside it never states. It drew a plain
``LineCollection`` that no patch claimed, so a figure whose only layer was a
rug fell back to a picture, and a rug over a ``kdeplot`` left the
observations unread.

Read as a **scatter**, for the reason ``EventPlot`` gives about an event
plot's ticks: ``height`` is one number for the whole call, so the tick's
length is decoration and only its position is data.

Measured on seaborn 0.13.2::

    sns.rugplot(x=[10.251, ...])
    [[10.251, 0.0], [10.251, 0.025]]

The tick is held constant on the axis carrying the data and stretched
across the other, so the *constant* coordinate is the observation.
"""

from __future__ import annotations

import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.collections import LineCollection

import maidr
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.rugplot import RUG_AXIS_LABEL, read_rug
from maidr.exception import UnsupportedPlotError

import seaborn as sns


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture(autouse=True)
def _quiet_seaborn():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame({"value": [1.0, 2.5, 3.0, 7.25], "other": [4.0, 5.5, 9.0, 2.0]})


def _layers(fig) -> list:
    try:
        return [plot.type.value for plot in FigureManager.get_maidr(fig).plots]
    except UnsupportedPlotError:
        return []


def _schemas(fig) -> list:
    maidr.render(fig)._repr_html_()
    return [plot.schema for plot in FigureManager.get_maidr(fig).plots]


def test_a_rug_registers_the_observations_it_marks(frame):
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", ax=ax)

    (schema,) = _schemas(fig)
    assert schema["type"] == "point"
    assert [point["x"] for point in schema["data"]] == [1.0, 2.5, 3.0, 7.25]


def test_the_tick_height_is_not_announced_as_a_measurement(frame):
    # The whole reason a rug is a scatter and not a spike: every tick is the
    # same length, so the length says nothing. Emitted as a constant rather
    # than as the tick's own base, which is a fraction of the axes height and
    # would read as data at whatever scale the other axis happens to use.
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", height=0.4, ax=ax)

    (schema,) = _schemas(fig)
    assert {point["y"] for point in schema["data"]} == {0}


def test_the_strip_the_ticks_sit_in_is_named_rather_than_left_as_a_value(frame):
    # A rug over a `kdeplot` has a real "Density" label on the axis across
    # the ticks, and every point this layer emits sits at 0 -- so leaving the
    # chart's own label there announces each observation as "Density 0",
    # which is a number the chart does not show.
    fig, ax = plt.subplots()
    sns.kdeplot(frame, x="value", ax=ax)
    sns.rugplot(frame, x="value", ax=ax)

    schemas = _schemas(fig)
    rug = schemas[-1]
    assert rug["axes"]["y"]["label"] == RUG_AXIS_LABEL
    # The axis carrying the observations keeps the chart's own label.
    assert rug["axes"]["x"]["label"] == "value"
    # And the curve beside it is untouched.
    assert schemas[0]["axes"]["y"]["label"] == "Density"


def test_a_rug_on_y_names_the_other_axis(frame):
    # `MaidrPlot.render()` builds the axes payload *before* the data, so
    # resolving which axis the observations lie along during extraction left
    # this case labelling the y axis "Rug" while the observations it carries
    # were announced under "X".
    fig, ax = plt.subplots()
    sns.rugplot(frame, y="other", ax=ax)

    (schema,) = _schemas(fig)
    assert schema["axes"]["x"]["label"] == RUG_AXIS_LABEL
    assert schema["axes"]["y"]["label"] == "other"
    assert [point["y"] for point in schema["data"]] == [4.0, 5.5, 9.0, 2.0]


def test_one_call_marking_both_margins_reads_as_two_layers(frame):
    # Two margins, two collections, two sets of positions off two different
    # axes. Merging them would announce one series whose coordinates come
    # from both.
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", y="other", ax=ax)

    schemas = _schemas(fig)
    assert len(schemas) == 2
    assert [schema["name"] for schema in schemas] == ["value", "other"]
    assert [point["x"] for point in schemas[0]["data"]] == [1.0, 2.5, 3.0, 7.25]
    assert [point["y"] for point in schemas[1]["data"]] == [4.0, 5.5, 9.0, 2.0]


def test_a_rug_beside_a_scatter_reads_its_own_collection(frame):
    # The distinction #426 was about. A rug drawn over a scatter must read
    # the collection *its own call* added, not whichever one a sweep of the
    # axes turns up first.
    fig, ax = plt.subplots()
    sns.scatterplot(frame, x="value", y="other", ax=ax)
    sns.rugplot(frame, x="value", ax=ax)

    schemas = _schemas(fig)
    assert len(schemas) == 2
    rug = schemas[-1]
    assert [point["x"] for point in rug["data"]] == [1.0, 2.5, 3.0, 7.25]
    assert {point["y"] for point in rug["data"]} == {0}


def test_the_layer_is_named_so_it_can_be_told_from_its_neighbour(frame):
    # `MaidrLayer.name`, which xability/maidr#828 added for exactly this.
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", ax=ax)

    (schema,) = _schemas(fig)
    assert schema["name"] == "value"


def test_a_rug_of_bare_arrays_still_gets_a_name():
    # No column to take a name from, so the layer falls back rather than
    # arriving unnamed beside whatever else the figure holds.
    fig, ax = plt.subplots()
    sns.rugplot(x=np.array([1.0, 2.0, 3.0]), ax=ax)

    (schema,) = _schemas(fig)
    assert schema["name"] == RUG_AXIS_LABEL


def test_every_tick_has_an_element_of_its_own(frame):
    # One `<g>` holding one `<path>` per tick, in draw order, which is the
    # order the points were emitted in -- so the two lists line up without
    # either being numbered.
    import re

    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", ax=ax)
    html = maidr.render(fig)._repr_html_()

    plot = FigureManager.get_maidr(fig).plots[0]
    gid = plot._collection.get_gid()
    assert plot.schema["selectors"] == f"g[id='{gid}'] > path"

    group = re.search(rf'<g[^>]*id="{re.escape(gid)}"[^>]*>(.*?)</g>', html, re.S)
    assert group is not None
    assert len(re.findall(r"<path", group.group(1))) == len(plot.schema["data"])


def test_a_collection_that_is_not_a_set_of_ticks_is_declined():
    # A segment sloping across both axes is held constant on neither, so it
    # marks no position. The whole layer is declined rather than part of it
    # read, so a chart is never announced as a subset of itself.
    sloped = LineCollection([[[0.0, 1.0], [5.0, 2.0]]])
    assert read_rug(sloped) is None

    # A tick of zero length is constant on both axes and names neither.
    flat = LineCollection([[[1.0, 0.0], [1.0, 0.0]]])
    assert read_rug(flat) is None


def test_a_rug_no_longer_costs_the_figure_its_reading(frame):
    # What #250 is actually about: before this, a figure whose only layer was
    # a rug had nothing to read and fell back to a picture.
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", ax=ax)

    assert _layers(fig) == ["point"]
    assert len(maidr.render(fig)._repr_html_()) > 0


def test_a_second_rug_on_the_same_axes_reads_only_its_own_ticks(frame):
    # The distinction #426 was about, in the form that actually bites. A
    # scatter beside a rug is safe by accident -- its `PathCollection` is not
    # a `LineCollection`, so even a sweep of the axes would skip it. Two rug
    # calls are not: sweeping would have the second call register the first
    # call's collection as well, announcing those observations twice and
    # leaving the figure with three layers where it has two.
    fig, ax = plt.subplots()
    sns.rugplot(x=np.array([1.0, 2.0]), ax=ax)
    sns.rugplot(x=np.array([8.0, 9.0]), ax=ax)

    schemas = _schemas(fig)
    assert len(schemas) == 2
    assert [[point["x"] for point in schema["data"]] for schema in schemas] == [
        [1.0, 2.0],
        [8.0, 9.0],
    ]


def test_a_hue_split_rug_still_marks_every_observation(frame):
    # The question this has always answered -- does a hue split lose ticks --
    # asked of the reading it has now. Seaborn draws one collection either
    # way and only recolours it, so the split is made in the patch (#597);
    # what must not change is that every observation is still marked, exactly
    # once, across whatever layers it takes.
    frame = frame.assign(sex=["F", "F", "M", "M"])
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="sex", ax=ax)

    marked = [point["x"] for schema in _schemas(fig) for point in schema["data"]]
    assert sorted(marked) == [1.0, 2.5, 3.0, 7.25]


def test_a_rug_under_a_hue_split_density_reads_beside_it(frame):
    # The layered case the reading is actually for: the curves are smoothed
    # and the rug is where the observations fell, so both belong.
    frame = frame.assign(sex=["F", "F", "M", "M"])
    fig, ax = plt.subplots()
    sns.kdeplot(frame, x="value", hue="sex", ax=ax)
    sns.rugplot(frame, x="value", hue="sex", ax=ax)

    schemas = _schemas(fig)
    assert [schema["type"] for schema in schemas] == [
        "smooth",
        "smooth",
        "point",
        "point",
    ]
    marked = [
        point["x"]
        for schema in schemas
        if schema["type"] == "point"
        for point in schema["data"]
    ]
    assert sorted(marked) == [1.0, 2.5, 3.0, 7.25]


def test_a_name_can_come_off_an_axis_another_plot_labelled(frame):
    # The documented limit of `_name_for`. The artist carries no record of
    # the column it came from, so a rug drawn onto an axis something else
    # already labelled takes that label. Pinned so the behaviour is known
    # rather than discovered: the layer's *data* is unaffected, only what it
    # is announced as.
    fig, ax = plt.subplots()
    sns.scatterplot(frame, x="value", y="other", ax=ax)
    sns.rugplot(x=np.array([7.0, 8.0]), ax=ax)

    rug = _schemas(fig)[-1]
    assert rug["name"] == "value"
    assert [point["x"] for point in rug["data"]] == [7.0, 8.0]


def test_a_rug_with_no_tick_length_is_declined():
    # Measured: `height=0` gives every segment two identical ends,
    # `[[1.0, 0.0], [1.0, 0.0]]`, which is constant on both axes and so names
    # neither. Declined along with the rest, and deliberately -- a rug whose
    # ticks have no length draws nothing a sighted reader can see either, so
    # announcing its positions would describe a chart that is not there.
    fig, ax = plt.subplots()
    sns.rugplot(x=np.array([1.0, 2.0, 3.0]), height=0, ax=ax)

    assert _layers(fig) == []
    assert len(maidr.render(fig)._repr_html_()) > 0


def _named(fig) -> list:
    return [
        (schema.get("name"), [point["x"] for point in schema["data"]])
        for schema in _schemas(fig)
    ]


def test_a_hue_split_rug_reads_one_layer_per_level(frame):
    """The groups are drawn and were folded together (#597).

    `rugplot(hue=...)` emitted exactly the schema of the same call without
    one: a single layer holding every tick, named after the *variable* rather
    than a level, with no `z`. The grouping was not merely unnamed -- it was
    absent, on a chart drawn to compare two distributions' raw observations.

    Seaborn leaves it readable: one `LineCollection` with a colour per tick,
    and the legend that names those colours built inside the call. Measured
    on twelve observations over two levels, `colour rows=12, unique=2` and
    `names_for` names every one of them.
    """
    frame = frame.assign(sex=["F", "F", "M", "M"])
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="sex", ax=ax)

    # Each layer holds its own level's observations, checked by value rather
    # than by count -- a split that got the membership backwards would have
    # the right two layers of two.
    assert _named(fig) == [("F", [1.0, 2.5]), ("M", [3.0, 7.25])]


def test_each_layer_names_the_variable_it_is_split_by(frame):
    # `z` says what the split is by and `name` says which side of it this
    # layer is, the division `ScatterPlot` documents.
    frame = frame.assign(sex=["F", "F", "M", "M"])
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="sex", ax=ax)

    labels = [schema["axes"]["z"]["label"] for schema in _schemas(fig)]
    assert labels == ["sex", "sex"]


def test_a_rug_on_y_splits_the_same_way(frame):
    # The observations move to the other axis and the grouping does not move
    # at all; reading the colours off the wrong thing would show here.
    frame = frame.assign(sex=["F", "F", "M", "M"])
    fig, ax = plt.subplots()
    sns.rugplot(frame, y="value", hue="sex", ax=ax)

    assert [
        (schema.get("name"), [point["y"] for point in schema["data"]])
        for schema in _schemas(fig)
    ] == [("F", [1.0, 2.5]), ("M", [3.0, 7.25])]


def test_each_group_addresses_only_its_own_ticks(frame):
    """A group's selectors must not light the whole rug up.

    One collection holds every level's ticks, so the whole-collection
    selector the ungrouped layer uses would highlight all four for a layer
    announcing two. Numbered by segment instead, which is the order the
    `<path>` children are written in.
    """
    frame = frame.assign(sex=["F", "F", "M", "M"])
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="sex", ax=ax)

    selectors = [schema["selectors"] for schema in _schemas(fig)]
    assert [len(group) for group in selectors] == [2, 2]
    # Four distinct ticks addressed, none of them twice.
    assert len({selector for group in selectors for selector in group}) == 4


def test_a_split_drawn_without_a_legend_is_declined(frame):
    # The colours are still there and nothing names them. Groups called "1"
    # and "2" are not an improvement on one strip, so the chart keeps the
    # reading it had.
    frame = frame.assign(sex=["F", "F", "M", "M"])
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="sex", legend=False, ax=ax)

    (schema,) = _schemas(fig)
    assert schema.get("name") == "value"
    assert [point["x"] for point in schema["data"]] == [1.0, 2.5, 3.0, 7.25]


def test_an_ungrouped_rug_keeps_its_whole_collection_selector(frame):
    # Nothing to split, so nothing changes: one layer, one selector matching
    # every tick, named after the variable it marks.
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", ax=ax)

    (schema,) = _schemas(fig)
    assert schema.get("name") == "value"
    assert isinstance(schema["selectors"], str)
    assert len(schema["data"]) == 4


def test_the_layers_follow_the_legend_order_not_the_drawing_order(frame):
    # #502 settled that a grouped layer's layers come out in the order the
    # chart names its levels. This frame draws F first, so a split that kept
    # the drawing order would put F first under either `hue_order`.
    frame = frame.assign(sex=["F", "F", "M", "M"])
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="sex", hue_order=["M", "F"], ax=ax)

    assert _named(fig) == [("M", [3.0, 7.25]), ("F", [1.0, 2.5])]


def test_a_continuous_hue_is_a_scale_and_is_not_split(frame):
    """One layer per observation is not a reading of a colour scale.

    The colours cannot say so themselves, and on a small frame they look
    exactly like a grouping: seaborn's legend samples every value, so all
    four ticks match a swatch and `names_for` names all four. Measured, the
    first draft split this into four layers of one tick each.

    So the plotter is asked instead -- it reports `map_type='numeric'` --
    which is the same discriminator `patch/stripplot` uses and the same
    decline `scatterplot.hue_groups` makes one artist type over.
    """
    frame = frame.assign(level=[0.0, 0.33, 0.66, 1.0])
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="level", ax=ax)

    (schema,) = _schemas(fig)
    assert [point["x"] for point in schema["data"]] == [1.0, 2.5, 3.0, 7.25]


def _grouped_axes(frame):
    """An axes carrying a real hue-split rug, for its legend and colours."""
    frame = frame.assign(sex=["F", "F", "M", "M"])
    _, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="sex", ax=ax)
    return ax, list(np.asarray(ax.collections[0].get_colors()))


def test_a_colour_list_that_does_not_correspond_to_the_ticks_is_declined(frame):
    """Fewer colours than ticks cannot say which tick wore which.

    Splitting on them would hand the first ticks to groups and drop the
    rest, which is silent data loss. Nothing measured draws such a
    collection -- seaborn gives one colour per tick under a hue, and one for
    the whole rug without -- so it is asserted directly.

    Built on an axes whose legend *does* name these colours, so the decline
    is the count and not the naming: given four of them the same call
    splits.
    """
    from maidr.patch.rugplot import _HUE_MAP_TYPE, _hue_groups

    ax, colours = _grouped_axes(frame)
    segments = [[(0.0, 0.0), (0.0, 1.0)] for _ in range(4)]
    short = LineCollection(segments, colors=[colours[0], colours[-1]])
    full = LineCollection(segments, colors=colours)

    token = _HUE_MAP_TYPE.set("categorical")
    try:
        assert _hue_groups(ax, short, 4) is None
        assert _hue_groups(ax, full, 4) is not None
    finally:
        _HUE_MAP_TYPE.reset(token)


def test_a_tick_no_swatch_names_declines_the_whole_split(frame):
    """A partly named rug is worse than an unnamed one.

    Splitting on the named ticks alone would announce a group called "None"
    holding the rest -- maidr's own word for "unmatched" read aloud as a
    level. The whole split is declined instead, which is the rule
    `scatterplot.hue_groups` follows for a point no swatch claims.
    """
    from maidr.patch.rugplot import _HUE_MAP_TYPE, _hue_groups

    ax, colours = _grouped_axes(frame)
    segments = [[(0.0, 0.0), (0.0, 1.0)] for _ in range(4)]
    # Two ticks in a colour the legend names, two in one it does not.
    partly = LineCollection(
        segments, colors=[colours[0], colours[0], "magenta", "magenta"]
    )

    token = _HUE_MAP_TYPE.set("categorical")
    try:
        assert _hue_groups(ax, partly, 4) is None
    finally:
        _HUE_MAP_TYPE.reset(token)


def test_a_split_named_by_a_figure_legend_still_says_what_it_split_by():
    """The `z` label has to come off the legend that named the groups.

    `legend_of` falls back to a lone figure-level legend for a panel with
    none of its own -- that is how a `PairGrid`'s panels are named -- and
    the layers then carry the levels it named them with. Reading the title
    off `ax.get_legend()` alone leaves that chart saying which side of a
    grouping each layer is on without ever saying what the grouping is.

    Measured before the fix: two layers, `name='a'` and `name='b'`, and no
    `z` at all.
    """
    frame = pd.DataFrame({"v": [1.0, 2.0, 3.0, 7.0, 8.0, 9.0], "g": list("aaabbb")})
    fig, ax = plt.subplots()
    palette = sns.color_palette(n_colors=2)
    handles = [
        plt.Line2D([], [], color=colour, label=name)
        for name, colour in zip(["a", "b"], palette)
    ]
    fig.legend(handles=handles, title="g")

    sns.rugplot(frame, x="v", hue="g", ax=ax, legend=False)

    assert ax.get_legend() is None
    schemas = _schemas(fig)
    assert [schema.get("name") for schema in schemas] == ["a", "b"]
    assert [schema["axes"].get("z") for schema in schemas] == [
        {"label": "g"},
        {"label": "g"},
    ]


def test_a_hue_on_one_level_is_read_as_one_ungrouped_layer():
    """One group is not a grouping.

    Reachable here and not from the scatter split, which declines a one-level
    hue earlier on its own legend count. So this is where
    `grouped_by_name`'s fewer-than-two rule is exercised through a chart --
    measured, removing it leaves the scatter's own file green and only this
    one red (#599).
    """
    frame = pd.DataFrame({"value": [0.1, 0.2, 0.3, 0.4], "grp": ["p"] * 4})
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="grp", ax=ax)

    schemas = _schemas(fig)
    assert len(schemas) == 1
    # The variable's own name, which is what an ungrouped rug announces.
    assert schemas[0].get("name") == "value"
    assert len(schemas[0]["data"]) == 4


# --- The bounds that make the layer reachable in grid mode (maidr#1132) ------
#
# A point layer renders braille only in grid mode, and grid mode is built from
# `axes.{x,y}.{min,max,tickStep}`. With the labels alone, maidr's `ScatterTrace`
# returns an empty braille state, and a rug is then the one chart with no
# braille surface reachable by any keystroke. Measured there, four observations
# at 1, 2, 3 and 9 over a 0-10 axis give `values [[2, 1, 0, 1]]` -- the count
# per cell, which is the clustering a rug is drawn to show and the one thing
# its audio cannot carry, every tick sitting at the same place on the axis
# pitch is mapped from.


def _axis(schema, key) -> dict:
    """One axis' config. `MaidrKey` is a str enum, so the emitted keys compare
    equal to their plain-string spellings and need no conversion -- calling
    `str()` on them gives `'MaidrKey.LABEL'` and breaks the comparison."""
    return dict(schema["axes"][key])


def test_the_observation_axis_carries_the_chart_s_own_bounds(frame):
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", ax=ax)

    low, high = ax.get_xlim()
    x = _axis(_schemas(fig)[0], "x")
    assert x["min"] == pytest.approx(low)
    assert x["max"] == pytest.approx(high)
    assert x["tickStep"] > 0


def test_the_strip_is_one_row_deep(frame):
    """Which is what a rug is: every entry sits at the same place across the
    ticks. A finer step buys a second row of zeroes -- measured against
    `ScatterTrace`, `tickStep` 0.5 gives `[[2, 1, 0, 1], [0, 0, 0, 0]]`.

    Centred on the entries rather than starting at them. `0` to `1` was the
    first spelling and reads identically -- measured against `ScatterTrace`,
    both give `values [[2, 1, 0, 1]]` -- but it puts the entries on a cell
    *edge*, and which side of an edge a value falls on is the frontend's
    tie-break rather than something this states. `one_row_around` centres
    them, which also generalises to a layer whose row is not zero.
    """
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", ax=ax)

    assert _axis(_schemas(fig)[0], "y") == {
        "label": "Rug",
        "min": -0.5,
        "max": 0.5,
        "tickStep": 1.0,
    }


def test_a_rug_up_the_y_axis_puts_the_bounds_on_y(frame):
    fig, ax = plt.subplots()
    sns.rugplot(frame, y="value", ax=ax)

    schema = _schemas(fig)[0]
    assert _axis(schema, "x") == {
        "label": "Rug",
        "min": -0.5,
        "max": 0.5,
        "tickStep": 1.0,
    }
    assert _axis(schema, "y")["min"] == pytest.approx(ax.get_ylim()[0])


def test_an_axis_whose_ticks_are_not_evenly_spaced_is_declined(frame):
    """A grid built on uneven ticks is a surface whose cells do not
    correspond to the axis the reader is told about, which is worse than no
    surface.

    The scale here is linear, so this is the chart that isolates the tick
    check: measured, `set_xticks([0, 1, 5, 10])` gives `step=None` while the
    log-scale guard passes it straight through.
    """
    fig, ax = plt.subplots()
    ax.set_xticks([0.0, 1.0, 5.0, 10.0])
    sns.rugplot(frame, x="value", ax=ax)

    schema = _schemas(fig)[0]
    assert _axis(schema, "x") == {"label": "value"}
    assert _axis(schema, "y") == {"label": "Rug"}


def test_a_log_axis_is_declined(frame):
    fig, ax = plt.subplots()
    ax.set_xscale("log")
    sns.rugplot(frame, x="value", ax=ax)

    schema = _schemas(fig)[0]
    assert _axis(schema, "x") == {"label": "value"}
    assert _axis(schema, "y") == {"label": "Rug"}


def test_a_log_axis_answers_its_limits_and_its_ticks_in_different_spaces(frame):
    """What makes the scale check a guard rather than a live branch.

    Dropping it leaves the whole suite green, and the reason is worth
    recording rather than rediscovering: matplotlib answers `get_xlim` in
    **log space** and `get_xticks` in **data space**, so a log chart's tick
    step is measured against a span it does not belong to and the
    `step > (high - low)` clause declines it anyway.

    Pinned here because it is a fact about matplotlib, not about this layer.
    If a release ever makes the two agree, this goes red and the scale check
    stops being redundant -- which is the moment it starts earning its keep.
    """
    fig, ax = plt.subplots()
    ax.set_xscale("log")
    ax.set_xticks([1.0, 2.0, 3.0])
    sns.rugplot(frame, x="value", ax=ax)

    low, high = ax.get_xlim()
    ticks = list(ax.get_xticks())

    # The ticks are the data-space values that were asked for.
    assert ticks == [1.0, 2.0, 3.0]
    # The limits are not: they are the logs of the data-space bounds, and the
    # whole span is narrower than one tick step.
    assert high - low < 1.0
    assert high < min(ticks)


def test_the_bounds_change_nothing_the_layer_already_said(frame):
    """Additive only: grid mode is entered deliberately, so the ordinary
    reading has to be untouched. Pinned against the values the layer emitted
    before the bounds existed."""
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", ax=ax)

    schema = _schemas(fig)[0]
    assert schema.get("name") == "value"
    assert [point["x"] for point in schema["data"]] == list(frame["value"])
    assert all(point["y"] == 0 for point in schema["data"])
    # One selector for the whole collection, as an ungrouped rug has always
    # had -- a string rather than the per-segment list a grouped one gets.
    assert isinstance(schema["selectors"], str)


def test_each_hue_group_gets_the_bounds_too(frame):
    """A grouped rug is several layers over one axis, and a reader feeling any
    of them is feeling the same plotting area."""
    frame = frame.assign(sex=["F", "F", "M", "M"])
    fig, ax = plt.subplots()
    sns.rugplot(frame, x="value", hue="sex", ax=ax)

    schemas = _schemas(fig)
    assert len(schemas) == 2
    for schema in schemas:
        assert _axis(schema, "x")["tickStep"] > 0
        assert _axis(schema, "y") == {
            "label": "Rug",
            "min": -0.5,
            "max": 0.5,
            "tickStep": 1.0,
        }
        # And the grouping variable is still named. The bounds are added
        # beside `z` rather than in place of it, and nothing else in the
        # schema moves.
        assert _axis(schema, "z") == {"label": "sex"}
