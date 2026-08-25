"""
``so.Dash`` drew an observation per tick and registered nothing (#670).

`so.Dash()` is `so.Dot()`'s flat sibling: instead of a marker it draws a
short horizontal segment at each observation, so several observations at one
category stack up as a row of rules rather than as a pile of overlapping
circles. What it leaves behind is a ``LineCollection`` and nothing else,
which is the whole of why it was silent -- ``ScatterPlot`` asks a
``PathCollection`` for its offsets, and a line collection has none.

Two things had to be measured rather than assumed.

**The width is drawing and the middle is the datum.** Measured on
``seaborn 0.13.2``, forty observations over five categories::

    so.Dash()               first segment  [[-0.4, 3.696], [0.4, 3.696]]
    so.Dash(), so.Dodge()   first segment  [[-0.4, 3.696], [0.0, 3.696]]

The span is ``0.8`` by default and halved again by a dodge, and neither
number is anything the chart measured. What both spellings agree on is the
segment's centre.

**A dodged tick's centre is not its tick.** Read literally it announces
``-0.2`` where the axis says ``a`` -- the shape #617 describes for
``so.Bar``. It needs no special case here, because ``ScatterPlot._on_axis``
already snaps a drawn coordinate to the slot it belongs to and ``_sample``
names it: the machinery a jittered strip plot needed (#439), reused.
"""

from __future__ import annotations

import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn.objects as so

import maidr
from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Forty observations over five categories, split two ways by colour."""
    rng = np.random.default_rng(4)
    return pd.DataFrame(
        {
            "x": list("abcde") * 8,
            "v": rng.normal(5, 2, 40),
            "g": ["p"] * 20 + ["q"] * 20,
            "n": rng.integers(1, 9, 40),
        }
    )


def _layers(plot) -> list[dict]:
    """Every layer the drawn plot registered, as schemas."""
    return [layer.schema for layer in FigureManager.get_maidr(plot.plot()._figure).plots]


def _only(plot) -> dict:
    schemas = _layers(plot)
    assert len(schemas) == 1, f"expected one layer, got {len(schemas)}"
    return schemas[0]


def test_a_dash_mark_is_read_rather_than_registering_nothing():
    schema = _only(so.Plot(_frame(), x="x", y="v").add(so.Dash()))

    assert schema[MaidrKey.TYPE] is PlotType.SCATTER
    assert len(schema[MaidrKey.DATA]) == 40


def test_every_tick_is_read_off_its_own_middle():
    """The centre, not either end: the span is the mark's width."""
    frame = _frame()
    schema = _only(so.Plot(frame, x="n", y="v").add(so.Dash()))

    drawn = {(point[MaidrKey.X], round(point[MaidrKey.Y], 6))
             for point in schema[MaidrKey.DATA]}
    expected = {(float(n), round(float(v), 6))
                for n, v in zip(frame["n"], frame["v"])}

    assert drawn == expected


def test_a_categorical_tick_is_named_after_its_slot():
    """A reader is handed "a", not the slot index the position is."""
    schema = _only(so.Plot(_frame(), x="x", y="v").add(so.Dash()))
    points = schema[MaidrKey.DATA]

    assert points[0][MaidrKey.X] == 0.0
    assert points[0][MaidrKey.X_LABEL] == "a"
    assert {point[MaidrKey.X_LABEL] for point in points} == set("abcde")


def test_a_dodged_tick_announces_its_category_and_not_the_offset():
    """A dodge moves the tick off its slot; the reading puts it back.

    Measured, a dodged first segment runs `[-0.4, y]` to `[0.0, y]`, so its
    midpoint is `-0.2` -- the offset, which is what #617 found `so.Bar`
    announcing where the axis says `a`.

    A dodge needs something to dodge by, so this chart is also colour-split
    and reads as one layer per level (#680). The snapping is per tick, so it
    is asserted of every layer rather than of the one this used to be.
    """
    schemas = _layers(
        so.Plot(_frame(), x="x", y="v", color="g").add(so.Dash(), so.Dodge())
    )

    assert len(schemas) == 2
    for schema in schemas:
        points = schema[MaidrKey.DATA]
        assert {point[MaidrKey.X] for point in points} == {0.0, 1.0, 2.0, 3.0, 4.0}
        assert {point[MaidrKey.X_LABEL] for point in points} == set("abcde")


def test_an_aggregated_dash_reads_one_tick_per_category():
    schema = _only(so.Plot(_frame(), x="x", y="v").add(so.Dash(), so.Agg()))

    assert len(schema[MaidrKey.DATA]) == 5
    assert [point[MaidrKey.X_LABEL] for point in schema[MaidrKey.DATA]] == list("abcde")


def test_a_numeric_axis_is_not_renamed_after_a_tick():
    """No `xLabel` where the axis carries measurements rather than names."""
    schema = _only(so.Plot(_frame(), x="n", y="v").add(so.Dash()))

    assert all(MaidrKey.X_LABEL not in point for point in schema[MaidrKey.DATA])


def test_a_selector_resolves_to_exactly_one_drawn_tick():
    """Addressed by path inside the collection's group, not by `<use>`.

    A line collection writes one `<path>` per segment where a marker
    collection writes `<use>` elements, so the inherited scatter selector
    would match nothing. Resolved against the SVG the render actually emits
    rather than compared as a string.
    """
    figure = plt.figure()
    so.Plot(_frame(), x="x", y="v").add(so.Dash()).on(figure).plot()
    schema = FigureManager.get_maidr(figure).plots[0].schema
    selectors = schema[MaidrKey.SELECTOR]

    html = maidr.render(figure)._repr_html_()
    gid = re.search(r"id='([^']+)'", selectors[0]).group(1)
    group = re.search(
        r"<g id=\"" + re.escape(gid) + r"\"[^>]*>(.*?)</g>", html, re.S
    )

    assert group is not None, "the collection's group is not in the rendered SVG"
    assert len(selectors) == 40
    assert len(re.findall(r"<path", group.group(1))) == 40


def test_a_dash_beside_a_dot_reads_as_two_layers():
    """Each mark its own layer, which is what `so.Plot.add()` twice means."""
    schemas = _layers(
        so.Plot(_frame(), x="x", y="v").add(so.Dot()).add(so.Dash())
    )

    assert [schema[MaidrKey.TYPE] for schema in schemas] == [
        PlotType.SCATTER,
        PlotType.SCATTER,
    ]


def test_a_sideways_chart_reads_the_tick_the_other_way_round():
    """A tick runs across the axis its category is on, and either axis can be it.

    Measured, the same forty observations drawn both ways::

        so.Plot(x="cat", y="v")   [[-0.4, 3.696], [ 0.4, 3.696]]
        so.Plot(y="cat", x="v")   [[3.696, -0.4], [3.696,  0.4]]

    Reading only the first is not a narrower reading but a broken one: every
    segment of the transposed chart fails the horizontal test, the layer
    finds nothing to announce, and the `ExtractionError` that follows takes
    the whole figure to a static image.
    """
    frame = _frame()
    schema = _only(so.Plot(frame, y="x", x="v").add(so.Dash()))
    points = schema[MaidrKey.DATA]

    assert len(points) == 40
    # The category is on y now, and so is its name.
    assert {point[MaidrKey.Y] for point in points} == {0.0, 1.0, 2.0, 3.0, 4.0}
    assert {point[MaidrKey.Y_LABEL] for point in points} == set("abcde")
    assert all(MaidrKey.X_LABEL not in point for point in points)
    # And the values are on x, unrounded.
    assert {round(point[MaidrKey.X], 6) for point in points} == {
        round(float(v), 6) for v in frame["v"]
    }


def test_a_segment_that_is_not_a_tick_is_declined():
    """Constant on neither axis, so there is no one position it marks.

    No `so.Dash` spelling draws one -- both orientations hold one coordinate
    fixed -- so the guard is tested against a collection built to have the
    case. Averaged into a midpoint it would announce a position the chart
    never drew.
    """
    from matplotlib.collections import LineCollection

    from maidr.core.plot.dashplot import DRAWN_DASHES, DashPlot

    _, ax = plt.subplots()
    collection = LineCollection(
        [
            [(0.0, 1.0), (1.0, 1.0)],   # a tick
            [(2.0, 1.0), (3.0, 4.0)],   # a sloped segment
            [(4.0, 2.0), (5.0, 2.0)],   # a tick
        ]
    )
    ax.add_collection(collection)

    points = DashPlot(ax, **{DRAWN_DASHES: collection})._extract_plot_data()

    assert [point[MaidrKey.X] for point in points] == [0.5, 4.5]


def test_a_tick_with_a_non_finite_end_is_dropped():
    """`json.dumps` writes `NaN` as a bare token, which `JSON.parse` rejects.

    One such value stops the chart initialising at all (#427), so the tick is
    dropped rather than announced -- and a scatter point with no position has
    nothing left to say, unlike a bar that keeps its category.

    What drops it is the **shape** check, and this pins the matplotlib
    behaviour that makes it sufficient: a non-finite vertex is stripped
    before `get_segments` returns, so the tick arrives as a single point
    rather than as a pair with a `NaN` in it. If a release stops stripping,
    this test fails here rather than the payload failing to parse in a
    browser.
    """
    from matplotlib.collections import LineCollection

    from maidr.core.plot.dashplot import DRAWN_DASHES, DashPlot

    _, ax = plt.subplots()
    collection = LineCollection(
        [
            [(0.0, 1.0), (1.0, 1.0)],
            # One end, not both -- the case that would reach the midpoint
            # if the pair survived, since it is constant on x.
            [(2.0, np.nan), (2.0, 5.0)],
            [(4.0, 2.0), (5.0, 2.0)],
        ]
    )
    ax.add_collection(collection)

    # matplotlib strips the non-finite vertex, so the tick arrives with one
    # end rather than two. That is the mechanism, asserted rather than
    # assumed.
    assert [len(segment) for segment in collection.get_segments()] == [2, 1, 2]

    plot = DashPlot(ax, **{DRAWN_DASHES: collection})
    points = plot._extract_plot_data()

    assert [point[MaidrKey.X] for point in points] == [0.5, 4.5]
    # The selectors follow the drawn segments, not the announced ones: the
    # dropped tick is still a `<path>`, so numbering past it would put the
    # second point's highlight on the tick that was declined.
    assert [
        int(re.search(r"nth-of-type\((\d+)\)", selector).group(1))
        for selector in plot._get_selector()
    ] == [1, 3]


def test_the_nth_selector_addresses_the_nth_tick():
    """Off by one puts every highlight on a neighbour, which is silent.

    The count agreeing is not enough -- a list numbered from zero, or from
    the announced points rather than the drawn ones, has the right length and
    the wrong targets. This resolves the third selector against the SVG and
    checks it reaches the third path.
    """
    figure = plt.figure()
    so.Plot(_frame(), x="x", y="v").add(so.Dash()).on(figure).plot()
    selectors = FigureManager.get_maidr(figure).plots[0].schema[MaidrKey.SELECTOR]

    html = maidr.render(figure)._repr_html_()
    gid = re.search(r"id='([^']+)'", selectors[2]).group(1)
    group = re.search(
        r"<g id=\"" + re.escape(gid) + r"\"[^>]*>(.*?)</g>", html, re.S
    )
    paths = re.findall(r"<path[^>]*>", group.group(1))

    assert re.search(r"nth-of-type\((\d+)\)", selectors[0]).group(1) == "1"
    assert re.search(r"nth-of-type\((\d+)\)", selectors[2]).group(1) == "3"
    assert len(paths) == len(selectors)


def test_a_colour_split_becomes_one_layer_per_level():
    """A two-level chart offered one anonymous cloud of forty ticks (#680).

    `hue_groups` inverts a collection's colours against the legend that names
    them, and it read *face* colours — which a line collection has none of.
    Measured on this chart, 0 face colours against 40 edge colours: the
    grouping was all there, one attribute over.
    """
    schemas = _layers(
        so.Plot(_frame(), x="x", y="v", color="g").add(so.Dash(), so.Dodge())
    )

    assert [schema.get(MaidrKey.NAME) for schema in schemas] == ["p", "q"]
    assert [len(schema[MaidrKey.DATA]) for schema in schemas] == [20, 20]


def test_each_level_keeps_its_categories_and_its_own_values():
    frame = _frame()
    schemas = _layers(
        so.Plot(frame, x="x", y="v", color="g").add(so.Dash(), so.Dodge())
    )

    for schema, level in zip(schemas, ["p", "q"]):
        points = schema[MaidrKey.DATA]
        # Still snapped to the ticks rather than announced at the dodge
        # offset, and still named after them.
        assert {point[MaidrKey.X_LABEL] for point in points} == set("abcde")
        assert {round(point[MaidrKey.Y], 6) for point in points} == {
            round(float(v), 6) for v in frame.loc[frame["g"] == level, "v"]
        }


def test_each_level_outlines_its_own_ticks_and_not_its_neighbours():
    """Numbered against the collection, not against the layer.

    Every level's ticks live in one collection, so a layer that numbered its
    selectors from one would point the second level's announcements at the
    first level's paths.
    """
    schemas = _layers(
        so.Plot(_frame(), x="x", y="v", color="g").add(so.Dash(), so.Dodge())
    )
    numbers = [
        [
            int(re.search(r"nth-of-type\((\d+)\)", selector).group(1))
            for selector in schema[MaidrKey.SELECTOR]
        ]
        for schema in schemas
    ]

    assert numbers[0] == list(range(1, 21))
    assert numbers[1] == list(range(21, 41))
    # And one gid between them, because it is one collection.
    assert len({
        re.search(r"id='([^']+)'", schema[MaidrKey.SELECTOR][0]).group(1)
        for schema in schemas
    }) == 1


def test_an_ungrouped_dash_is_still_one_unnamed_layer():
    """The split is a grouping, not a default: one colour is one layer."""
    schema = _only(so.Plot(_frame(), x="x", y="v").add(so.Dash()))

    assert MaidrKey.NAME not in schema
    assert len(schema[MaidrKey.DATA]) == 40
