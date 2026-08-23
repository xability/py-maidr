"""A drawing call that produced no artist registers nothing (#623).

Carried across from xability/r-maidr#232, which found the same defect on the R
side. Measured here before the fix, four real observations plus a second call
drawing nothing::

    scatter + empty scatter          point(4) point(0)
    bar     + empty bar              ValueError: No plot found.
    only an empty scatter            point(0)

The bar row is the one that matters most: the exception came out of the
caller's own ``ax.bar()`` line, not out of ``maidr.render()``, so ``import
maidr`` decided whether an existing script's plotting call returned at all.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import pytest

import maidr
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import drew_nothing


def _layers(figure):
    """The layers a figure registered, as ``type(n)`` strings in order."""
    plots = FigureManager.get_maidr(figure).plots
    sizes = []
    for plot in plots:
        data = plot.schema.get("data")
        if isinstance(data, list) and data and isinstance(data[0], list):
            sizes.append(f"{plot.schema['type'].value}({len(data)}x{len(data[0])})")
        else:
            sizes.append(f"{plot.schema['type'].value}({len(data or [])})")
    return sizes


@pytest.mark.parametrize(
    "draw_empty, kind",
    [
        pytest.param(lambda ax: ax.scatter([], []), "scatter", id="scatter"),
        pytest.param(lambda ax: ax.bar([], []), "bar", id="bar"),
        pytest.param(lambda ax: ax.plot([], []), "line", id="line"),
    ],
)
def test_a_call_that_drew_nothing_adds_no_layer(draw_empty, kind):
    """The chart reads as though the empty call had not been written."""
    figure, axes = plt.subplots()
    axes.scatter([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0])
    draw_empty(axes)
    maidr.render(figure)._repr_html_()

    assert _layers(figure) == ["point(4)"]


def test_an_empty_bar_does_not_raise_out_of_the_caller_s_own_call():
    """The sharp end of #623.

    `ax.bar([], [])` returns a `BarContainer` holding nothing, so
    `FigureManager.get_axes()` found no axes on it and `create_maidr` raised
    `ValueError("No plot found.")` -- from `ax.bar()`, while the user was
    drawing, rather than from `maidr.render()` while they were saving. The
    chart was fine: rendering after catching the error succeeded.

    A decline is a reading decision; an exception is a broken call. That is
    the argument xability/r-maidr#230 settled on the R side.
    """
    figure, axes = plt.subplots()
    axes.bar(["a", "b"], [1.0, 2.0])

    # The assertion is that this line returns at all.
    container = axes.bar([], [])
    assert len(container) == 0

    maidr.render(figure)._repr_html_()
    assert _layers(figure) == ["bar(2)"]


def test_an_empty_seaborn_scatter_does_not_announce_the_previous_call_s_points():
    """The seaborn half of #623, and the worst of the three.

    `seaborn.scatterplot` returns the *axes* rather than its collection, so
    `drew_nothing` cannot read it and the empty call went on to sweep the
    axes for a `PathCollection` -- finding the *first* call's. Measured
    before::

        layer 0: point [{x:1,y:2}, {x:2,y:4}, {x:3,y:6}, {x:4,y:8}]
        layer 1: point [{x:1,y:2}, {x:2,y:4}, {x:3,y:6}, {x:4,y:8}]
        collections on axes: 1

    Not an empty layer -- a *wrong* one. A reader was offered the same four
    points twice, under two layers, with nothing to say they were the same.

    Told apart by the collection count, since a call that drew points adds
    one and a call that drew none adds none.
    """
    import seaborn as sns

    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "y": [2.0, 4.0, 6.0, 8.0]})
    figure, axes = plt.subplots()
    sns.scatterplot(data=frame, x="x", y="y", ax=axes)
    sns.scatterplot(data=frame.iloc[0:0], x="x", y="y", ax=axes)
    maidr.render(figure)._repr_html_()

    assert len(axes.collections) == 1
    assert _layers(figure) == ["point(4)"]


def test_two_real_seaborn_scatters_still_register_two_layers():
    """The guard rail on the count. Two calls that each drew points must
    still give two layers -- a rule keyed on "the axes already has a
    collection" rather than on the count changing would have folded them
    together, which is a worse failure than the one being fixed.
    """
    import seaborn as sns

    first = pd.DataFrame({"x": [1.0, 2.0], "y": [1.0, 2.0]})
    second = pd.DataFrame({"x": [3.0, 4.0], "y": [9.0, 16.0]})
    figure, axes = plt.subplots()
    sns.scatterplot(data=first, x="x", y="y", ax=axes)
    sns.scatterplot(data=second, x="x", y="y", ax=axes)
    maidr.render(figure)._repr_html_()

    assert len(axes.collections) == 2
    assert _layers(figure) == ["point(2)", "point(2)"]


def test_a_chart_that_is_only_an_empty_call_falls_back_to_an_image():
    """No layers is not an interactive chart with nothing in it.

    r-maidr states the reason at its own guard: a chart announcing itself as
    interactive with nothing in it is worse than an image, because an image at
    least says what it is. Here it comes out of the fallback #443 established
    rather than a guard of its own -- nothing registers, so there is no
    supported plot, so the figure renders as a picture.
    """
    figure, axes = plt.subplots()
    axes.scatter([], [])

    html = maidr.render(figure)._repr_html_()
    assert "maidr-data" not in html
    assert "base64" in html


@pytest.mark.parametrize(
    "make, empty",
    [
        pytest.param(lambda ax: ax.bar([], []), True, id="empty-bar"),
        pytest.param(lambda ax: ax.bar(["a"], [1.0]), False, id="drawn-bar"),
        pytest.param(lambda ax: ax.scatter([], []), True, id="empty-scatter"),
        pytest.param(lambda ax: ax.scatter([1.0], [1.0]), False, id="drawn-scatter"),
        pytest.param(lambda ax: ax.plot([], []), True, id="empty-line"),
        pytest.param(lambda ax: ax.plot([1.0], [1.0]), False, id="drawn-line"),
    ],
)
def test_drew_nothing_reads_the_artists_whose_emptiness_is_unambiguous(make, empty):
    """`ax.plot` returns a *list*, which is why the list branch is not
    decoration: a list drew nothing when every artist in it did."""
    _, axes = plt.subplots()
    assert drew_nothing(make(axes)) is empty


def test_drew_nothing_declines_to_guess():
    """Everything it does not recognise registers as before, which is what
    makes this additive rather than a new way to lose a layer.

    An `Axes` is the case that matters: `seaborn.scatterplot` returns one
    rather than its collection, so what it drew cannot be read off its return
    value at all -- and the seaborn half of #623 stays open because of it.
    """
    _, axes = plt.subplots()

    assert drew_nothing(axes) is False
    assert drew_nothing(None) is False
    assert drew_nothing({}) is False
    assert drew_nothing("not an artist") is False
