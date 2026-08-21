"""
A multi-dataset ``ax.hist([a, b])`` raises before anything is read (#553).

Passing a list of datasets is the documented way to draw two distributions in
one call, and it killed the figure from the **plotting line**, not from render
or ``save_html``::

    ax.hist([np.zeros(10) + 1, np.zeros(10) + 50], bins=2)
    AttributeError: 'BarContainer' object has no attribute 'axes'

`Axes.hist` returns `(n, bins, patches)`, and `patches` is a single
`BarContainer` for one dataset but a **list** for several -- of containers for
``histtype="bar"`` and ``"barstacked"``, of `Polygon` lists for ``"step"`` and
``"stepfilled"``. `FigureManager.get_axes` treated any list as a list of
artists and read `.axes` off the first element, which neither has, so all four
histtypes raised.

Two things follow from the fix, and both are asserted here rather than
assumed:

- **one layer per dataset.** Reading one container would announce one
  distribution and silently drop the rest, which is the defect #527 fixed for
  a pair of separate calls.
- **nothing registered where there is no container.** The step histtypes
  create none, and the layer registered for them raised `ExtractionError` at
  render -- a pre-existing failure, unrelated to the list, filed as #555.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

from maidr.core.figure_manager import FigureManager
from maidr.exception import UnsupportedPlotError


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _counts(fig) -> list:
    """Every hist layer's per-bin counts, in registration order."""
    return [
        [point["y"] for point in plot.schema["data"]]
        for plot in FigureManager.get_maidr(fig).plots
    ]


def _two_datasets() -> list:
    """Ten in one bin, then four and six across both."""
    return [np.array([1.0] * 10), np.array([1.0] * 4 + [3.0] * 6)]


@pytest.mark.parametrize("histtype", ["bar", "barstacked"])
def test_a_multi_dataset_histogram_no_longer_raises(histtype):
    fig, ax = plt.subplots()

    ax.hist(_two_datasets(), bins=2, histtype=histtype)  # must not raise

    assert len(FigureManager.get_maidr(fig).plots) == 2


@pytest.mark.parametrize("histtype", ["step", "stepfilled"])
def test_a_step_histogram_no_longer_raises_either(histtype):
    # The list branch was only half of it: these two put *lists of Polygons*
    # in the list, so they raised on `'list' object has no attribute 'axes'`.
    fig, ax = plt.subplots()

    ax.hist(_two_datasets(), bins=2, histtype=histtype)  # must not raise

    # And nothing is registered, because there is no container to read. The
    # chart takes the static-image fallback rather than raising at render.
    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)


def test_each_dataset_is_announced_as_its_own_layer():
    fig, ax = plt.subplots()
    ax.hist(_two_datasets(), bins=2)

    assert _counts(fig) == [[10.0, 0.0], [4.0, 6.0]]


def test_a_stacked_histogram_announces_each_datasets_own_counts():
    # Measured rather than assumed: `barstacked` puts the stacking in the
    # bars' `bottom` and leaves each container's *heights* as its own
    # dataset's counts -- 10/0 and 4/6, not the cumulative 10/0 and 14/6 that
    # `n` reports. So the counts announced are right; only the fact that they
    # are stacked is not said.
    fig, ax = plt.subplots()
    ax.hist(_two_datasets(), bins=2, histtype="barstacked")

    assert _counts(fig) == [[10.0, 0.0], [4.0, 6.0]]


def test_a_single_dataset_histogram_is_unchanged():
    fig, ax = plt.subplots()
    ax.hist(np.array([1.0] * 10), bins=2)

    assert len(_counts(fig)) == 1


def test_a_step_histogram_renders_instead_of_dying():
    # The pre-existing half: a step histogram registered a layer that
    # `HistPlot` could not read, and `render` died on the whole figure.
    # Declining to register is not the same as reading it (#555), but a chart
    # that falls back to a picture beats one that raises.
    import maidr

    fig, ax = plt.subplots()
    ax.hist(np.array([1.0] * 10), bins=2, histtype="step")

    assert len(maidr.render(fig)._repr_html_()) > 0
