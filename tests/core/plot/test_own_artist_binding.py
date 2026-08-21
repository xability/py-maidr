"""
A layer reads whichever artist a search of its axes turns up first (#527).

Two heatmaps on one axes were both read from the first one's mesh, and the
audit that issue asked for found the identical defect in ``HistPlot``. Both
are fixed here, so this file covers the binding rather than one chart type.

``HeatPlot`` found its artist by searching the axes rather than by being told
which one it was registered for, so every heatmap on an axes resolved to the
same mesh. Measured on matplotlib 3.9.4 before the fix::

    ax.pcolormesh(np.arange(6).reshape(2, 3))          # 0..5
    ax.pcolormesh(np.arange(100, 106).reshape(2, 3))   # 100..105

    heat [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]]
    heat [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]]

Two layers, both the first mesh, nothing raised. The second chart's numbers
appeared nowhere and a reader navigating two layers heard the same values in
each with no way to tell one was a copy.

The layer is now bound to the artist its own call drew, the way
``ScatterPlot._own_points`` already was for #426. The fallback matters
separately and is asserted too: ``seaborn.heatmap`` returns an ``Axes`` rather
than its mesh, so the patch has to find it on the axes -- and must take the
**last** grid, not the first, because the call that is registering right now
drew the newest one.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn as sns
from matplotlib.container import BarContainer

from maidr.core.figure_manager import FigureManager


def _bins(points) -> list:
    """Each bin's lower edge, which is what says *which* distribution it is."""
    return [point["xMin"] for point in points]


def _points(fig) -> list:
    """Every heat layer's grid of values, in registration order."""
    maidr = FigureManager.get_maidr(fig)
    return [plot.schema["data"]["points"] for plot in maidr.plots]


def _hist_points(fig) -> list:
    """Every hist layer's bins, in registration order."""
    maidr = FigureManager.get_maidr(fig)
    return [plot.schema["data"] for plot in maidr.plots]


def _elements(fig) -> list:
    """The artist each heat layer will highlight through."""
    maidr = FigureManager.get_maidr(fig)
    return [plot.elements[0] if plot.elements else None for plot in maidr.plots]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def test_two_meshes_on_one_axes_each_read_their_own_values():
    fig, ax = plt.subplots()
    ax.pcolormesh(np.arange(6).reshape(2, 3))
    ax.pcolormesh(np.arange(100, 106).reshape(2, 3))

    assert _points(fig) == [
        [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]],
        [[100.0, 101.0, 102.0], [103.0, 104.0, 105.0]],
    ]


def test_two_images_on_one_axes_each_read_their_own_values():
    # `imshow` returns an `AxesImage` rather than a mesh, and reaches the same
    # branch by a different type -- which is the point of naming all three.
    fig, ax = plt.subplots()
    ax.imshow(np.arange(6).reshape(2, 3))
    ax.imshow(np.arange(100, 106).reshape(2, 3))

    assert _points(fig) == [
        [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]],
        [[100.0, 101.0, 102.0], [103.0, 104.0, 105.0]],
    ]


def test_a_pcolor_beside_a_pcolormesh_keeps_them_apart():
    # `pcolor` draws a `PolyQuadMesh` and `pcolormesh` a `QuadMesh`, so this
    # pairing would survive a fix that only told two artists of one class
    # apart.
    fig, ax = plt.subplots()
    ax.pcolor(np.arange(6).reshape(2, 3))
    ax.pcolormesh(np.arange(100, 106).reshape(2, 3))

    assert _points(fig) == [
        [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]],
        [[100.0, 101.0, 102.0], [103.0, 104.0, 105.0]],
    ]


def test_a_seaborn_heatmap_beside_a_mesh_reads_its_own_values():
    # `seaborn.heatmap` returns the axes, so the artist has to be found rather
    # than taken from the return value. Taking the *first* grid -- which is
    # what `extract_scalar_mappable` answers -- would hand seaborn's layer the
    # mesh drawn before it.
    fig, ax = plt.subplots()
    ax.pcolormesh(np.arange(6).reshape(2, 3))
    sns.heatmap(np.arange(100, 106).reshape(2, 3), ax=ax)

    assert _points(fig) == [
        [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]],
        [[100.0, 101.0, 102.0], [103.0, 104.0, 105.0]],
    ]


def test_each_layer_highlights_the_grid_it_announces():
    # The blind spot: audio, text and braille would all read correctly off the
    # fix above while the wrong mesh lit up, because the element registered
    # for highlighting is the same artist the values were read from. Asserted
    # as identity against the artists the calls returned.
    fig, ax = plt.subplots()
    first = ax.pcolormesh(np.arange(6).reshape(2, 3))
    second = ax.pcolormesh(np.arange(100, 106).reshape(2, 3))

    assert _elements(fig) == [first, second]


def test_one_heatmap_alone_is_unchanged():
    fig, ax = plt.subplots()
    ax.pcolormesh(np.arange(6).reshape(2, 3))

    assert _points(fig) == [[[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]]]


def test_a_layer_told_nothing_still_finds_the_axes_heatmap():
    # The documented fallback, exercised directly: a producer that registers a
    # heatmap without naming the artist keeps the behaviour it has always had.
    from maidr.core.plot.heatmap import HeatPlot

    fig, ax = plt.subplots()
    ax.pcolormesh(np.arange(6).reshape(2, 3))

    assert HeatPlot(ax).schema["data"]["points"] == [
        [0.0, 1.0, 2.0],
        [3.0, 4.0, 5.0],
    ]


def test_a_layer_told_a_grid_that_is_not_one_falls_back_rather_than_breaking():
    # Guarded on the type, not on presence -- the same rule
    # `ScatterPlot._own_points` follows, because the seaborn wrapper hands the
    # axes through the same keyword.
    from maidr.core.plot.heatmap import DRAWN_GRID, HeatPlot

    fig, ax = plt.subplots()
    ax.pcolormesh(np.arange(6).reshape(2, 3))

    plot = HeatPlot(ax, **{DRAWN_GRID: ax})
    assert plot.schema["data"]["points"] == [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]]


# ---------------------------------------------------------------------------
# The audit the issue asked for
#
# "Anything that resolves its artist from `self.ax` at extraction time has the
# same exposure whenever two of a kind share an axes." Measured across the
# extractors that do: two `ax.bar()` calls read correctly (the patch already
# hands each layer its own container), and so do two `ax.plot()` calls. Two
# `ax.hist()` calls did not -- the identical defect, in `HistPlot`:
#
#     ax.hist(np.zeros(10) + 1, bins=2)
#     ax.hist(np.zeros(10) + 50, bins=2)
#
#     hist [{'x': 0.75, 'xMin': 0.5, ...}, ...]
#     hist [{'x': 0.75, 'xMin': 0.5, ...}, ...]   <- the first one's bins
#
# so it is fixed here rather than filed, being the same defect in the same
# family.
# ---------------------------------------------------------------------------


def test_two_histograms_on_one_axes_each_read_their_own_bins():
    fig, ax = plt.subplots()
    ax.hist(np.zeros(10) + 1, bins=2)
    ax.hist(np.zeros(10) + 50, bins=2)

    first, second = _hist_points(fig)
    assert _bins(first) == [0.5, 1.0]
    assert _bins(second) == [49.5, 50.0]


def test_a_seaborn_histogram_beside_a_matplotlib_one_reads_its_own_bins():
    # The seaborn wrapper returns the axes, so it finds its container by
    # diffing the axes against a snapshot taken before the call -- which it
    # already did to decide whether to register at all. It now hands the
    # container it found to the layer instead of letting the layer search.
    fig, ax = plt.subplots()
    ax.hist(np.zeros(10) + 1, bins=2)
    sns.histplot(x=np.zeros(10) + 50.0, bins=2, ax=ax)

    first, second = _hist_points(fig)
    assert _bins(first) == [0.5, 1.0]
    assert _bins(second)[0] == pytest.approx(49.5, abs=1.0)
    assert _bins(second)[0] > 40


def test_one_histogram_alone_is_unchanged():
    fig, ax = plt.subplots()
    ax.hist(np.zeros(10) + 1, bins=2)

    assert _bins(_hist_points(fig)[0]) == [0.5, 1.0]


def test_two_identical_histograms_are_still_told_apart():
    # Two calls with the same numbers: the containers are distinct objects
    # holding distinct artists. Measured, they compare *unequal* -- a
    # `BarContainer` is a tuple over `Rectangle`s, which compare by identity --
    # so a value comparison would separate them too. Pinned because the
    # snapshot diff is what decides which container a layer is handed, and a
    # pair that a future matplotlib gave value semantics to would collapse
    # into one and hand the second layer the first's bars.
    fig, ax = plt.subplots()
    sns.histplot(x=np.zeros(10) + 1.0, bins=2, ax=ax)
    sns.histplot(x=np.zeros(10) + 1.0, bins=2, ax=ax)

    containers = [c for c in ax.containers if isinstance(c, BarContainer)]
    assert len(containers) == 2

    bound = [plot._own_bars for plot in FigureManager.get_maidr(fig).plots]
    assert bound[0] is containers[0]
    assert bound[1] is containers[1]


def test_a_hue_grouped_histogram_gives_each_group_its_own_layer():
    # This asserted **one** layer when it was written, on the reasoning that a
    # hue's groups share one binning and so the container the patch picked was
    # unobservable. The binning is shared -- both rows below still open at
    # 1.0 and 25.5 -- but the counts are not, and reading one container
    # announced one distribution while the other stayed drawn and unspoken
    # (#558).
    #
    # What this case is really about is unchanged: a layer reads the container
    # its own call drew. There are simply two of them.
    frame = pd.DataFrame(
        {"v": [1, 1, 1, 50, 50, 50], "g": ["a", "a", "a", "b", "b", "b"]}
    )
    fig, ax = plt.subplots()
    sns.histplot(frame, x="v", hue="g", bins=2, ax=ax)

    layers = _hist_points(fig)
    assert len(layers) == 2
    assert [_bins(layer) for layer in layers] == [[1.0, 25.5], [1.0, 25.5]]

    # Three observations at 1 in one group and three at 50 in the other, which
    # is the half the old reading threw away. Group `b` is drawn first here:
    # seaborn's container order is not its hue order, which is why #558 names
    # each layer by the colour of the swatch that claims it rather than by
    # where it sits.
    assert [[point["y"] for point in layer] for layer in layers] == [
        [0.0, 3.0],
        [3.0, 0.0],
    ]
    names = [plot.schema.get("name") for plot in FigureManager.get_maidr(fig).plots]
    assert names == ["b", "a"]
