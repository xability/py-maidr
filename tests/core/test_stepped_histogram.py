"""`sns.histplot(element="step")` draws a histogram, and it was read as nothing.

`element="bars"` leaves a `BarContainer` and reads as `hist`. `element="step"`
and `element="poly"` draw the *same distribution* as a single closed
`PolyCollection` outline, so `HistPlot`'s container lookup finds nothing and
`_drew_bars` answers no -- the third branch of the decline #522 fixed for the
bivariate mesh, measured::

    element=bars   containers=[BarContainer]     -> ['hist']
    element=step   collections=[PolyCollection]  -> nothing
    element=poly   collections=[PolyCollection]  -> nothing

The two spellings differ in how much of the reading is exact.

**`step` traces the bin edges.** Its ring walks the baseline left to right, up
the right-hand edge and back along the tops, so every edge is visited going out
and every count is held coming back. An empty bin survives that: the outward
leg still walks through it, where the return leg runs flat across a whole run
of them and could not tell one wide gap from two narrow ones.

**`poly` traces the bin centres**, and the edges are not in the drawing at all.
They come back from the spacing, which is exact when the bins are even and
impossible when they are not -- `bins=[0, 1, 5, 10]` gives centres 0.5, 3.0 and
7.5, and gaps of 2.5 and 4.5 do not say where the boundaries were.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.exception import UnsupportedPlotError  # noqa: E402
from maidr.patch import histogram as patch_histogram  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


#: A sample with no ties, so the counts are lopsided and a transposed or
#: mis-paired reading cannot pass by symmetry.
SAMPLE = np.random.default_rng(0).normal(size=200)

#: Ten at one end and twenty at the other, so the two middle bins are empty.
GAPPED = np.concatenate([np.full(10, 0.1), np.full(20, 3.9)])

#: Author-set thresholds, so the bins are not evenly spaced.
UNEVEN = np.concatenate([np.full(5, 0.5), np.full(9, 2.5), np.full(3, 7.0)])


def _layers(fig):
    """The layers registered for a figure, or an empty list when there are none."""
    try:
        return FigureManager.get_maidr(fig).plots
    except UnsupportedPlotError:
        return []


def _flat(bins):
    """The bins as one flat list, which is what ``approx`` compares cleanly."""
    return [value for triple in bins for value in triple]


def _vertical_bins(fig, index: int = 0):
    return [
        (point["xMin"], point["xMax"], point["y"])
        for point in _layers(fig)[index].schema[MaidrKey.DATA]
    ]


def _horizontal_bins(fig, index: int = 0):
    return [
        (point["yMin"], point["yMax"], point["x"])
        for point in _layers(fig)[index].schema[MaidrKey.DATA]
    ]


def _drawn(sample, element: str, **kwargs):
    fig, ax = plt.subplots()
    sns.histplot(x=sample, element=element, ax=ax, **kwargs)
    return fig


@pytest.mark.parametrize("element", ["step", "poly"])

def test_an_outlined_histogram_is_read_at_all(element: str):
    fig = _drawn(SAMPLE, element, bins=4)

    assert [layer.type for layer in _layers(fig)] == [PlotType.HIST]


@pytest.mark.parametrize("element", ["step", "poly"])
def test_an_outline_and_the_bars_describe_the_same_distribution(element: str):
    # The point of the change: the same data drawn three ways has to come back
    # as one reading, not three that resemble each other.
    outlined = _drawn(SAMPLE, element, bins=4)
    barred = _drawn(SAMPLE, "bars", bins=4)

    assert _vertical_bins(outlined) == _vertical_bins(barred)


def test_a_step_outline_keeps_the_bins_nothing_landed_in():
    # The return leg runs flat across the two empty bins and could not tell
    # one wide gap from two narrow ones. The outward leg walks every edge, so
    # the bins survive -- and a reader sweeping the distribution hears the two
    # zeroes rather than a hole.
    fig = _drawn(GAPPED, "step", bins=4)

    # `approx`, because the edges are the drawing's own floats: seaborn
    # divides the range and matplotlib writes what that division gave, so 0.1
    # arrives as 0.10000000000000003. Rounding them here would assert a
    # tidiness the chart does not have.
    assert _flat(_vertical_bins(fig)) == pytest.approx(
        [0.1, 1.05, 10.0, 1.05, 2.0, 0.0, 2.0, 2.95, 0.0, 2.95, 3.9, 20.0]
    )


def test_a_step_outline_reads_author_set_thresholds():
    # The edges are walked rather than reconstructed, so bins that are not
    # evenly spaced come back exactly.
    fig = _drawn(UNEVEN, "step", bins=[0, 1, 5, 10])

    assert _flat(_vertical_bins(fig)) == pytest.approx(
        [0.0, 1.0, 5.0, 1.0, 5.0, 9.0, 5.0, 10.0, 3.0]
    )


def test_a_poly_outline_with_uneven_bins_is_declined():
    # Its centres are 0.5, 3.0 and 7.5, and gaps of 2.5 and 4.5 do not say
    # where the boundaries were. Declined *before* a layer exists, so the
    # chart falls back rather than carrying an empty row (#421).
    fig = _drawn(UNEVEN, "poly", bins=[0, 1, 5, 10])

    assert _layers(fig) == []


def test_a_horizontal_outline_runs_its_bins_up_the_y_axis():
    fig, ax = plt.subplots()
    sns.histplot(y=SAMPLE, element="step", ax=ax, bins=3)

    schema = _layers(fig)[0].schema
    assert schema[MaidrKey.ORIENTATION] == "horz"
    # And it is the same distribution the bars give the other way round.
    barred = plt.subplots()
    sns.histplot(y=SAMPLE, element="bars", ax=barred[1], bins=3)
    assert _horizontal_bins(fig) == _horizontal_bins(barred[0])


def test_each_hue_level_is_its_own_histogram():
    # One outline per series, each an independent count over the same bins,
    # which is what `hist` describes. "The collection on this Axes" would read
    # the first series once per layer.
    rng = np.random.default_rng(1)
    groups = np.where(rng.random(len(SAMPLE)) < 0.5, "a", "b")
    fig, ax = plt.subplots()
    sns.histplot(x=SAMPLE, hue=groups, element="step", ax=ax, bins=3)

    layers = _layers(fig)
    assert [layer.type for layer in layers] == [PlotType.HIST, PlotType.HIST]
    counts = [[low_high_count[2] for low_high_count in _vertical_bins(fig, i)]
              for i in range(2)]
    assert counts[0] != counts[1]
    # Together they account for every observation.
    assert sum(counts[0]) + sum(counts[1]) == len(SAMPLE)


def test_a_one_bin_step_is_not_mistaken_for_a_three_bin_polygon():
    # Their rings are the same length -- 4k+5 and 2k+3 collide at nine -- so
    # the vertex count alone is not decisive. What separates them is how many
    # distinct positions the ring visits along the binned axis: a step walks
    # every edge, a poly visits every centre.
    fig = _drawn(SAMPLE, "step", bins=1)

    bins = _vertical_bins(fig)

    assert len(bins) == 1
    # One bin holds everything, and it spans the whole sample.
    low, high, count = bins[0]
    assert count == float(len(SAMPLE))
    assert low == pytest.approx(SAMPLE.min())
    assert high == pytest.approx(SAMPLE.max())


def test_a_three_bin_polygon_is_not_mistaken_for_a_one_bin_step():
    fig = _drawn(SAMPLE, "poly", bins=3)

    assert len(_vertical_bins(fig)) == 3
    assert sum(count for _, _, count in _vertical_bins(fig)) == float(len(SAMPLE))


def test_an_outlined_histogram_announces_its_bins_but_highlights_none():
    # One `<path>` for the whole outline, as `Axes.stairs` has. A selector
    # matching it would light the entire distribution up at every bin, which
    # tells a low-vision reader nothing about where they are.
    fig = _drawn(SAMPLE, "step", bins=4)

    schema = _layers(fig)[0].schema
    assert len(schema[MaidrKey.DATA]) == 4
    assert MaidrKey.SELECTOR not in schema


def test_bars_still_read_through_the_container_they_always_did():
    fig = _drawn(SAMPLE, "bars", bins=4)

    assert [layer.type for layer in _layers(fig)] == [PlotType.HIST]
    assert len(_vertical_bins(fig)) == 4


def test_the_artist_fill_between_returns_is_one_this_reads():
    """
    Whatever ``fill_between`` draws on *this* matplotlib is an outline here.

    This is the guard that was missing, and the one that would have caught
    #543 before it shipped rather than in CI. seaborn draws
    ``element="step"`` and ``element="poly"`` through ``Axes.fill_between``,
    and matplotlib 3.10 gave that method a ``PolyCollection`` subclass of its
    own -- so the reader's exact-type check saw a plain ``PolyCollection`` on
    3.9 and nothing at all on 3.10 and later. Every test in this file passed
    on the development interpreter and eleven of them failed on the other
    three.

    Asked of the artist matplotlib actually returns rather than of a version
    number, so it keeps holding when the next release renames the class
    again. Nothing here goes through seaborn: the point is what the *drawing
    primitive* returns, and a seaborn-shaped test would fail for a dozen
    other reasons first.
    """
    fig, ax = plt.subplots()
    band = ax.fill_between([0.0, 1.0, 2.0], [0.0, 0.0, 0.0], [1.0, 2.0, 1.0])
    plt.close(fig)

    assert type(band) in patch_histogram._OUTLINE_TYPES, (
        f"fill_between returns {type(band).__name__}, which the outline "
        "reader does not recognise, so a stepped histogram reads as nothing"
    )
