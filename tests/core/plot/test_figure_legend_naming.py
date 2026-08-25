"""
A colour-split ``so.Line`` gave two series a reader could not tell apart
(#672).

`so.Plot(..., color="g").add(so.Line())` drew two lines and read as two
series carrying no names at all -- no per-point `z`, and no `axes.z` naming
the variable they were split by. The identical chart written with the classic
function named both::

    sns.lineplot(hue="g")   axes.z {"label": "g"}   first point z "a"
    so.Line() + color="g"   axes.z absent           first point z absent

**A `so.Plot`'s legend is the figure's, never the axes'.** Measured on every
colour-split mark: `ax.legend_` is `None` and `fig.legends` holds exactly
one, whose title is the grouping variable, whose texts are the group names,
and whose handles carry the drawn artists' own colours.

`maidr.util.legend_names.legend_of` already knows that -- it falls back to
the figure's legend when the axes has none, and the scatter and bar paths
moved onto it in #617. Two readers never did: `MultiLinePlot`'s
`legend_labels`, and `MaidrPlot._legend_title`. That is exactly why
`so.Dot(color=)` was named and `so.Line(color=)` was not.

The fix is those two reads, and nothing else. Every rule about *which*
legend answers -- the axes' own wins, two figure legends are ambiguous and
decline -- is `legend_of`'s and is asserted here as reached rather than
reimplemented.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
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
    """Two groups over the same positions, with no value shared between them.

    A series announced under its neighbour's name is then visible in the
    values, not only in the label.
    """
    return pd.DataFrame(
        {
            "x": [0.0, 1.0, 2.0, 0.0, 1.0, 2.0],
            "y": [1.0, 3.0, 2.0, 7.0, 9.0, 8.0],
            "g": ["p", "p", "p", "q", "q", "q"],
        }
    )


def _schema(figure) -> dict:
    """The first layer's schema, after a real render."""
    maidr.render(figure)._repr_html_()
    return FigureManager.get_maidr(figure).plots[0].schema


def _so_line(figure) -> dict:
    so.Plot(_frame(), x="x", y="y", color="g").add(so.Line()).on(figure).plot()
    return _schema(figure)


def _named_series(schema) -> list[list]:
    """Each series' distinct ``z`` values, in the order the series are read."""
    return [sorted({point.get("z") for point in series}) for series in schema["data"]]


def test_a_colour_split_so_line_names_each_series():
    # The reproduction. Before this the layer held two series of bare
    # (x, y) and a reader met "line 1" and "line 2".
    schema = _so_line(plt.figure())

    assert _named_series(schema) == [["p"], ["q"]]


def test_a_colour_split_so_line_names_the_variable_it_split_by():
    # The other half, and the one a reader needs first: `z` says which group
    # a point is in, `axes.z` says what kind of thing a group *is*.
    schema = _so_line(plt.figure())

    assert schema["axes"]["z"] == {"label": "g"}


def test_the_names_go_with_the_values_they_were_drawn_with():
    # Two series named is worth nothing if they are named the wrong way
    # round, and a swap is invisible in the labels alone.
    schema = _so_line(plt.figure())

    readings = {
        series[0]["z"]: [point["y"] for point in series] for series in schema["data"]
    }
    assert readings == {"p": [1.0, 3.0, 2.0], "q": [7.0, 9.0, 8.0]}


def test_the_classic_spelling_of_the_same_chart_reads_the_same_way():
    # What the `so` chart is being brought into line *with*, asserted here so
    # a change that broke the classic path to fix this one would be caught.
    figure, ax = plt.subplots()
    sns.lineplot(data=_frame(), x="x", y="y", hue="g", ax=ax)
    schema = _schema(figure)

    assert _named_series(schema) == [["p"], ["q"]]
    assert schema["axes"]["z"] == {"label": "g"}


def test_a_colour_split_so_dot_names_the_variable_too():
    # The scatter path already split and named its *groups* -- it goes
    # through `legend_of` via `hue_groups` -- but the `z` label came from
    # `_legend_title`, which did not, so the variable went unnamed.
    figure = plt.figure()
    so.Plot(_frame(), x="x", y="y", color="g").add(so.Dot()).on(figure).plot()
    maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    assert [plot.schema["axes"]["z"] for plot in plots] == [
        {"label": "g"},
        {"label": "g"},
    ]


def _moved_to_the_figure(draw) -> plt.Figure:
    """One chart whose legend was moved off the panel and onto the figure.

    The swatches are the *drawn* ones, which is what makes this the real
    case rather than a stand-in: a grid's ``add_legend()`` gathers the
    panels' own handles, so the colour match that names the groups still
    holds and only the legend's owner has changed.
    """
    figure, ax = plt.subplots()
    draw(ax)
    own = ax.get_legend()
    handles = own.legend_handles
    labels = [text.get_text() for text in own.get_texts()]
    own.remove()
    figure.legend(handles, labels, title="g")
    return figure


def test_a_scatter_names_its_variable_from_a_legend_moved_to_the_figure():
    # `_legend_title` is shared, and `ScatterPlot` is one of the three other
    # classes that read through it. Its groups were already named -- the
    # split goes through `legend_of` -- so before this fix the chart said
    # which side of a grouping each layer was on and never said what the
    # grouping was.
    figure = _moved_to_the_figure(
        lambda ax: sns.scatterplot(data=_frame(), x="x", y="y", hue="g", ax=ax)
    )
    maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    assert [plot.schema["name"] for plot in plots] == ["p", "q"]
    assert [plot.schema["axes"]["z"] for plot in plots] == [
        {"label": "g"},
        {"label": "g"},
    ]


def test_an_estimate_plot_names_its_variable_from_that_legend_too():
    # `PointPlot`, the third caller. An interval chart is where a grouping
    # matters most -- whether two groups' intervals overlap is the question
    # the chart is drawn to answer -- so an unnamed one is the worst place
    # for this to be missing.
    # Replicated, because an estimate plot draws an interval only where
    # there is a spread to draw one from: with one observation per cell
    # `PointPlot` never appears and the chart is a plain line.
    replicated = pd.concat([_frame()] * 3, ignore_index=True)
    replicated["y"] += [0.0, 0.5, -0.5] * (len(replicated) // 3)
    figure = _moved_to_the_figure(
        lambda ax: sns.pointplot(data=replicated, x="x", y="y", hue="g", ax=ax)
    )
    maidr.render(figure)._repr_html_()
    plots = FigureManager.get_maidr(figure).plots

    # A point plot draws its estimates and their intervals as separate
    # layers, and both are read; the grouping names the chart rather than
    # either layer, so it belongs on every one of them.
    assert "error_bar" in [plot.type.value for plot in plots]
    assert [plot.schema["axes"]["z"] for plot in plots] == [{"label": "g"}] * len(plots)


def test_a_line_chart_with_no_legend_is_named_nothing_rather_than_something():
    # The direction that matters if this were ever loosened: a chart nobody
    # split announces no groups, rather than a name invented for it.
    figure, ax = plt.subplots()
    frame = _frame()
    ax.plot(frame["x"][:3], frame["y"][:3])
    schema = _schema(figure)

    assert "z" not in schema["axes"]
    assert all("z" not in point for series in schema["data"] for point in series)


def test_the_axes_own_legend_still_wins_over_the_figures():
    # `legend_of`'s first rule, reached through this read rather than
    # restated: one figure legend is taken to name *every* axes, so a panel
    # that has its own must not be renamed by it.
    figure, ax = plt.subplots()
    frame = _frame()
    ax.plot(frame["x"][:3], frame["y"][:3], label="own")
    ax.legend(title="mine")
    figure.legend([plt.Line2D([], [])], ["theirs"], title="not mine")
    schema = _schema(figure)

    assert schema["axes"]["z"] == {"label": "mine"}


def test_the_variables_name_is_trimmed_of_the_spacing_around_it():
    # Pre-existing, and pinned here because this change routes many more
    # charts through the read: a `z` label is announced beside every point,
    # and the padding a caller wrote for the drawn legend is not part of the
    # variable's name.
    figure, ax = plt.subplots()
    frame = _frame()
    ax.plot(frame["x"][:3], frame["y"][:3], label="own")
    ax.legend(title="  the group  ")
    schema = _schema(figure)

    assert schema["axes"]["z"] == {"label": "the group"}


def test_two_figure_legends_name_nothing_rather_than_one_of_them():
    # The ambiguity `legend_of` declines on. Picking either would name half
    # the chart wrongly and say nothing about which half.
    figure, ax = plt.subplots()
    frame = _frame()
    ax.plot(frame["x"][:3], frame["y"][:3])
    figure.legend([plt.Line2D([], [])], ["first"], title="one", loc="upper left")
    figure.legend([plt.Line2D([], [])], ["second"], title="two", loc="upper right")
    schema = _schema(figure)

    assert "z" not in schema["axes"]
