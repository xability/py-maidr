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
