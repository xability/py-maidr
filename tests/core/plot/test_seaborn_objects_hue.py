"""
A ``seaborn.objects`` mark split by ``color=`` read as one unnamed layer (#617).

#615 made every `so.Dot` register; it registered as *one* layer holding every
point. The classic spelling of the same chart has split and named its groups
since #544. Measured before, two levels of three:

    so.Plot(frame, x=, y=, color="g").add(so.Dot())   point None (6)
    sns.scatterplot(data=frame, x=, y=, hue="g")      point 'p'  (3)
                                                      point 'q'  (3)

Two things had to change, and neither alone is enough.

**`hue_groups` asked the wrong legend.** It read `ax.get_legend()` where the
rest of the module goes through `legend_of`, which also reads a lone *figure*
legend (#561) and a lone shared-axis sibling's (#610). A `so.Plot` puts its
one legend on the figure, so the axes had none and the split declined before
looking at a colour. Two answers to one question in one module is the drift
#599 extracted `legend_names` to end.

**The split was asked too early.** `Plotter._plot_layer` is the only place
that can say which artists a layer drew, and `Plotter._make_legend` runs after
every layer is on the page. A *name* can be deferred to render as a callable,
which is what #612 did for `FacetGrid`; a *split* cannot, because it decides
how many layers there are. So the reading is recorded during the draw and
registered once the plot is complete.

**Not in scope, deliberately.** `so.Line(color=)` reads as one layer of two
series and stays that way -- measured, that is exactly what
`seaborn.lineplot(hue=)` already does, so there is no gap between the two
spellings to close and naming multi-series lines is a question for both at
once. `so.Bar(color=)` draws every level into one container, unlike
`seaborn.barplot(hue=)`, so its split needs an answer this does not have.
"""

from __future__ import annotations

import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn as sns
import seaborn.objects as so

import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    # `p` holds the low half of y and `q` the high half, with no overlap, so
    # which layer got which group is a fact about the numbers rather than
    # about the order they were registered in.
    return pd.DataFrame(
        {
            "x": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0],
            "y": [1.0, 2.0, 3.0, 11.0, 12.0, 13.0],
            "g": ["p", "p", "p", "q", "q", "q"],
        }
    )


def _named(figure) -> list[tuple[str, object, list]]:
    """Every layer as ``(type, name, the y values it holds)``."""
    maidr.render(figure)._repr_html_()
    out = []
    for plot in FigureManager.get_maidr(figure).plots:
        data = plot.schema["data"]
        held = (
            [float(point["y"]) for point in data] if plot.type.value == "point" else []
        )
        out.append((plot.type.value, plot.schema.get("name"), held))
    return out


def _drawn(build) -> plt.Figure:
    figure = plt.figure()
    build(figure)
    return figure


def test_a_colour_split_dot_reads_one_named_layer_per_group():
    """Two layers, named, each holding its own half."""
    figure = _drawn(
        lambda fig: (
            so.Plot(_frame(), x="x", y="y", color="g").add(so.Dot()).on(fig).plot()
        )
    )

    assert _named(figure) == [
        ("point", "p", [1.0, 2.0, 3.0]),
        ("point", "q", [11.0, 12.0, 13.0]),
    ]


def test_it_reads_exactly_as_the_classic_spelling_of_the_same_chart():
    """Compared against `scatterplot(hue=)` rather than against written-down
    names, so a change to how a grouped scatter is emitted moves both sides
    together and this keeps asserting what it means to."""
    frame = _frame()
    objects = _named(
        _drawn(
            lambda fig: (
                so.Plot(frame, x="x", y="y", color="g").add(so.Dot()).on(fig).plot()
            )
        )
    )
    classic = _named(
        _drawn(
            lambda fig: sns.scatterplot(
                data=frame, x="x", y="y", hue="g", ax=fig.subplots()
            )
        )
    )

    assert objects == classic


def test_a_colour_split_dots_mark_splits_too():
    """`so.Dots` is the many-points spelling and draws the same artist."""
    figure = _drawn(
        lambda fig: (
            so.Plot(_frame(), x="x", y="y", color="g").add(so.Dots()).on(fig).plot()
        )
    )

    assert [name for _, name, _ in _named(figure)] == ["p", "q"]


def test_a_dot_with_no_colour_is_untouched():
    """Additive. One group against no legend reads exactly as it did."""
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="x", y="y").add(so.Dot()).on(fig).plot()
    )

    assert _named(figure) == [("point", None, [1.0, 2.0, 3.0, 11.0, 12.0, 13.0])]


def test_a_colour_split_line_is_still_one_layer_of_several_series():
    """Deliberately unchanged, and pinned so a later change is a decision.

    `seaborn.lineplot(hue=)` reads as one `line` layer of two unnamed series,
    measured, so the two spellings already agree. Naming a multi-series line
    is a question for both at once rather than one this may answer for the
    new interface alone.
    """
    frame = _frame()
    objects = _named(
        _drawn(
            lambda fig: (
                so.Plot(frame, x="x", y="y", color="g").add(so.Line()).on(fig).plot()
            )
        )
    )
    classic = _named(
        _drawn(
            lambda fig: sns.lineplot(
                data=frame, x="x", y="y", hue="g", ax=fig.subplots()
            )
        )
    )

    assert objects == classic == [("line", None, [])]


def test_each_facet_panel_splits_its_own_groups():
    """The split is per panel, and the legend naming it is the figure's."""
    frame = _frame().assign(panel=["one", "one", "two", "one", "one", "two"])
    figure = _drawn(
        lambda fig: (
            so.Plot(frame, x="x", y="y", color="g")
            .facet(col="panel")
            .add(so.Dot())
            .on(fig)
            .plot()
        )
    )

    assert [(name, held) for _, name, held in _named(figure)] == [
        ("p", [1.0, 2.0]),
        ("q", [11.0, 12.0]),
        ("p", [3.0]),
        ("q", [13.0]),
    ]


def test_every_split_layer_can_be_highlighted():
    """A layer that announces correctly and outlines nothing is the blind
    spot xability/maidr#814 names, and a split layer addresses its points
    through the collection it shares with its sibling."""
    figure = _drawn(
        lambda fig: (
            so.Plot(_frame(), x="x", y="y", color="g").add(so.Dot()).on(fig).plot()
        )
    )
    html = maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    assert len(plots) == 2
    for plot in plots:
        selectors = plot.schema["selectors"]
        assert len(selectors) == len(plot.schema["data"])
        for selector in selectors:
            for identifier in re.findall(r"'([^']+)'", str(selector)):
                assert identifier in html


# --------------------------------------------------------------------------
# The shared helpers, asked directly. Both live in
# `maidr/core/plot/scatterplot.py` and are reached by every grouped scatter,
# so a change to either is a change to the classic path as well.
# --------------------------------------------------------------------------


def test_a_collection_swatch_and_a_marker_swatch_name_the_same_colour():
    """The handle type `seaborn.objects` builds is not the classic one.

    Classic seaborn builds scatter legend handles as `Line2D` markers, which
    answer with a flat RGBA; `seaborn.objects` builds `PathCollection`s,
    which answer `get_facecolor()` with a row per colour. `to_rgba` accepts
    both -- measured, a ``(1, 4)`` array resolves to its single colour -- so
    nothing had to be added for this, and this test says so rather than
    leaving the shape difference looking like a hazard that was handled.
    """
    from matplotlib.collections import PathCollection
    from matplotlib.lines import Line2D

    from maidr.core.plot.scatterplot import _handle_colour

    _, axes = plt.subplots()
    collection = axes.scatter([0.0], [0.0], color="#1f77b4")
    line = Line2D([], [], color="#1f77b4")

    assert isinstance(collection, PathCollection)
    assert _handle_colour(collection) == _handle_colour(line) is not None


def test_a_handle_drawn_in_several_colours_names_none():
    """A swatch drawn in several colours names no group, and must keep
    declining -- a handle resolved to the first of its colours would name a
    group after a colour it only partly stands for."""
    from maidr.core.plot.scatterplot import _handle_colour

    _, axes = plt.subplots()
    many = axes.scatter([0.0, 1.0], [0.0, 1.0], color=["#1f77b4", "#ff7f0e"])

    assert _handle_colour(many) is None


def test_the_groups_are_read_off_the_legend_wherever_it_was_put():
    """`hue_groups` goes through `legend_of` now, so a figure legend answers.

    Built by hand rather than through `so.Plot`, so this states the rule
    rather than one library's use of it: one collection carrying two colours,
    and the only legend naming them on the figure.
    """
    from matplotlib.lines import Line2D

    from maidr.core.plot.scatterplot import hue_groups

    figure, axes = plt.subplots()
    rng = np.random.default_rng(0)
    points = axes.scatter(
        rng.uniform(size=4),
        rng.uniform(size=4),
        color=["#1f77b4"] * 2 + ["#ff7f0e"] * 2,
    )
    figure.legend(
        handles=[Line2D([], [], color="#1f77b4"), Line2D([], [], color="#ff7f0e")],
        labels=["p", "q"],
    )

    assert hue_groups(axes, points) == [("p", [0, 1]), ("q", [2, 3])]


def test_a_plot_that_was_given_no_figure_registers_too():
    """`Plot.plot()` is wrapped because every route reaches it.

    Every other test here hands the figure in with `.on(fig)`. This one does
    not, so the layers are registered on a figure seaborn made -- which is
    what `show()`, `save()` and `_repr_png_()` all do, and what makes
    wrapping one method enough.
    """
    plotter = so.Plot(_frame(), x="x", y="y", color="g").add(so.Dot()).plot()

    assert _named(plotter._figure) == [
        ("point", "p", [1.0, 2.0, 3.0]),
        ("point", "q", [11.0, 12.0, 13.0]),
    ]


def test_the_notebook_repr_route_reads_the_same_chart():
    """`_repr_png_()` calls `plot()` for its own figure, so it must not
    raise and must leave a chart behind."""
    plot = so.Plot(_frame(), x="x", y="y", color="g").add(so.Dot())

    assert plot._repr_png_() is not None
    assert [name for _, name, _ in _named(plot.plot()._figure)] == ["p", "q"]


def test_a_plotter_with_nowhere_to_record_declines_rather_than_raising():
    """The layer's reading is kept on the plotter until the legend exists.

    A seaborn release that gave `Plotter` `__slots__` would leave nowhere to
    keep it, and raising there would come out of the user's *draw* -- so the
    chart would stop rendering rather than stop being read. Declining puts it
    back where #615 found it, which is what an unread mark already does.
    """
    from maidr.patch.seaborn_objects import _layer

    figure = plt.figure()
    figure.subplots()

    class _Slotted:
        __slots__ = ("_figure",)

        def __init__(self, fig):
            self._figure = fig

    drawn = []

    def draw(*args, **kwargs):
        drawn.append(True)

    _layer(draw, _Slotted(figure), (None, {"mark": so.Dot()}), {})

    assert drawn == [True]
    assert not hasattr(figure, "_maidr_pending")


def _bars() -> pd.DataFrame:
    """Two categories over two levels, every magnitude distinct."""
    return pd.DataFrame(
        {"cat": ["a", "a", "b", "b"], "val": [1.0, 2.0, 3.0, 4.0], "g": list("pqpq")}
    )


def test_a_colour_split_bar_announces_its_categories_not_its_coordinates():
    """The half of #617 that fixes a *wrong* reading rather than a missing one.

    `BarPlot._labels_for` announces bar positions whenever the tick labels do
    not number the bars -- right where #382 put it, since a numeric axis picks
    its own breaks -- and a colour split walks straight into it: every level's
    bars land on one axes against one tick per category. Measured before, two
    categories and two levels::

                            bars   ticks        announced x
        color= (no move)      4    ['a','b']    ['0', '0', '1', '1']
        color= + Dodge()      4    ['a','b']    ['-0.2', '0.2', '0.8', '1.2']

    Those are the dodge offsets, announced as the categories. Splitting the
    layer per level puts one bar against one tick again.

    Asked here of the plain `color=` spelling, which stays split: a bar
    carrying `Dodge()` or `Stack()` is read as one grouped layer instead, and
    the same claim about its categories is made below against that shape.
    """
    figure = _drawn(
        lambda fig: (
            so.Plot(_bars(), x="cat", y="val", color="g").add(so.Bar()).on(fig).plot()
        )
    )
    maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    assert [
        (plot.schema.get("name"), [(bar["x"], bar["y"]) for bar in plot.schema["data"]])
        for plot in plots
    ] == [
        ("p", [("a", 1.0), ("b", 3.0)]),
        ("q", [("a", 2.0), ("b", 4.0)]),
    ]


@pytest.mark.parametrize(
    "build, expected",
    [
        pytest.param(lambda plot: plot.add(so.Bar()), "bar", id="plain"),
        pytest.param(
            lambda plot: plot.add(so.Bar(), so.Dodge()), "dodged_bar", id="dodged"
        ),
        pytest.param(
            lambda plot: plot.add(so.Bar(), so.Stack()), "stacked_bar", id="stacked"
        ),
        pytest.param(
            lambda plot: plot.add(so.Bar(), so.Dodge(), so.Stack()),
            "stacked_bar",
            id="dodged-then-stacked",
        ),
    ],
)
def test_a_position_transform_types_the_layer(build, expected):
    """The third item on #617. `so` states the transform as an explicit
    `Move` on the layer, which is a cleaner signal than anything the classic
    path gets -- `seaborn.barplot(hue=)` is read as dodged by *counting
    containers*, and a stacked bar has to be declared through
    `maidr.stacked()`.

    A transform makes the chart a grouped bar chart of that kind, so it reads
    as one layer of every group rather than a layer per group. Plain `color=`
    has no transform and overplots the levels at the same position, which is
    neither, so it keeps the split.

    `Dodge()` *and* `Stack()` together resolves to the stack: seaborn dodges
    the levels apart and then stacks within each dodged slot, so the segments
    a reader steps through are the stack's.
    """
    figure = plt.figure()
    build(so.Plot(_bars(), x="cat", y="val", color="g")).on(figure).plot()
    maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    assert [str(plot.schema["type"].value) for plot in plots] == (
        [expected] if expected != "bar" else ["bar", "bar"]
    )


def test_three_groups_split_three_ways_in_legend_order():
    """Two levels is the smallest split there is, so it cannot tell a rule
    that holds from one that happens to pair up. Three does: `grouped_by_name`
    builds each group's index list by ascending draw order, and the bars
    interleave (`p q r p q r`), so a level's bars are non-contiguous."""
    frame = pd.DataFrame(
        {
            "cat": ["a"] * 3 + ["b"] * 3,
            "val": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "g": list("pqr") * 2,
        }
    )
    figure = _drawn(
        lambda fig: (
            so.Plot(frame, x="cat", y="val", color="g").add(so.Bar()).on(fig).plot()
        )
    )
    maidr.render(figure)._repr_html_()

    assert [
        (plot.schema.get("name"), [(bar["x"], bar["y"]) for bar in plot.schema["data"]])
        for plot in FigureManager.get_maidr(figure).plots
    ] == [
        ("p", [("a", 1.0), ("b", 4.0)]),
        ("q", [("a", 2.0), ("b", 5.0)]),
        ("r", [("a", 3.0), ("b", 6.0)]),
    ]


def test_three_groups_reach_the_grouped_reading_in_legend_order():
    """The same three levels through the transform branch, where they become
    one layer of three groups rather than three layers. The interleaving is
    what makes it worth asking twice: `grouped_by_name` returns each level's
    indices in ascending draw order, and with `p q r p q r` no level's bars
    are contiguous, so a container assembled from the wrong slice shows up.
    """
    frame = pd.DataFrame(
        {
            "cat": ["a"] * 3 + ["b"] * 3,
            "val": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "g": list("pqr") * 2,
        }
    )
    figure = _drawn(
        lambda fig: (
            so.Plot(frame, x="cat", y="val", color="g")
            .add(so.Bar(), so.Dodge())
            .on(fig)
            .plot()
        )
    )
    maidr.render(figure)._repr_html_()
    (plot,) = FigureManager.get_maidr(figure).plots

    assert [
        [(bar["z"], bar["x"], bar["y"]) for bar in group]
        for group in plot.schema["data"]
    ] == [
        [("p", "a", 1.0), ("p", "b", 4.0)],
        [("q", "a", 2.0), ("q", "b", 5.0)],
        [("r", "a", 3.0), ("r", "b", 6.0)],
    ]


def test_a_faceted_grouped_bar_reads_one_layer_per_panel():
    """The per-panel loop and the grouped handover meet here. Faceting is
    exercised for the scatter split elsewhere; a bar carrying a transform
    reaches the same loop by a different branch, and the one legend `so.Plot`
    builds has to name the groups on *every* panel -- `legend_of` reads a
    lone figure legend as doing exactly that (#561).
    """
    frame = pd.DataFrame(
        {
            "cat": ["a", "a", "b", "b"] * 2,
            "val": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "g": list("pqpq") * 2,
            "panel": ["L"] * 4 + ["R"] * 4,
        }
    )
    figure = _drawn(
        lambda fig: (
            so.Plot(frame, x="cat", y="val", color="g")
            .facet(col="panel")
            .add(so.Bar(), so.Dodge())
            .on(fig)
            .plot()
        )
    )
    maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    assert [plot.schema["type"].value for plot in plots] == [
        "dodged_bar",
        "dodged_bar",
    ]
    assert [plot.schema["axes"]["z"] for plot in plots] == [{"label": "g"}] * 2
    assert [
        [
            [(bar["z"], bar["x"], bar["y"]) for bar in group]
            for group in plot.schema["data"]
        ]
        for plot in plots
    ] == [
        [[("p", "a", 1.0), ("p", "b", 3.0)], [("q", "a", 2.0), ("q", "b", 4.0)]],
        [[("p", "a", 5.0), ("p", "b", 7.0)], [("q", "a", 6.0), ("q", "b", 8.0)]],
    ]


@pytest.mark.parametrize(
    "build, expected",
    [
        pytest.param(
            lambda plot: plot.add(so.Bar(), so.Norm(func="sum", by=["x"]), so.Stack()),
            "stacked_normalized_bar",
            id="shares",
        ),
        pytest.param(
            lambda plot: plot.add(
                so.Bar(),
                so.Norm(func="sum", by=["x"], percent=True),
                so.Stack(),
            ),
            "stacked_normalized_bar",
            id="percent",
        ),
        pytest.param(
            lambda plot: plot.add(
                so.Bar(), so.Norm(func="sum", by=["x", "color"]), so.Stack()
            ),
            "stacked_bar",
            id="normed-per-level",
        ),
        pytest.param(
            lambda plot: plot.add(so.Bar(), so.Norm(), so.Stack()),
            "stacked_bar",
            id="normed-by-max",
        ),
        pytest.param(
            lambda plot: plot.add(so.Bar(), so.Norm(func="sum"), so.Stack()),
            "stacked_bar",
            id="normed-without-by",
        ),
        pytest.param(
            lambda plot: plot.add(so.Bar(), so.Stack(), so.Norm(func="sum", by=["x"])),
            "stacked_bar",
            id="normed-after-stacking",
        ),
        pytest.param(
            lambda plot: plot.add(so.Bar(), so.Stack()),
            "stacked_bar",
            id="not-normed",
        ),
        pytest.param(
            lambda plot: plot.add(so.Bar(), so.Norm(func="sum", by=["x"]), so.Dodge()),
            "dodged_bar",
            id="normed-but-not-stacked",
        ),
    ],
)
def test_only_a_stack_that_reaches_a_whole_is_a_hundred_percent_bar(build, expected):
    """#620. `so.Norm` looks like the 100% stack's transform and is not one
    on its own -- which combination of `func` and `by` was written decides,
    and so does whether it ran before the stack. Measured, each category's
    stack total::

        Norm(func="sum", by=["x"])              1.0     <- a whole
        Norm(func="sum", by=["x", "color"])     2.0     <- every level to 1
        Norm(func="sum")                        0.583 / 1.417
        Norm()                                  0.833 / 2.0
        Stack() then Norm(...)                  0.429 / 1.0

    `by=["x", "color"]` is the trap: it names the category axis, so a rule
    reading `by` would claim it, and it announces shares summing to twice
    the whole.

    So the drawn bars are asked instead, and a plain `Stack()` is left alone
    even when its categories happen to total alike -- the author has to have
    asked for a sum-normalisation *and* the bars have to have landed on it.

    `Stack()` before `Norm(...)` is turned away by the totals rather than by
    a rule about the order; `test_a_stack_normalised_afterwards_is_claimed_
    only_when_it_landed` covers where that lands and why the order is not
    asked about separately.
    """
    figure = plt.figure()
    build(so.Plot(_bars(), x="cat", y="val", color="g")).on(figure).plot()
    maidr.render(figure)._repr_html_()

    assert [
        plot.schema["type"].value for plot in FigureManager.get_maidr(figure).plots
    ] == [expected]


def test_a_stack_normalised_afterwards_is_claimed_only_when_it_landed():
    """Why `_normalises_to_a_whole` does not check where `Norm` sits relative
    to `Stack`, even though the order plainly changes the drawing.

    After `Stack()` then `Norm(func="sum")` the drawn tops are each
    category's `t_i / sum(t_i)` over the *cumulative* tops, so they are all
    wholes only when one top carries the whole sum -- every level but the
    last at zero -- and the shares announced then (0, 1) are the true ones.

    Three levels with one at zero: tops 0.8 and 0.667, turned away.
    Two levels with one at zero: tops 1.0, claimed, and correctly.
    """
    three = pd.DataFrame(
        {
            "cat": ["a"] * 3 + ["b"] * 3,
            "val": [0.0, 1.0, 3.0, 0.0, 2.0, 2.0],
            "g": list("pqr") * 2,
        }
    )
    figure = _drawn(
        lambda fig: (
            so.Plot(three, x="cat", y="val", color="g")
            .add(so.Bar(), so.Stack(), so.Norm(func="sum", by=["x"]))
            .on(fig)
            .plot()
        )
    )
    maidr.render(figure)._repr_html_()
    assert [
        plot.schema["type"].value for plot in FigureManager.get_maidr(figure).plots
    ] == ["stacked_bar"]

    two = pd.DataFrame(
        {"cat": ["a", "a", "b", "b"], "val": [0.0, 2.0, 0.0, 4.0], "g": list("pqpq")}
    )
    figure = _drawn(
        lambda fig: (
            so.Plot(two, x="cat", y="val", color="g")
            .add(so.Bar(), so.Stack(), so.Norm(func="sum", by=["x"]))
            .on(fig)
            .plot()
        )
    )
    maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots
    assert len(figure.axes[0].containers[0]) == 2
    assert [plot.schema["type"].value for plot in plots] == ["bar"]


def test_a_callable_sum_is_read_like_the_named_one():
    """`so.Norm` takes either a numpy method's *name* or a callable, and
    `Norm(func=numpy.sum)` draws exactly what `Norm(func="sum")` does -- so a
    reader should not be told a different thing about it.

    A lambda still declines. What this reads is the layer's stated intent,
    and a lambda states none; declining keeps the chart reading as the stack
    it is rather than claiming a whole on a guess.
    """
    import numpy as np

    for func in ("sum", np.sum, sum):
        figure = plt.figure()
        (
            so.Plot(_bars(), x="cat", y="val", color="g")
            .add(so.Bar(), so.Norm(func=func, by=["x"]), so.Stack())
            .on(figure)
            .plot()
        )
        maidr.render(figure)._repr_html_()
        assert [
            plot.schema["type"].value for plot in FigureManager.get_maidr(figure).plots
        ] == ["stacked_normalized_bar"], func
        plt.close("all")

    figure = plt.figure()
    (
        so.Plot(_bars(), x="cat", y="val", color="g")
        .add(so.Bar(), so.Norm(func=lambda a, **kw: a.sum(**kw), by=["x"]), so.Stack())
        .on(figure)
        .plot()
    )
    maidr.render(figure)._repr_html_()
    assert [
        plot.schema["type"].value for plot in FigureManager.get_maidr(figure).plots
    ] == ["stacked_bar"]


def test_a_dodge_beside_the_stack_is_not_a_whole():
    """Where the boundary of `_normalises_to_a_whole` sits, stated rather
    than left implicit.

    Totals are keyed on the drawn position, and a `Dodge()` moves the
    segments apart, so the keys split with them. That is the answer rather
    than a hole in it: each drawn column is one dodge slot's share of its
    category, not the category's, so none of them is a whole. Measured, four
    levels dodged and stacked under `Norm(func="sum", by=["x"])`: eight
    columns topping out between 0.1 and 0.4.
    """
    frame = pd.DataFrame(
        {
            "cat": ["a"] * 4 + ["b"] * 4,
            "val": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "g": list("pqrs") * 2,
        }
    )
    figure = _drawn(
        lambda fig: (
            so.Plot(frame, x="cat", y="val", color="g")
            .add(so.Bar(), so.Norm(func="sum", by=["x"]), so.Dodge(), so.Stack())
            .on(fig)
            .plot()
        )
    )
    maidr.render(figure)._repr_html_()

    tops = {}
    for patch in figure.axes[0].containers[0]:
        key = round(float(patch.get_x()), 3)
        tops[key] = max(tops.get(key, 0.0), patch.get_y() + patch.get_height())
    assert len(tops) == 8
    assert not any(abs(top - 1.0) < 1e-6 for top in tops.values())

    assert [
        plot.schema["type"].value for plot in FigureManager.get_maidr(figure).plots
    ] == ["stacked_bar"]


def test_only_a_sum_normalisation_counts_as_asking_for_a_whole():
    """The intent half of `_normalises_to_a_whole`, asked of the function
    directly because no `so.Bar` reaches it.

    `Norm(func="max", by=["x"])` divides each category by its own maximum,
    so a stack of it totals `sum / max`. With two drawn levels that is
    always more than 1 and less than 100, and a level at zero draws nothing
    at all -- so no chart of a plausible size lands it on a whole. A hundred
    equal levels would, at exactly 100.0, and would then announce each
    segment as 1 *percent* when it is the whole of its level.

    Stubbing the moves and the bars says that in three lines instead of a
    hundred-level chart, and it is the only thing keeping `func == "sum"`
    from being decoration.
    """
    from types import SimpleNamespace

    from maidr.patch.seaborn_objects import _normalises_to_a_whole

    _, axes = plt.subplots()
    # Two categories, each a stack reaching exactly 1.0 -- what a sum
    # normalisation draws, and what a max normalisation would draw if a
    # chart could get there.
    container = axes.bar([0, 1, 0, 1], [0.25, 0.5, 0.75, 0.5], bottom=[0, 0, 0.25, 0.5])

    # `Stack` and `Norm` are matched by class name, so the stubs are named.
    class Norm(SimpleNamespace):
        pass

    class Stack(SimpleNamespace):
        pass

    assert _normalises_to_a_whole([Norm(func="sum"), Stack()], container) is True
    assert _normalises_to_a_whole([Norm(func="max"), Stack()], container) is False
    # No stack at all is not a whole either, however the bars happen to land.
    assert _normalises_to_a_whole([Norm(func="sum")], container) is False
    assert _normalises_to_a_whole(None, container) is False


def test_a_hundred_percent_bar_announces_the_shares_it_drew():
    """The payload is the drawn heights, because seaborn has already turned
    the numbers into shares -- unlike the plotly path, where `layout.barnorm`
    leaves the raw values in the trace and `maidr/plotly/barnorm.py` has to
    compute them (#338).

    Horizontal too, where the shares run along x and the categories sit on y.
    """
    figure = _drawn(
        lambda fig: (
            so.Plot(_bars(), y="cat", x="val", color="g")
            .add(so.Bar(), so.Norm(func="sum", by=["y"]), so.Stack())
            .on(fig)
            .plot()
        )
    )
    maidr.render(figure)._repr_html_()
    (plot,) = FigureManager.get_maidr(figure).plots

    assert plot.schema["type"].value == "stacked_normalized_bar"
    assert plot.schema["orientation"] == "horz"
    shares = [
        [(bar["z"], bar["y"], round(bar["x"], 3)) for bar in group]
        for group in plot.schema["data"]
    ]
    assert shares == [
        [("p", "a", 0.333), ("p", "b", 0.429)],
        [("q", "a", 0.667), ("q", "b", 0.571)],
    ]
    # Each category's segments are a whole, which is the claim the type makes.
    for category in ("a", "b"):
        total = sum(
            bar["x"]
            for group in plot.schema["data"]
            for bar in group
            if bar["y"] == category
        )
        assert total == pytest.approx(1.0)


def test_the_grouped_reading_names_its_z_axis_from_the_figure_legend():
    """`GroupedBarPlot` read both its `z` label and its group names from
    `ax.get_legend()`, which is right for `seaborn.barplot(hue=)` and `None`
    for an `so.Plot` -- seaborn hangs that legend on the **figure**. Reading
    through `legend_of` finds it, the same tier #561 added for `PairGrid`.

    Without it the `z` axis has no label and the groups fall back to the
    containers' matplotlib labels, so a reader is told the levels apart by
    nothing they can name.
    """
    figure = _drawn(
        lambda fig: (
            so.Plot(_bars(), x="cat", y="val", color="g")
            .add(so.Bar(), so.Dodge())
            .on(fig)
            .plot()
        )
    )
    maidr.render(figure)._repr_html_()
    (plot,) = FigureManager.get_maidr(figure).plots

    assert figure.axes[0].get_legend() is None
    assert plot.schema["axes"]["z"] == {"label": "g"}
    assert [group[0]["z"] for group in plot.schema["data"]] == ["p", "q"]


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda plot: plot.add(so.Bar()), id="split"),
        pytest.param(lambda plot: plot.add(so.Bar(), so.Dodge()), id="grouped"),
    ],
)
def test_a_horizontal_colour_split_bar_keeps_its_orientation(build):
    """The synthetic container carries the original's `orientation`, and both
    readings depend on it -- `BarPlot._extract_orientation` on the split path,
    `GroupedBarPlot._extract_orientation` on the grouped one. Drop it and a
    horizontal colour-split bar defaults to vertical, putting the category in
    the magnitude field: exactly the reading #950 warns about.
    """
    figure = _drawn(
        lambda fig: build(so.Plot(_bars(), y="cat", x="val", color="g")).on(fig).plot()
    )
    maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    assert {plot.schema["orientation"] for plot in plots} == {"horz"}
    # The magnitude runs along x and the category sits on y, whichever
    # reading was taken -- the layers just group the same points differently.
    points = [
        bar
        for plot in plots
        for group in (
            plot.schema["data"]
            if isinstance(plot.schema["data"][0], list)
            else [plot.schema["data"]]
        )
        for bar in group
    ]
    assert sorted((bar["x"], bar["y"]) for bar in points) == [
        (1.0, "a"),
        (2.0, "a"),
        (3.0, "b"),
        (4.0, "b"),
    ]


def test_a_bar_with_no_colour_is_untouched():
    """Additive. One group against no legend reads exactly as it did."""
    frame = _bars().groupby("cat", as_index=False).sum(numeric_only=True)
    figure = _drawn(
        lambda fig: so.Plot(frame, x="cat", y="val").add(so.Bar()).on(fig).plot()
    )
    maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    assert len(plots) == 1
    assert plots[0].schema.get("name") is None
    assert [(bar["x"], bar["y"]) for bar in plots[0].schema["data"]] == [
        ("a", 3.0),
        ("b", 7.0),
    ]


def test_each_split_bar_layer_addresses_its_own_bars():
    """Two layers built from one container must not share a selector -- the
    shape review caught on xability/r-maidr#226, where two layers of a kind
    resolved to the same element and the second highlighted the first's."""
    figure = _drawn(
        lambda fig: (
            so.Plot(_bars(), x="cat", y="val", color="g")
            .add(so.Bar(), so.Dodge())
            .on(fig)
            .plot()
        )
    )
    html = maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    selectors = []
    for plot in plots:
        found = plot.schema.get("selectors") or plot.schema.get("selector")
        flat = found if isinstance(found, list) else [found]
        for selector in flat:
            for identifier in re.findall(r"'([^']+)'", str(selector)):
                assert identifier in html
        selectors.append(tuple(flat))

    assert len(set(selectors)) == len(selectors)


def test_an_ungrouped_container_names_no_groups():
    """`bar_groups` declines exactly where `hue_groups` does, because both
    end in the same shared tail."""
    from maidr.core.plot.barplot import bar_groups

    _, axes = plt.subplots()
    one_colour = axes.bar(["a", "b"], [1.0, 2.0])

    assert bar_groups(axes, one_colour) is None
