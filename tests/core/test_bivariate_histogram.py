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
from maidr.util.mixin import (  # noqa: E402
    ContainerExtractorMixin,
    ScalarMappableExtractorMixin,
)


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

    # The mesh is read as the heatmap it is (#522). It used to be nothing at
    # all: `hist` was declined, correctly, and the `heat` the inner
    # `pcolormesh` would have registered had been suppressed by the recursion
    # guard the decline made pointless.
    assert _layers(fig) == [PlotType.SCATTER, PlotType.HEAT]
    assert maidr.render(fig) is not None


def test_a_jointplot_of_histograms_renders() -> None:
    """A documented `jointplot` kind that produced nothing at all.

    Its central panel is the bivariate histogram and its marginals are
    ordinary 1D ones. All three are announced now: the joint panel as `heat`
    and the margins as `hist`.

    Before #522 this returned the two margins alone — which is the worse
    symptom of the two, because nothing raised. A reader was handed a
    complete-sounding chart with the joint distribution, the thing a joint
    plot is drawn for, silently missing.
    """
    grid = sns.jointplot(data=_frame(), x="v", y="w", kind="hist")

    assert _layers(grid.figure) == [PlotType.HEAT, PlotType.HIST, PlotType.HIST]
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

    # No `hist`, which is the point of this case. The `heat` beside it is the
    # mesh that call did draw, and is asked the same question about ownership
    # that the bars are — see the mesh test below (#522).
    assert _layers(fig) == [PlotType.BAR, PlotType.HEAT]


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


def test_the_two_spellings_of_one_bivariate_histogram_agree() -> None:
    """The row the fix is for.

    `sns.displot(x=, y=)` read as `heat` and `sns.histplot(x=, y=)` was
    silent, and the only difference between them was that `histplot` is
    patched: `common()` sets the internal context so a patched seaborn call
    does not register twice, the inner `Axes.pcolormesh` therefore declines,
    and then `_drew_bars` declines as well. `displot` escaped by not being
    patched at all.

    Asserted as an equality rather than as two literals, because what was
    wrong was the disagreement (#522).
    """
    frame = _frame()

    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="v", y="w", ax=ax)
    through_histplot = _layers(fig)

    grid = sns.displot(data=frame, x="v", y="w")
    through_displot = _layers(grid.figure)

    assert through_histplot == through_displot == [PlotType.HEAT]


def test_a_mesh_already_on_the_axes_is_not_claimed_by_a_later_call() -> None:
    """The ownership question, asked of meshes as it is of bars.

    `_drew_mesh` asks what *this call* added, not what the axes holds. Asked
    the second way, the `heatmap` drawn first is claimed all over again by the
    `histplot` beside it, and the reader navigates two identical heatmaps --
    the double-registration the recursion guard exists to prevent, arriving by
    another route.

    Drawn with nothing in it, which is what makes the case reachable: a
    histplot that draws bars registers its `hist` and never reaches the mesh
    branch, and a bivariate one always adds a mesh of its own, so neither can
    tell the two readings apart. An empty one takes the decline path and adds
    nothing, so the only mesh on the axes is somebody else's.
    """
    fig, ax = plt.subplots()

    sns.heatmap(np.arange(6).reshape(2, 3), ax=ax)
    sns.histplot(x=[], ax=ax)

    assert _layers(fig) == [PlotType.HEAT]


def test_a_second_bivariate_histogram_on_the_same_axes_registers_too() -> None:
    """The mesh analogue of the bar case above: new mesh, new layer.

    Two overlaid joint distributions are two charts, and each call adds its
    own `QuadMesh`, so the ownership check must let the second through rather
    than treat the first one's mesh as already accounting for it.

    Only the layer count is asserted. Both layers currently read their values
    from the *first* mesh, because `HeatPlot` resolves its artist from the
    axes at extraction time rather than being bound to the one it was
    registered for -- a separate defect (#527) which reproduces on two plain
    `ax.pcolormesh` calls and which this change neither causes nor fixes.
    """
    frame = _frame()
    fig, ax = plt.subplots()

    sns.histplot(data=frame, x="v", y="w", ax=ax)
    sns.histplot(data=frame, x="w", y="v", ax=ax)

    assert _layers(fig) == [PlotType.HEAT, PlotType.HEAT]


def test_a_heatmap_is_read_from_the_mesh_and_not_from_a_scatter() -> None:
    """`ScalarMappable` is a wider net than the extractor assumed.

    A scatter's `PathCollection` is a `ScalarMappable` -- that is what makes a
    colour-mapped scatter possible -- so "the first mappable on the axes"
    picked the scatter and `HeatPlot` was handed an artist with no grid. This
    fails on `pcolormesh` alone, with nothing from #522 involved, which is why
    it is asserted on that rather than through `histplot`.
    """
    rng = np.random.default_rng(20260820)
    fig, ax = plt.subplots()

    sns.scatterplot(x=rng.normal(size=30), y=rng.normal(size=30), ax=ax)
    ax.pcolormesh(np.arange(12).reshape(3, 4))

    assert _layers(fig) == [PlotType.SCATTER, PlotType.HEAT]
    assert maidr.render(fig) is not None


def test_an_axes_with_no_mappable_returns_none_rather_than_raising() -> None:
    """The contract the annotation always claimed.

    `extract_scalar_mappable` is typed `Optional[ScalarMappable]` and
    `HeatPlot._extract_plot_data` opens with `if data is None`, but a bare
    `next()` meant that branch could never run -- an axes holding no mappable
    raised `StopIteration`, which names nothing and takes the figure with it.
    The same shape #388 removed from `extract_container`.
    """
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [3, 2, 1])  # a line is not a ScalarMappable

    assert ScalarMappableExtractorMixin.extract_scalar_mappable(ax) is None


def test_seaborn_still_takes_ax_by_keyword() -> None:
    """The assumption the pre-draw snapshot rests on.

    `_prospective_axes` reads `ax` from kwargs alone. That is safe only while
    seaborn declares it keyword-only — a positional spelling would be missed,
    the snapshot would come back empty, and a stale container would once again
    look like this call's own work.

    Asserted rather than commented, because the failure is silent: every test
    above passes an explicit `ax=` keyword and would go on passing.
    """
    import inspect

    kind = inspect.signature(sns.histplot).parameters["ax"].kind

    assert kind is inspect.Parameter.KEYWORD_ONLY
