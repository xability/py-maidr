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
    from matplotlib.collections import LineCollection

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
    return [(schema.get("name"), [point["x"] for point in schema["data"]])
            for schema in _schemas(fig)]


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
    from matplotlib.collections import LineCollection

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
    from matplotlib.collections import LineCollection

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
