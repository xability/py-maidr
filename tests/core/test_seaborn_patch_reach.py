"""A seaborn function has two names, and MAIDR was patching one of them.

seaborn re-exports its plotting functions from the package root, and its own
figure-level functions import them from the **defining module**, inside the
function body::

    from .relational import scatterplot   # Avoid circular import
    from .distributions import histplot, kdeplot

Those are two separate bindings to one function object, so wrapping
``seaborn.scatterplot`` left ``seaborn.relational.scatterplot`` untouched --
and the grids in ``seaborn/axisgrid.py`` take the second one. `pairplot`,
`jointplot`, `relplot` and `lmplot` therefore ran the *unpatched* function.
Measured by counting calls that reach the defining-module binding:

    pairplot   histplot, scatterplot      catplot   -- none --
    jointplot  histplot, scatterplot      displot   -- none --
    relplot    scatterplot
    lmplot     regplot

That cost two things at once, and neither reads as a patching problem:

* a `histplot` panel arrived as **bars**, because `Axes.bar` cannot know it is
  drawing a histogram and the seaborn-level patch that would have known never
  ran;
* every panel registered **twice**. `seaborn.utils._default_color` draws a
  throwaway artist to resolve a default colour and removes it again, and with
  no seaborn-level patch there was no recursion context to suppress it, so the
  probe registered as a chart of its own (#344).

Measured on a two-variable `pairplot`, which draws four panels::

    before   bar, dodged_bar, bar, dodged_bar, point, point, point, point
    after    hist, hist, point, point

Three grids change: `pairplot`, `jointplot` and `lmplot`. `relplot` was
already right. `displot` and `catplot` were **not** fixed by this -- they
drive seaborn's plotter classes directly rather than importing the
module-level functions. Both have since been reached one level down, by
patching the plotter method the grid and the axes-level function share:
`displot` through `_DistributionPlotter` (#446), and `catplot` through the
`_CategoricalPlotter` methods behind each `kind` (#448, #449). `catplot` is
reached one `kind` at a time, though, since each is drawn by a different
method -- so the kinds still unreached are pinned at the foot of this file,
and the boundary stays visible rather than being discovered.

The failure was invisible from a direct call -- `sns.histplot(ax=ax)` has
always given `hist` -- which is why it survived this long. So the first test
below asserts the *binding*, not the behaviour: it is the only thing that
fails the moment a new patch is added at one name and not the other.
"""

from __future__ import annotations

import warnings

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402
import seaborn.categorical  # noqa: E402
import seaborn.distributions  # noqa: E402
import seaborn.matrix  # noqa: E402
import seaborn.regression  # noqa: E402
import seaborn.relational  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.patch.common import _warn_partial_patch, wrap_seaborn  # noqa: E402


#: Every seaborn function MAIDR patches, with the module that defines it.
PATCHED = [
    ("scatterplot", seaborn.relational),
    ("lineplot", seaborn.relational),
    ("histplot", seaborn.distributions),
    ("kdeplot", seaborn.distributions),
    ("barplot", seaborn.categorical),
    ("countplot", seaborn.categorical),
    ("pointplot", seaborn.categorical),
    ("heatmap", seaborn.matrix),
    ("regplot", seaborn.regression),
    ("boxplot", seaborn.categorical),
    ("violinplot", seaborn.categorical),
]


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Two numeric columns, enough for a 2x2 grid."""
    rng = np.random.default_rng(20260814)
    return pd.DataFrame({"a": rng.normal(size=60), "b": rng.normal(size=60)})


def _is_wrapped(function) -> bool:
    """Whether wrapt has a wrapper installed on this object."""
    return type(function).__name__ == "FunctionWrapper"


def _layers(fig) -> list:
    """The plot types registered for a figure, or an empty list."""
    try:
        return [plot.type for plot in FigureManager.get_maidr(fig).plots]
    except KeyError:
        return []


@pytest.mark.parametrize("name,module", PATCHED)
def test_both_names_are_wrapped(name, module) -> None:
    """The binding, asserted directly, because the behaviour hides it.

    Everything else in this file goes through a grid, which is a long way
    from the line that installs a patch. This is the check that fails the
    moment a tenth function is patched at the re-export and not at its
    defining module -- and that mistake is silent everywhere else, since a
    direct call keeps working.
    """
    assert _is_wrapped(getattr(sns, name)), f"seaborn.{name} is unwrapped"
    assert _is_wrapped(
        getattr(module, name)
    ), f"{module.__name__}.{name} is unwrapped"


def test_a_pairplot_reads_one_layer_per_panel() -> None:
    """Four panels, four layers, and the diagonal is a histogram.

    Before, this was eight layers: every panel twice, with the diagonal
    arriving as `bar` plus `dodged_bar` because only the matplotlib-level
    patches saw it.
    """
    grid = sns.pairplot(_frame())

    assert _layers(grid.figure) == [
        PlotType.HIST,
        PlotType.HIST,
        PlotType.SCATTER,
        PlotType.SCATTER,
    ]


def test_a_jointplot_marginal_is_a_histogram() -> None:
    """The central panel and its two marginals, each once.

    The marginals were `dodged_bar`, which is a chart with groups in it --
    a reader would have been told a distribution was a grouped bar chart.
    """
    grid = sns.jointplot(data=_frame(), x="a", y="b")

    assert _layers(grid.figure) == [
        PlotType.SCATTER,
        PlotType.HIST,
        PlotType.HIST,
    ]


def test_a_direct_call_is_unchanged() -> None:
    """The control, and what made this invisible.

    Calling the same functions with an explicit axes has always been right,
    because the top-level name is the one a user reaches for. Nothing here
    should move.
    """
    frame = _frame()

    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", ax=ax)
    assert _layers(fig) == [PlotType.HIST]

    fig, ax = plt.subplots()
    sns.scatterplot(data=frame, x="a", y="b", ax=ax)
    assert _layers(fig) == [PlotType.SCATTER]


def test_a_regression_grid_reads_its_curve_as_a_fit() -> None:
    """`lmplot` gained more than a layer count: its curve changed meaning.

    It was `point` plus **`line`** -- the fitted curve announced as though it
    were the data. `smooth` is the type for a computed fit, and it is what a
    direct `sns.regplot()` has always emitted. Unlooked-for when this change
    was written, and the clearest illustration of what running the unpatched
    function costs: the layer count was already right, so nothing about the
    old reading looked wrong.
    """
    grid = sns.lmplot(data=_frame(), x="a", y="b")

    assert _layers(grid.figure) == [PlotType.SCATTER, PlotType.SMOOTH]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("boxplot", [PlotType.BOX]),
        ("violinplot", [PlotType.VIOLIN_BOX, PlotType.VIOLIN_KDE]),
    ],
)
def test_a_categorical_plot_reads_the_same_from_either_binding(
    name, expected
) -> None:
    """No seaborn grid reaches these two, and they were still wrong.

    `catplot` drives `_CategoricalPlotter` directly, so nothing in seaborn
    takes `seaborn.categorical.boxplot`. What did was ordinary user code::

        from seaborn.categorical import violinplot

    and that import got a reading with nothing recognisable left in it:

        seaborn.violinplot              violin_box, violin_kde
        seaborn.categorical.violinplot  area, line

    A violin announced as a **line chart** -- not a degraded violin, a
    different chart -- plus a phantom `area` layer from the colour probe in
    `seaborn.utils._default_color`, which had no recursion context to
    suppress it because no seaborn-level patch had run.

    Asserted as equality between the two bindings *and* against the expected
    types, because either alone would pass if both bindings broke together.
    """
    frame = pd.DataFrame(
        {"group": list("aabbcc") * 4, "value": list(range(1, 25))}
    )
    readings = []

    for source in (sns, seaborn.categorical):
        fig, ax = plt.subplots()
        getattr(source, name)(data=frame, x="group", y="value", ax=ax)
        readings.append(_layers(fig))
        plt.close(fig)

    assert readings[0] == expected
    assert readings[1] == expected


def test_the_partial_patch_warning_names_no_grids() -> None:
    """The warning helper, driven directly, because nothing else reaches it.

    Its three call sites are unreachable on any seaborn MAIDR has been
    measured against -- they are for the release that moves a function or
    renames a module -- so the body would otherwise be untested by
    construction, and its whole job is to be readable by someone who has
    just hit it once, years from now, with no idea what a binding is.

    What is pinned is that it does *not* name grids. Which grids are exposed
    varies per function: `pairplot`, `jointplot`, `relplot` and `lmplot` take
    the defining-module binding, `catplot` and `displot` reach neither, and
    for `boxplot` and `violinplot` no grid reaches it at all -- the exposure
    there is a direct import. A message that named four grids would send the
    reader of a `violinplot` warning to look at functions that were never on
    the path, which is the same mistake this file's own docstring once made.
    """
    with pytest.warns(UserWarning) as caught:
        _warn_partial_patch(
            "violinplot",
            "seaborn.categorical.violinplot",
            "seaborn.categorical could not be imported",
        )

    message = str(caught[0].message)

    assert "violinplot" in message
    assert "seaborn.categorical.violinplot" in message
    assert "seaborn.categorical could not be imported" in message
    # Both routes to the unwrapped binding, and neither named as a specific
    # function that may not apply.
    assert "grids" in message
    assert "direct import" in message
    for grid in ("pairplot", "jointplot", "relplot", "lmplot", "catplot"):
        assert grid not in message


def test_a_function_defined_at_the_package_root_is_not_a_gap(monkeypatch) -> None:
    """``__module__ == "seaborn"`` means the wrap is complete, not partial.

    There is no second binding to miss when the function is defined at the
    package root: ``seaborn.<name>`` *is* the defining binding. Warning there
    would report a gap that does not exist, and the reader would go looking
    for a module that is already patched.

    None of the eleven functions patched today takes this branch, so it is
    driven with a stand-in installed on the seaborn module and removed again
    by ``monkeypatch``.
    """
    import seaborn

    def defined_at_the_root(*args, **kwargs):
        return None

    defined_at_the_root.__module__ = "seaborn"
    monkeypatch.setattr(seaborn, "_maidr_root_probe", defined_at_the_root, raising=False)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning here fails the test
        wrap_seaborn("_maidr_root_probe", lambda w, i, a, k: w(*a, **k))

    assert _is_wrapped(seaborn._maidr_root_probe)


def test_a_function_seaborn_no_longer_exports_warns() -> None:
    """Neither binding wrapped, which is worse than one of two.

    The function is simply read by the matplotlib-level patches from then on,
    with nothing anywhere saying so.
    """
    with pytest.warns(UserWarning, match="no longer exports"):
        wrap_seaborn("a_function_seaborn_has_never_had", lambda w, i, a, k: w(*a, **k))


def test_displot_is_reached_through_the_plotter_class() -> None:
    """`displot` was the half of this boundary that has since been closed.

    It still imports nothing -- it drives `_DistributionPlotter` directly --
    so the defining-module patching this file is about never touched it, and
    its panels were read only by the matplotlib-level patches. A histogram
    arrived as a **grouped bar chart** with its bin edges gone (#446).

    The fix went one level down, to the plotter method both interfaces drive,
    which is the same idiom `maidr/patch/boxplot.py` uses for
    `_CategoricalPlotter.plot_boxes`. So the assertion here inverts: what this
    test pinned as wrong is now pinned as right.
    """
    frame = _frame()

    # A histogram, read as one.
    assert _layers(sns.displot(data=frame, x="a").figure) == [PlotType.HIST]

    # A fitted curve, read as a curve rather than as a series of samples.
    assert _layers(
        sns.displot(data=frame, x="a", kind="kde").figure
    ) == [PlotType.SMOOTH]


def test_displot_panels_are_each_read() -> None:
    """One call to the plotter method covers the whole grid.

    `plot_univariate_histogram` is reached **once** for a faceted `displot`
    and draws every panel, so a wrapper that registered only `plotter.ax`
    would leave all but the first unread -- and `ax` is `None` in exactly that
    case, so it would in fact leave *all* of them unread.
    """
    frame = _frame()
    frame["group"] = ["x", "y"] * 30

    assert _layers(
        sns.displot(data=frame, x="a", col="group").figure
    ) == [PlotType.HIST, PlotType.HIST]


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("violin", [PlotType.VIOLIN_BOX, PlotType.VIOLIN_KDE]),
        ("boxen", [PlotType.BOXEN]),
        ("point", [PlotType.ERRORBAR]),
    ],
)
def test_a_catplot_kind_reached_through_the_plotter_class(kind, expected) -> None:
    """`catplot` is reached one `kind` at a time, because each has its own method.

    It drives `_CategoricalPlotter` directly and imports nothing, so neither
    the defining-module patching this file is about nor #446's plotter-level
    patching of `_DistributionPlotter` touched it. Every one of these
    panels was read only by the matplotlib-level patches, and every one
    arrived as a **line chart** (#448)::

        catplot(kind="violin")   line
        catplot(kind="boxen")    line, point, point
        catplot(kind="point")    line

    The violin's line was its inner box; the boxen's was its median segments,
    with the point layers holding the outliers alone -- every rung of every
    ladder absent, which is the reading `BoxenPlot` exists to replace. The
    point plot's line was right about its estimates and had nowhere to put its
    confidence intervals, which is the quietest of the three: a reading with
    no intervals in it sounds exactly like a correct reading of a chart that
    draws none.

    Each fix went to the plotter method the grid and the axes-level function
    share, so the two interfaces agree by construction rather than by being
    kept in step (#449).
    """
    frame = _frame()
    frame["group"] = ["x", "y"] * 30

    assert _layers(
        sns.catplot(data=frame, x="group", y="a", kind=kind).figure
    ) == expected


def test_the_kind_of_catplot_this_does_not_reach_is_named() -> None:
    """The boundary that remains, asserted rather than left to a bug report.

    `kind` selects which plotter method draws, and each is a separate reach:
    `plot_violins`, `plot_boxens` and `plot_points` are patched, `plot_bars`
    is not. So a `catplot` bar is still read only by the matplotlib-level
    patches -- bars plus the error-bar lines, neither read as what it is
    (#448).

    Pinned here so that the day it is fixed, this test fails and has to be
    rewritten -- the way this file pinned `displot`, the violin, the boxen and
    the point plot until they were.
    """
    frame = _frame()
    frame["group"] = ["x", "y"] * 30

    assert _layers(
        sns.catplot(data=frame, x="group", y="a", kind="bar").figure
    ) == [PlotType.DODGED, PlotType.LINE]
