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
        lambda fig: so.Plot(_frame(), x="x", y="y", color="g")
        .add(so.Dot())
        .on(fig)
        .plot()
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
            lambda fig: so.Plot(frame, x="x", y="y", color="g")
            .add(so.Dot())
            .on(fig)
            .plot()
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
        lambda fig: so.Plot(_frame(), x="x", y="y", color="g")
        .add(so.Dots())
        .on(fig)
        .plot()
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
            lambda fig: so.Plot(frame, x="x", y="y", color="g")
            .add(so.Line())
            .on(fig)
            .plot()
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
        lambda fig: so.Plot(frame, x="x", y="y", color="g")
        .facet(col="panel")
        .add(so.Dot())
        .on(fig)
        .plot()
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
        lambda fig: so.Plot(_frame(), x="x", y="y", color="g")
        .add(so.Dot())
        .on(fig)
        .plot()
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
