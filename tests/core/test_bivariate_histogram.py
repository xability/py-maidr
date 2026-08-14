"""A 2D histogram raised `StopIteration` and killed the render.

`sns.histplot(x=..., y=...)` is a **bivariate** histogram: seaborn draws it as
a `QuadMesh` of joint counts, not as bars. MAIDR registered it as `hist`
anyway, and `ContainerExtractorMixin.extract_container` then reached for the
first `BarContainer` on an axes that has none::

    return next(
        container for container in ax.containers
        if isinstance(container, container_type)
    )

Not an `ExtractionError` — a raw `StopIteration`, fatal to the whole figure
and naming nothing (#388).

    2D histplot alone                 ['hist']            ** StopIteration
    scatter + 2D histplot overlay     ['point', 'hist']   ** StopIteration
    jointplot(kind='hist')                                ** StopIteration
    jointplot(kind='kde')                                 ok
    jointplot(kind='scatter')                             ok

Two defects, and both had to go. `extract_container`'s two branches
disagreed — the list branch returned empty, the single branch raised — so the
`if plot is None` handling every caller opens with could never run. And
fixing only that turns `StopIteration` into `ExtractionError`, which is still
fatal: `hist` promises one bin per bar with a count, which a mesh has neither
of, so the layer must not be registered at all.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.container import BarContainer  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.mixin import ContainerExtractorMixin  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Two numeric columns, enough for a joint distribution."""
    rng = np.random.default_rng(20260814)
    return pd.DataFrame(
        {"v": rng.normal(10, 3, size=60), "w": rng.normal(5, 2, size=60)}
    )


def _layers(fig) -> list:
    """The plot types registered for a figure, or an empty list."""
    try:
        return [plot.type for plot in FigureManager.get_maidr(fig).plots]
    except KeyError:
        return []


def test_a_scatter_under_a_2d_histogram_still_renders() -> None:
    """The row that matters most: a good chart destroyed by its neighbour.

    The scatter reads perfectly well. It produced no HTML because a 2D
    histogram was drawn over it and registered a layer nothing could extract.
    """
    frame = _frame()
    fig, ax = plt.subplots()

    sns.scatterplot(data=frame, x="v", y="w", ax=ax)
    sns.histplot(data=frame, x="v", y="w", ax=ax)

    assert _layers(fig) == [PlotType.SCATTER]
    assert maidr.render(fig) is not None


def test_a_jointplot_of_histograms_renders() -> None:
    """A documented `jointplot` kind that produced nothing at all.

    Its central panel is the bivariate histogram; its marginals are ordinary
    1D ones, and those are what should be announced.
    """
    grid = sns.jointplot(data=_frame(), x="v", y="w", kind="hist")

    assert _layers(grid.figure) == [PlotType.HIST, PlotType.HIST]
    assert maidr.render(grid.figure) is not None


def test_a_one_dimensional_histogram_is_unchanged() -> None:
    """The control. Declining the bivariate case must cost the normal one
    nothing, since both arrive through the same patch."""
    fig, ax = plt.subplots()
    sns.histplot(data=_frame(), x="v", ax=ax)

    assert _layers(fig) == [PlotType.HIST]


def test_a_histogram_with_a_kde_overlay_is_unchanged() -> None:
    """The second control, because `sns_hist` gained an early return.

    `kde=True` registers a `smooth` alongside the `hist`, and that pass runs
    *after* the registration the early return skips — so a bivariate call must
    not reach it and a univariate one must still.
    """
    fig, ax = plt.subplots()
    sns.histplot(data=_frame(), x="v", kde=True, ax=ax)

    assert _layers(fig) == [PlotType.HIST, PlotType.SMOOTH]


def test_extract_container_returns_rather_than_raises() -> None:
    """The mixin's own contract, asserted directly.

    Both branches now agree that "none of that type" is a value, not an
    exception. This is the check that fails if the single-container branch
    goes back to a bare ``next()`` — which no behavioural test above would
    catch once the patch stops registering the layer that reached it.
    """
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [3, 2, 1])  # a line: no BarContainer anywhere

    assert ContainerExtractorMixin.extract_container(ax, BarContainer) is None
    assert (
        ContainerExtractorMixin.extract_container(ax, BarContainer, include_all=True)
        == []
    )


def test_extract_container_still_finds_the_first_of_several() -> None:
    """The behaviour the `next()` was there for, kept.

    Returning ``None`` on an empty match must not change which container is
    returned when there are some — the first, in the order the axes holds
    them.
    """
    fig, ax = plt.subplots()
    first = ax.bar(["a", "b"], [1.0, 2.0])
    ax.bar(["a", "b"], [3.0, 4.0], bottom=[1.0, 2.0])

    found = ContainerExtractorMixin.extract_container(ax, BarContainer)

    assert found is first
    assert len(
        ContainerExtractorMixin.extract_container(ax, BarContainer, include_all=True)
    ) == 2


def test_bars_already_on_the_axes_do_not_make_it_a_histogram() -> None:
    """The lie that would have sat next to the fixed crash.

    `_drew_bars` asks what *this call* added, not what the axes holds. Asked
    the second way, an axes that already has bars — a `barplot` drawn first —
    answers True for someone else's artists, `sns_hist` registers a `hist`,
    and `extract_container` hands back the first container on the axes. The
    layer then describes the **barplot's** bars with bin edges invented for
    them::

        registered: ['bar', 'hist']
          bar   [{'x': 'a', 'y': 8.67}, ...]
          hist  [{'y': 8.67, 'xMin': -0.4, 'xMax': 0.4}, ...]

    Right numbers, wrong chart, nothing raised — worse than the crash the
    decline was added to prevent.
    """
    frame = _frame()
    frame["g"] = ["a", "b", "c"] * 20
    fig, ax = plt.subplots()

    sns.barplot(data=frame, x="g", y="v", ax=ax)
    sns.histplot(data=frame, x="v", y="w", ax=ax)

    assert _layers(fig) == [PlotType.BAR]


def test_a_second_histogram_on_the_same_axes_still_registers() -> None:
    """The control for the diff: new bars are new bars.

    Snapshotting must decline only what added nothing. Two overlaid 1D
    histograms are two histograms, and each call adds its own container.
    """
    frame = _frame()
    fig, ax = plt.subplots()

    sns.histplot(data=frame, x="v", ax=ax)
    sns.histplot(data=frame, x="w", ax=ax)

    assert _layers(fig) == [PlotType.HIST, PlotType.HIST]


def test_a_histogram_drawn_without_an_explicit_axes_registers() -> None:
    """The snapshot has to find the axes seaborn will use, or find none.

    Without ``ax=``, seaborn draws on ``plt.gca()``. Resolving that before the
    call must not miss the axes (which would make the snapshot empty and let
    a stale container through) nor conjure one where a figure does not exist.
    """
    plt.close("all")
    sns.histplot(data=_frame(), x="v")

    assert _layers(plt.gcf()) == [PlotType.HIST]
