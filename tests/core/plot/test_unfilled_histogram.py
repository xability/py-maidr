"""`histplot(fill=False)` reads as the histogram its filled twin does (#583).

`fill` is a purely visual choice and changes no count, so the two spellings
have to say the same thing. That equality is the main assertion here: it
cannot be satisfied by inventing numbers, because the filled reading is
already pinned by its own tests.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import pytest
import seaborn as sns

import maidr
from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager
from maidr.exception import UnsupportedPlotError

VALUES = [1, 2, 2, 3, 3, 3, 8, 9]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"v": VALUES})


def _schemas(fig) -> list:
    return [plot.schema for plot in FigureManager.get_maidr(fig).plots]


def _draw(**kwargs):
    fig, ax = plt.subplots()
    sns.histplot(_frame(), bins=4, ax=ax, **kwargs)
    return fig


@pytest.mark.parametrize("element", ["step", "poly"])
@pytest.mark.parametrize("axis", ["x", "y"])
def test_unfilled_says_what_its_filled_twin_says(element: str, axis: str) -> None:
    filled = _schemas(_draw(**{axis: "v"}, element=element))
    unfilled = _schemas(_draw(**{axis: "v"}, element=element, fill=False))

    assert [s[MaidrKey.DATA] for s in filled] == [s[MaidrKey.DATA] for s in unfilled]
    assert [s.get(MaidrKey.ORIENTATION) for s in filled] == [
        s.get(MaidrKey.ORIENTATION) for s in unfilled
    ]


@pytest.mark.parametrize("element", ["step", "poly"])
def test_an_unfilled_outline_is_one_hist_layer(element: str) -> None:
    fig = _draw(x="v", element=element, fill=False)

    assert [plot.type for plot in FigureManager.get_maidr(fig).plots] == [PlotType.HIST]


@pytest.mark.parametrize("element", ["step", "poly"])
def test_the_counts_are_the_ones_the_data_has(element: str) -> None:
    """Bins 1-3, 3-5, 5-7, 7-9 over the sample hold 3, 3, 0 and 2."""
    fig = _draw(x="v", element=element, fill=False)

    data = _schemas(fig)[0][MaidrKey.DATA]
    assert [point["y"] for point in data] == [3.0, 3.0, 0.0, 2.0]
    assert [point["xMin"] for point in data] == [1.0, 3.0, 5.0, 7.0]
    assert [point["xMax"] for point in data] == [3.0, 5.0, 7.0, 9.0]


@pytest.mark.parametrize("element", ["step", "poly"])
def test_a_hue_split_gives_one_layer_per_group(element: str) -> None:
    frame = pd.DataFrame({"v": [1, 2, 3, 8, 9, 10], "g": ["a"] * 3 + ["b"] * 3})
    fig, ax = plt.subplots()
    sns.histplot(frame, x="v", hue="g", bins=3, element=element, fill=False, ax=ax)

    assert len(FigureManager.get_maidr(fig).plots) == 2


def test_a_stepped_outline_reads_uneven_bins_exactly() -> None:
    """It carries the edges themselves, so nothing has to be reconstructed."""
    fig, ax = plt.subplots()
    sns.histplot(_frame(), x="v", bins=[0, 1, 5, 10], element="step", fill=False, ax=ax)

    data = _schemas(fig)[0][MaidrKey.DATA]
    assert [point["xMin"] for point in data] == [0.0, 1.0, 5.0]
    assert [point["xMax"] for point in data] == [1.0, 5.0, 10.0]
    assert [point["y"] for point in data] == [0.0, 6.0, 2.0]


def test_an_uneven_poly_outline_is_declined_rather_than_invented() -> None:
    """It carries only the centres, and centres 0.5, 3.0, 7.5 do not say
    where the boundaries were. The same rule the filled poly already uses."""
    fig, ax = plt.subplots()
    sns.histplot(_frame(), x="v", bins=[0, 1, 5, 10], element="poly", fill=False, ax=ax)

    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)


def test_a_kde_overlay_is_not_read_as_a_histogram() -> None:
    """`kde=True` puts another `Line2D` on the same axes, and it is a density
    rather than a distribution of bins. A stepped outline is told from it by
    the drawstyle, which a density never has."""
    fig, ax = plt.subplots()
    sns.histplot(_frame(), x="v", bins=4, element="step", fill=False, kde=True, ax=ax)

    hist = [
        plot for plot in FigureManager.get_maidr(fig).plots if plot.type == PlotType.HIST
    ]
    assert len(hist) == 1
    assert [point["y"] for point in hist[0].schema[MaidrKey.DATA]] == [
        3.0,
        3.0,
        0.0,
        2.0,
    ]


def test_a_poly_outline_under_a_density_is_declined_rather_than_guessed() -> None:
    """Both are `default` drawstyle and differ only in vertex count, which
    `gridsize=` and the bin count both move -- so a threshold between them
    would be a guess, and a density announced as a distribution is worse than
    one left unread."""
    fig, ax = plt.subplots()
    sns.histplot(_frame(), x="v", bins=4, element="poly", fill=False, kde=True, ax=ax)

    # Nothing at all, which is what this combination already did and is not
    # made worse here: the outline is declined, and the density overlay is
    # registered only on the path a bar chart takes. The other three unfilled
    # combinations are read; this one stays as it was.
    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)


def test_the_two_kinds_of_line_really_do_interleave() -> None:
    """What rules out separating them by position. Pinned because the fix
    above rests on it."""
    frame = pd.DataFrame({"v": [1, 2, 3, 8, 9, 10], "g": ["a"] * 3 + ["b"] * 3})
    fig, ax = plt.subplots()
    sns.histplot(
        frame, x="v", hue="g", bins=3, element="step", fill=False, kde=True, ax=ax
    )

    stepped = [str(line.get_drawstyle()).startswith("steps") for line in ax.lines]
    assert stepped == [True, False, True, False]


def test_a_line_already_on_the_axes_is_not_claimed() -> None:
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3])
    sns.histplot(_frame(), x="v", bins=4, element="step", fill=False, ax=ax)

    kinds = sorted(plot.type.value for plot in FigureManager.get_maidr(fig).plots)
    assert kinds == ["hist", "line"]


@pytest.mark.parametrize("element", ["step", "poly"])
def test_the_chart_renders(element: str) -> None:
    fig = _draw(x="v", element=element, fill=False)

    assert len(maidr.render(fig)._repr_html_()) > 0
