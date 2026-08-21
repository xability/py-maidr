"""
`ax.hist(histtype="step")` is registered but cannot be read (#555).

A step-outlined histogram registered a `hist` layer and then raised when that
layer was rendered, taking the whole figure with it::

    ax.hist(np.array([1.0] * 10), bins=2, histtype="step")
    maidr.render(fig)
    ExtractionError: Error extracting data for hist plot type from <class 'NoneType'>.

`HistPlot` reads a `BarContainer`, and only two of matplotlib's four histtypes
make one::

    histtype       returns                 ax.containers
    bar            BarContainer            1
    barstacked     BarContainer            1
    step           [Polygon]               0
    stepfilled     [Polygon]               0

#553 stopped the crash by registering nothing where there was no container, so
a step histogram fell back to a static image. This reads it instead.

Nothing is recovered from the outline. `Axes.hist` returns `(n, bins, patches)`
whatever the histtype, and the first two *are* the counts and the edges — so
the patch hands them over and `StepHistPlot` reads them, through the same
`bins_to_points` that `StairsPlot` uses for the pair a `StepPatch` carries.
Two spellings of one chart, announced identically.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _layers(fig) -> list:
    return FigureManager.get_maidr(fig).plots


def _counts(fig) -> list:
    """Every hist layer's per-bin counts, in registration order."""
    return [
        [point["y"] for point in plot.schema["data"]] for plot in _layers(fig)
    ]


def _edges(fig, index: int = 0) -> list:
    """One layer's bin boundaries."""
    points = _layers(fig)[index].schema["data"]
    return [point["xMin"] for point in points] + [points[-1]["xMax"]]


def _one() -> np.ndarray:
    return np.array([1.0] * 10)


def _two() -> list:
    return [np.array([1.0] * 10), np.array([1.0] * 4 + [3.0] * 6)]


@pytest.mark.parametrize("histtype", ["step", "stepfilled"])
def test_a_step_histogram_is_read_rather_than_dropped(histtype):
    fig, ax = plt.subplots()
    ax.hist(_one(), bins=2, histtype=histtype)

    assert len(_layers(fig)) == 1
    assert _counts(fig) == [[0.0, 10.0]]


@pytest.mark.parametrize("histtype", ["step", "stepfilled"])
def test_a_step_histogram_renders_without_raising(histtype):
    # The regression: this raised `ExtractionError` from inside `render`, so
    # the whole figure died rather than one layer.
    fig, ax = plt.subplots()
    ax.hist(_one(), bins=2, histtype=histtype)

    assert len(maidr.render(fig)._repr_html_()) > 0


def test_a_step_histogram_reads_the_same_bins_a_bar_one_does():
    # The point of routing both through `bins_to_points`: the same data drawn
    # two ways is the same chart, and a reader should not be able to tell
    # which histtype the author picked from what they hear.
    bar_fig, bar_ax = plt.subplots()
    bar_ax.hist(_one(), bins=2)

    step_fig, step_ax = plt.subplots()
    step_ax.hist(_one(), bins=2, histtype="step")

    assert _counts(step_fig) == _counts(bar_fig)
    assert _edges(step_fig) == _edges(bar_fig)


def test_a_multi_dataset_step_histogram_is_one_layer_per_dataset():
    # The same rule the container branch follows (#553): reading one would
    # announce a single distribution and drop the rest.
    fig, ax = plt.subplots()
    ax.hist(_two(), bins=2, histtype="step")

    assert _counts(fig) == [[10.0, 0.0], [4.0, 6.0]]


def test_every_histtype_announces_the_same_two_distributions():
    # The strongest form of the previous two, across all four spellings.
    readings = {}
    for histtype in ("bar", "barstacked", "step", "stepfilled"):
        fig, ax = plt.subplots()
        ax.hist(_two(), bins=2, histtype=histtype)
        readings[histtype] = _counts(fig)

    assert readings == {
        "bar": [[10.0, 0.0], [4.0, 6.0]],
        "barstacked": [[10.0, 0.0], [4.0, 6.0]],
        "step": [[10.0, 0.0], [4.0, 6.0]],
        "stepfilled": [[10.0, 0.0], [4.0, 6.0]],
    }


def test_a_step_histogram_declines_highlighting():
    # For the reason `StairsPlot` declines it: the outline is a single element
    # covering every bin, so a selector naming it would outline the whole
    # histogram at every bin and tell a low-vision reader nothing about which
    # bin they are on. Announcing the bins is still a strict gain -- the chart
    # was an error before, so no highlight is being taken away.
    fig, ax = plt.subplots()
    ax.hist(_one(), bins=2, histtype="step")

    layer = _layers(fig)[0]
    assert layer.schema.get("selectors") in (None, "", [])


def test_a_horizontal_step_histogram_keeps_its_orientation():
    fig, ax = plt.subplots()
    ax.hist(_one(), bins=2, histtype="step", orientation="horizontal")

    assert _layers(fig)[0].schema["orientation"] == "horz"
