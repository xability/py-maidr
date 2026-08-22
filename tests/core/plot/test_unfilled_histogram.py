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


@pytest.mark.parametrize("element", ["step", "poly"])
def test_each_hue_group_carries_the_name_its_colour_is_given(element: str) -> None:
    """Two layers of a kind need telling apart, which is what #828 added.

    Counting the layers is not enough on its own: the patch matches each
    outline's colour against the legend swatch that names it, and a layer
    that computed the name and dropped it on the way to the schema counts
    the same as one that carries it. Measured on the first draft, which
    called ``HistPlot.__init__`` with the axes alone: both layers came out
    ``name=None`` while the patch had a name for each.

    The names come out in seaborn's own draw order, which is the reverse of
    the legend's for a hue-grouped histogram.
    """
    frame = pd.DataFrame({"v": [1, 2, 3, 8, 9, 10], "g": ["a"] * 3 + ["b"] * 3})
    fig, ax = plt.subplots()
    sns.histplot(frame, x="v", hue="g", bins=3, element=element, fill=False, ax=ax)

    assert [schema.get(MaidrKey.NAME) for schema in _schemas(fig)] == ["b", "a"]


# Counts 2 and 5 over two bins, and 1/2/3/4 over four: both frames make the
# *counts* column ascend, and the four-bin one makes it ascend by an even
# step as well. A `poly` outline repeats no value, so on a `y=` chart both of
# its columns then read as bins and the drawing cannot say which is which.
CLIMBING_TWO = [0.1, 0.2, 0.6, 0.7, 0.8, 0.9, 0.95]
CLIMBING_FOUR = [0.0, 0.3, 0.4, 0.55, 0.6, 0.65, 0.8, 0.85, 0.9, 1.0]


@pytest.mark.parametrize("element", ["step", "poly"])
@pytest.mark.parametrize(
    ("values", "bins"), [(CLIMBING_TWO, 2), (CLIMBING_FOUR, 4)], ids=["two", "four"]
)
def test_a_horizontal_outline_whose_counts_climb_is_not_read_transposed(
    element: str, values: list, bins: int
) -> None:
    """The counts are not the axis, however much they look like one.

    Measured on the first draft, which took whichever column ascended first::

        sns.histplot(df, y="v", bins=2, element="poly", fill=False)
        orientation 'vert', xMin 0.5, xMax 3.5, y 0.3125

    The bin edges were built out of the counts 2 and 5, and the bin centre
    0.3125 was announced as the count. Silently transposed, which is the one
    outcome this reading is meant not to have.

    Pinned against the filled twin, which reads the same chart from a
    ``PolyCollection`` that carries a baseline and so was never ambiguous.
    """
    frame = pd.DataFrame({"v": values})

    def draw(**kwargs):
        fig, ax = plt.subplots()
        sns.histplot(frame, y="v", bins=bins, ax=ax, element=element, **kwargs)
        return fig

    filled = _schemas(draw())
    unfilled = _schemas(draw(fill=False))

    assert [s.get(MaidrKey.ORIENTATION) for s in unfilled] == ["horz"]
    assert [s[MaidrKey.DATA] for s in unfilled] == [s[MaidrKey.DATA] for s in filled]
    # The bins run up y and the counts sit on x, not the other way about.
    for point in unfilled[0][MaidrKey.DATA]:
        assert point["yMin"] < point["yMax"]
        assert point["yMax"] == pytest.approx(max(values), abs=1e-9) or point[
            "yMax"
        ] < max(values)
        assert point["x"] == int(point["x"])


def test_an_outline_that_reads_either_way_declines_when_nothing_says_which() -> None:
    """Both columns are bins, so without the caller there is no answer.

    The tie-break is the orientation the patch hands over; a reader that has
    none is in the position the first draft was in, and the rule there is the
    one an uneven ``poly`` already follows -- decline rather than pick.
    """
    from matplotlib.lines import Line2D

    from maidr.core.plot.outlined_histogram import _read_line

    # Counts 1..4 against centres 0.125..0.875: both ascend, both evenly.
    line = Line2D([1.0, 2.0, 3.0, 4.0], [0.125, 0.375, 0.625, 0.875])

    assert _read_line(line, None) is None
    assert _read_line(line, True)[0] is True
    assert _read_line(line, False)[0] is False


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
