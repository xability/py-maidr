"""A plotly violin plot produced a figure with no layers at all.

`_extract_plots` had no branch for the `violin` trace type, so a violin fell
through to `PlotlyPlotFactory`, which returned `None`:

    go.Violin(...)                      layers: []
    go.Violin(..., box_visible=True)    layers: []

Nothing errored. The HTML rendered and MAIDR loaded; what arrived was an empty
shell with nothing to navigate and no error saying why (#343).

A violin is announced as two layers, matching the matplotlib path and the
browser-side plotly adapter: `violin_box` summarises the distribution and
`violin_kde` is the shape the chart actually draws. Both are built from one
list of violins, so row *i* of the box and curve *i* of the KDE cannot come to
mean different violins.

The density is recomputed here because plotly runs the KDE in the browser --
`maidr/plotly/violin_stats.py` ports plotly's own rules for that, and
`test_plotly_violin_stats.py` pins the port against real plotly output. This
file covers what the *layers* do with it: grouping, labelling, ordering and
selectors.

Every selector below was checked in Chromium against real plotly output and
resolves to exactly one element.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Two samples with visibly different centres, so a curve paired with the
#: wrong label fails rather than passing on numbers that look plausible.
LOWER = list(np.round(np.random.default_rng(5).normal(10, 2, 30), 6))
UPPER = list(np.round(np.random.default_rng(6).normal(30, 3, 30), 6))


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _of_type(figure: go.Figure, plot_type: PlotType) -> dict:
    """The one layer of *plot_type*."""
    return next(layer for layer in _layers(figure) if layer["type"] is plot_type)


def test_a_violin_is_read_at_all() -> None:
    """The reproduction: a whole chart that announced nothing.

    Not a crash and not a mislabel -- there was no branch for the type, so the
    figure arrived with an empty layer list.
    """
    layers = _layers(go.Figure([go.Violin(y=LOWER, name="A")]))

    assert [layer["type"] for layer in layers] == [
        PlotType.VIOLIN_BOX,
        PlotType.VIOLIN_KDE,
    ]


def test_the_box_summarises_the_sample() -> None:
    """The quartiles and extremes a reader is told, from the sample itself."""
    sample = np.array(LOWER)
    (row,) = _of_type(go.Figure([go.Violin(y=LOWER, name="A")]), PlotType.VIOLIN_BOX)[
        "data"
    ]

    assert row["z"] == "A"
    assert row["min"] == pytest.approx(sample.min())
    assert row["max"] == pytest.approx(sample.max())
    assert row["q1"] < row["q2"] < row["q3"]


def test_the_box_draws_to_the_data_rather_than_a_fence() -> None:
    """A plotly violin's box has no outlier sections, and that is deliberate.

    The KDE curve beside it already covers the tails, so splitting points off
    into `lowerOutliers` / `upperOutliers` would announce a distinction the
    chart does not draw -- and the whiskers would then stop short of values
    the violin visibly extends to.
    """
    (row,) = _of_type(go.Figure([go.Violin(y=LOWER, name="A")]), PlotType.VIOLIN_BOX)[
        "data"
    ]

    assert row["lowerOutliers"] == []
    assert row["upperOutliers"] == []


def test_the_curve_is_one_side_of_the_outline() -> None:
    """One point per position plotly evaluated, not a there-and-back walk.

    The density *is* the half-width, so the mirror image carries no further
    information; walking it would announce every value twice. This is the
    shape the browser-side plotly adapter emits.
    """
    layer = _of_type(go.Figure([go.Violin(y=LOWER, name="A")]), PlotType.VIOLIN_KDE)
    (curve,) = layer["data"]

    positions = [point["y"] for point in curve]

    assert positions == sorted(positions), "a single ascending sweep"
    assert len(set(positions)) == len(positions), "no position visited twice"
    assert all(point["density"] >= 0 for point in curve)
    assert all(point["x"] == "A" for point in curve)


def test_the_curve_carries_no_pixel_coordinates() -> None:
    """`svg_x`/`svg_y` are optional, and Python has no honest value for them.

    Plotly lays the chart out in the browser, so a coordinate emitted here
    would be a guess at where the point ended up. Their absence costs the
    highlight's positioning, not the reading -- and a wrong one would move the
    highlight somewhere the value is not.
    """
    layer = _of_type(go.Figure([go.Violin(y=LOWER, name="A")]), PlotType.VIOLIN_KDE)

    for curve in layer["data"]:
        for point in curve:
            assert set(point) == {"x", "y", "density"}


def test_one_trace_per_category_becomes_one_violin_each() -> None:
    """A categorical violin trace holds several violins.

    Plotly draws one per unique category, in the order they first appear --
    its default `categoryorder` is `trace`, not sorted -- so grouping any
    other way would pair a violin's numbers with a neighbour's name. `UPPER`
    is centred twenty units above `LOWER`, so a swap is visible in the medians
    rather than only in the labels.
    """
    figure = go.Figure(
        [go.Violin(x=["p"] * 30 + ["q"] * 30, y=LOWER + UPPER, name="A")]
    )

    rows = _of_type(figure, PlotType.VIOLIN_BOX)["data"]

    assert [row["z"] for row in rows] == ["p", "q"]
    assert rows[0]["q2"] < 20 < rows[1]["q2"]


def test_categories_keep_the_order_they_appear_in() -> None:
    """Not alphabetical, because plotly's axis is not.

    Stated separately from the test above because a sorted grouping would pass
    that one — `p` before `q` is both. Here the first category sorts last.
    """
    figure = go.Figure(
        [go.Violin(x=["z"] * 30 + ["a"] * 30, y=LOWER + UPPER, name="A")]
    )

    rows = _of_type(figure, PlotType.VIOLIN_BOX)["data"]

    assert [row["z"] for row in rows] == ["z", "a"]
    assert rows[0]["q2"] < 20 < rows[1]["q2"]


def test_a_trace_without_categories_is_named_after_itself() -> None:
    """One violin for the trace, labelled the way plotly labels the axis."""
    figure = go.Figure([go.Violin(y=LOWER, name="measurements")])

    (row,) = _of_type(figure, PlotType.VIOLIN_BOX)["data"]

    assert row["z"] == "measurements"


def test_several_traces_share_one_pair_of_layers() -> None:
    """Two violin traces are two violins, not two charts.

    A subplot gets one `violin_box` and one `violin_kde` however many traces
    the violins came from — the grouping the matplotlib path produces per
    axes, and the one the browser-side adapter uses.
    """
    figure = go.Figure(
        [go.Violin(y=LOWER, name="A"), go.Violin(y=UPPER, name="B")]
    )

    layers = _layers(figure)

    assert [layer["type"] for layer in layers] == [
        PlotType.VIOLIN_BOX,
        PlotType.VIOLIN_KDE,
    ]
    assert [row["z"] for row in layers[0]["data"]] == ["A", "B"]
    assert len(layers[1]["data"]) == 2


def test_the_two_layers_describe_the_violins_in_the_same_order() -> None:
    """Row *i* of the box and curve *i* of the KDE must be one violin.

    They are built from a single list for exactly this reason. Computing each
    layer's grouping separately is how the two quietly come to disagree, and a
    reader moving between them would hear one violin's quartiles against
    another's shape with nothing signalling the swap.
    """
    # Boxes drawn, so the box layer has selectors to compare against the KDE's
    # -- the pairing this test is about is between the two layers, and without
    # a box the box layer honestly emits none.
    figure_with_boxes = go.Figure(
        [
            go.Violin(y=LOWER, name="A", box_visible=True),
            go.Violin(y=UPPER, name="B", box_visible=True),
        ]
    )
    box = _of_type(figure_with_boxes, PlotType.VIOLIN_BOX)
    kde = _of_type(figure_with_boxes, PlotType.VIOLIN_KDE)

    assert [row["z"] for row in box["data"]] == [
        curve[0]["x"] for curve in kde["data"]
    ]
    assert [selector["min"] for selector in box["selectors"]] == [
        selector.replace("path.violin", "path.box") for selector in kde["selectors"]
    ]


def test_a_mean_line_makes_the_mean_available() -> None:
    """`meanline_visible` is plotly's switch, so it decides.

    Emitting a mean regardless would offer a section for a line the chart does
    not draw; omitting it when the line *is* drawn loses a statistic the
    reader can see.
    """
    sample = np.array(LOWER)
    with_line = go.Figure([go.Violin(y=LOWER, name="A", meanline_visible=True)])
    without = go.Figure([go.Violin(y=LOWER, name="A")])

    (shown,) = _of_type(with_line, PlotType.VIOLIN_BOX)["data"]
    (hidden,) = _of_type(without, PlotType.VIOLIN_BOX)["data"]

    assert shown["mean"] == pytest.approx(sample.mean())
    assert "mean" not in hidden


# ---------------------------------------------------------------------------
# Orientation and selectors
# ---------------------------------------------------------------------------


def test_a_vertical_violin_says_so() -> None:
    """The orientation decides which axis a reader is navigating."""
    layers = _layers(go.Figure([go.Violin(y=LOWER, name="A")]))

    assert all(layer["orientation"] == "vert" for layer in layers)


def test_a_horizontal_violin_reads_its_values_off_x() -> None:
    """`orientation="h"` swaps the roles of the two arrays.

    Read the vertical way, a horizontal violin has no sample at all -- `y`
    holds its category -- so this is not a cosmetic difference.
    """
    figure = go.Figure([go.Violin(x=LOWER, name="A", orientation="h")])
    sample = np.array(LOWER)

    (row,) = _of_type(figure, PlotType.VIOLIN_BOX)["data"]

    assert all(layer["orientation"] == "horz" for layer in _layers(figure))
    assert row["min"] == pytest.approx(sample.min())
    assert row["max"] == pytest.approx(sample.max())


def test_a_horizontal_plot_is_emitted_bottom_to_top() -> None:
    """The core reads a horizontal violin plot in visual order.

    Plotly's own order runs the other way, so emitting it unchanged would pair
    each row with the wrong name. Both layers reverse together, or they would
    disagree with each other as well as with the chart.
    """
    figure = go.Figure(
        [
            go.Violin(x=LOWER, name="A", orientation="h"),
            go.Violin(x=UPPER, name="B", orientation="h"),
        ]
    )

    box = _of_type(figure, PlotType.VIOLIN_BOX)
    kde = _of_type(figure, PlotType.VIOLIN_KDE)

    assert [row["z"] for row in box["data"]] == ["B", "A"]
    assert [curve[0]["x"] for curve in kde["data"]] == ["B", "A"]


def test_each_curve_is_paired_with_its_own_shape() -> None:
    """Data order and selector order have to agree *within* one render.

    `render()` asks for the data first and the selectors second, so a
    reversal done in place reverses once for the data and back again for the
    selectors: the first curve is `B`'s numbers carrying `A`'s selector, and
    the highlight lands on the neighbouring violin. Measured, that is exactly
    what happens::

        data[0]='B'   selector[0]=... g:nth-child(1) ...   <- trace A's group

    Every assertion elsewhere in this file still passes in that state, because
    each list is internally consistent and stable across renders. Only the
    pairing between them is wrong, which is why it is asserted here directly:
    `B` is the second trace, so its selector has to name group 2.
    """
    figure = go.Figure(
        [
            go.Violin(x=LOWER, name="A", orientation="h"),
            go.Violin(x=UPPER, name="B", orientation="h"),
        ]
    )

    kde = _of_type(figure, PlotType.VIOLIN_KDE)
    group_of = {"A": "g:nth-child(1)", "B": "g:nth-child(2)"}

    for curve, selector in zip(kde["data"], kde["selectors"]):
        assert group_of[curve[0]["x"]] in selector, (curve[0]["x"], selector)


def test_reversal_survives_a_second_render() -> None:
    """The horizontal order must not flip back on the next render.

    Reversing the stored list in place would put it back in drawn order every
    second time, so after an even number of renders selector *i* would point
    at a different violin from point *i* and the highlight would land on a
    neighbour -- the failure #354 describes, one list further along. A fresh
    list per call is what makes this idempotent.
    """
    figure = go.Figure(
        [
            go.Violin(x=LOWER, name="A", orientation="h"),
            go.Violin(x=UPPER, name="B", orientation="h"),
        ]
    )
    maidr = PlotlyMaidr(figure)

    first = maidr._flatten_maidr()["subplots"][0][0]["layers"]
    second = maidr._flatten_maidr()["subplots"][0][0]["layers"]

    assert [row["z"] for row in first[0]["data"]] == ["B", "A"]
    assert [row["z"] for row in second[0]["data"]] == ["B", "A"]
    assert first[1]["selectors"] == second[1]["selectors"]


def test_the_selectors_address_one_violin_each() -> None:
    """Measured in Chromium: each of these matches exactly one element.

    Two scopings, each for a reason. `.subplot.<id>` keeps a selector inside
    its own panel. The `nth-child` pair separates the trace's group in the
    `violinlayer` from the violin's outline within that group -- a categorical
    trace puts several `path.violin` in one group, so one index cannot address
    both.

    `:nth-child(N of path.violin)` rather than `path.violin:nth-child(N)`,
    because a trace drawing its inner box puts `path.box` among the same
    siblings; the `of` form counts only the violins and so does not depend on
    plotly emitting them all first.
    """
    figure = go.Figure(
        [go.Violin(x=["p"] * 30 + ["q"] * 30, y=LOWER + UPPER, name="A")]
    )

    kde = _of_type(figure, PlotType.VIOLIN_KDE)

    assert kde["selectors"] == [
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.violin)",
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(2 of path.violin)",
    ]


def test_separate_traces_take_separate_groups() -> None:
    """Plotly appends one group per trace, so the outer index moves.

    The mirror of the categorical case above, where the outer index stays and
    the inner one moves. Confusing the two would put every violin of the
    second trace on the first trace's shape.
    """
    figure = go.Figure(
        [go.Violin(y=LOWER, name="A"), go.Violin(y=UPPER, name="B")]
    )

    kde = _of_type(figure, PlotType.VIOLIN_KDE)

    assert kde["selectors"] == [
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.violin)",
        ".subplot.xy .violinlayer > g:nth-child(2) > :nth-child(1 of path.violin)",
    ]


def test_a_violin_on_a_second_subplot_is_scoped_to_it() -> None:
    """The subplot prefix has to follow the trace, not default to `xy`.

    Two panels each holding one violin both sit at `nth-child(1)` of their own
    `violinlayer`, so the axis pair is the only thing telling them apart.
    """
    figure = go.Figure(
        [
            go.Violin(y=LOWER, name="A"),
            go.Violin(y=UPPER, name="B", xaxis="x2", yaxis="y2"),
        ]
    )
    figure.update_layout(
        xaxis={"domain": [0.0, 0.45]},
        xaxis2={"domain": [0.55, 1.0], "anchor": "y2"},
        yaxis2={"anchor": "x2"},
    )

    selectors = sorted(
        selector
        for layer in _layers(figure)
        if layer["type"] is PlotType.VIOLIN_KDE
        for selector in layer["selectors"]
    )

    assert selectors == [
        ".subplot.x2y2 .violinlayer > g:nth-child(1) > :nth-child(1 of path.violin)",
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.violin)",
    ]


def test_a_category_whose_values_are_all_equal_is_still_announced() -> None:
    """Plotly draws it, so a reader hears about it.

    A constant sample has no spread to describe, and the tempting move is to
    skip it. Measured in Chromium, plotly does not: its bandwidth comes out
    zero, it emits one density point of 1, and the category gets its own
    `path.violin` like any other. Skipping would take a drawn category out of
    the reading and -- because plotly renders an element per sample either
    way -- would leave every later violin's selector pointing one shape too
    early.
    """
    figure = go.Figure(
        [go.Violin(x=["p"] * 5 + ["q"] * 30, y=[7.0] * 5 + UPPER, name="A")]
    )

    kde = _of_type(figure, PlotType.VIOLIN_KDE)
    box = _of_type(figure, PlotType.VIOLIN_BOX)

    assert [curve[0]["x"] for curve in kde["data"]] == ["p", "q"]
    assert kde["data"][0] == [{"x": "p", "y": 7.0, "density": 1.0}]
    assert kde["selectors"] == [
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.violin)",
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(2 of path.violin)",
    ]

    flat = box["data"][0]
    assert (flat["min"], flat["q1"], flat["q2"], flat["q3"], flat["max"]) == (
        7.0,
        7.0,
        7.0,
        7.0,
        7.0,
    )


@pytest.mark.parametrize("hidden", [False, "legendonly"], ids=["false", "legendonly"])
def test_a_hidden_violin_is_neither_announced_nor_counted(hidden) -> None:
    """A hidden trace is not on the chart, so it is not in the reading.

    Two failures at once, and the first is the worse. Announcing it describes
    a violin the reader cannot see -- its quartiles, its shape, its name --
    with nothing saying it is not drawn. And letting it advance the group
    index pushes the violin that *is* drawn onto `nth-child(2)` of a layer
    with one child, so its selector matches nothing and the highlight
    silently stops appearing.

    Clicking a legend entry sets `visible="legendonly"` and re-renders, so
    this is a state reached by ordinary use rather than an exotic figure.
    """
    figure = go.Figure(
        [
            go.Violin(y=LOWER, name="hidden", visible=hidden),
            go.Violin(y=UPPER, name="shown"),
        ]
    )

    kde = _of_type(figure, PlotType.VIOLIN_KDE)
    box = _of_type(figure, PlotType.VIOLIN_BOX)

    assert [curve[0]["x"] for curve in kde["data"]] == ["shown"]
    assert [row["z"] for row in box["data"]] == ["shown"]
    assert kde["selectors"] == [
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.violin)"
    ]


def test_a_figure_of_only_hidden_violins_emits_no_layers() -> None:
    """Nothing drawn is nothing to read.

    The empty-list guard the branch already has, driven: skipping every trace
    must leave no `violin_box`/`violin_kde` pair behind rather than an empty
    one, which would be a chart announcing two layers with no violins in them.
    """
    figure = go.Figure([go.Violin(y=LOWER, name="A", visible=False)])

    assert _layers(figure) == []


def test_the_box_selectors_are_box_shaped() -> None:
    """The frontend reads `selectors[i].min`, not `selectors[i]`.

    A flat list of strings is the wrong shape for a `violin_box` layer, and
    nothing in the emitted data would show it: the layer is present, the
    statistics are right, and the highlight simply never resolves. This is the
    assertion that was missing when that is exactly what this layer emitted.

    `PlotlyBoxPlot` and the matplotlib `ViolinBoxPlot` both build the same
    dict, so the shape is the codebase's own convention rather than a guess at
    what the frontend wants.
    """
    figure = go.Figure([go.Violin(y=LOWER, name="A", box_visible=True)])

    (selector,) = _of_type(figure, PlotType.VIOLIN_BOX)["selectors"]

    assert isinstance(selector, dict)
    assert set(selector) == {"lowerOutliers", "min", "iq", "q2", "max", "upperOutliers"}
    assert selector["lowerOutliers"] == []
    assert selector["upperOutliers"] == []
    # Plotly draws whiskers, quartile box and median as one `path.box`, so
    # every section points at it. There is nothing finer to address.
    assert (
        selector["min"]
        == selector["iq"]
        == selector["q2"]
        == selector["max"]
        == ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.box)"
    )


def test_a_layer_with_nothing_drawn_to_point_at_emits_no_selectors() -> None:
    """Neither a box nor a mean line, so there is nothing to highlight.

    Every box selector would address a `path.box` plotly never drew. Emitting
    none says "nothing to point at here" honestly, where a full set says
    "highlight these" and then resolves to nothing. A mean line alone is
    enough to change the answer -- see the meanline test below.
    """
    figure = go.Figure([go.Violin(y=LOWER, name="A")])

    assert "selectors" not in _of_type(figure, PlotType.VIOLIN_BOX)


def test_a_mean_line_gets_a_selector_of_its_own() -> None:
    """Plotly draws the mean as its own path, so it is separately addressable.

    Without this the `mean` section would highlight the box -- a mark next to
    the one being announced, which is worse than no highlight because it looks
    right.
    """
    figure = go.Figure(
        [go.Violin(y=LOWER, name="A", box_visible=True, meanline_visible=True)]
    )

    (selector,) = _of_type(figure, PlotType.VIOLIN_BOX)["selectors"]

    assert selector["mean"] == (
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.mean)"
    )
    assert selector["mean"] != selector["q2"]


def test_a_mean_without_a_box_is_drawn_as_a_meanline() -> None:
    """The element's name depends on whether there is a box to draw it in.

    Measured in Chromium: with a box the children are
    `path.violin, path.box, path.mean`; without one they are
    `path.violin, path.meanline`. One name for both would address nothing in
    half the figures that ask for a mean line -- and this is the half that is
    plotly's default, since `box_visible` is off.
    """
    figure = go.Figure([go.Violin(y=LOWER, name="A", meanline_visible=True)])

    (selector,) = _of_type(figure, PlotType.VIOLIN_BOX)["selectors"]

    assert selector["mean"] == (
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.meanline)"
    )
    # The box sections still name `path.box`, which this figure has none of,
    # so they resolve to nothing -- the same graceful miss a violin without a
    # box takes when it shares a layer with one that has it. What matters is
    # that the mean, which *is* drawn, stays reachable.
    assert "path.box" in selector["q2"]


def test_the_mean_is_announced_only_when_it_is_drawn() -> None:
    """`meanline_visible` is plotly's switch, so it decides both.

    Kept alongside the selector tests because the data and the selector have
    to agree: a `mean` value with no way to point at it, or a pointer to a
    statistic that is not announced, are both half-states.
    """
    sample = np.array(LOWER)
    shown = go.Figure(
        [go.Violin(y=LOWER, name="A", box_visible=True, meanline_visible=True)]
    )
    hidden = go.Figure([go.Violin(y=LOWER, name="A", box_visible=True)])

    (with_mean,) = _of_type(shown, PlotType.VIOLIN_BOX)["data"]
    (without,) = _of_type(hidden, PlotType.VIOLIN_BOX)["data"]
    (selector,) = _of_type(hidden, PlotType.VIOLIN_BOX)["selectors"]

    assert with_mean["mean"] == pytest.approx(sample.mean())
    assert "mean" not in without
    assert "mean" not in selector


def test_a_category_with_no_values_takes_no_slot() -> None:
    """Plotly omits it entirely, which is not what it does for a flat one.

    The two empty-ish cases pull opposite ways, and getting them confused
    breaks the other. Measured in Chromium:

      all values equal    -> plotly draws a degenerate violin, one `path.violin`
      all values missing  -> plotly draws nothing, no element at all

    So a missing category must *not* reserve an index while a flat one must.
    Counting samples rather than drawn violins put `q` at
    `nth-child(2 of path.violin)` in a group holding one, matching nothing.
    """
    figure = go.Figure(
        [go.Violin(x=["p"] * 5 + ["q"] * 30, y=[None] * 5 + UPPER, name="A")]
    )

    kde = _of_type(figure, PlotType.VIOLIN_KDE)

    assert [curve[0]["x"] for curve in kde["data"]] == ["q"]
    assert kde["selectors"] == [
        ".subplot.xy .violinlayer > g:nth-child(1) > :nth-child(1 of path.violin)"
    ]


def test_a_violin_beside_other_traces_is_unaffected() -> None:
    """The control: a new branch must cost the existing types nothing.

    A bar and a scatter both reach the factory fallback that the violin
    branch now sits in front of.
    """
    figure = go.Figure(
        [
            go.Bar(x=["a"], y=[1.0], name="bar"),
            go.Violin(y=LOWER, name="A"),
            go.Scatter(x=[1, 2], y=[3, 4], mode="markers", name="pts"),
        ]
    )

    assert [layer["type"] for layer in _layers(figure)] == [
        PlotType.VIOLIN_BOX,
        PlotType.VIOLIN_KDE,
        PlotType.BAR,
        PlotType.SCATTER,
    ]
