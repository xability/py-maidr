"""A seaborn function has two names, and MAIDR was patching one of them.

seaborn re-exports its plotting functions from the package root, and its own
figure-level functions import them from the **defining module**, inside the
function body::

    from .relational import scatterplot   # Avoid circular import
    from .distributions import histplot, kdeplot

Those are two separate bindings to one function object, so wrapping
``seaborn.scatterplot`` left ``seaborn.relational.scatterplot`` untouched --
and every grid in ``seaborn/axisgrid.py`` takes the second one. `pairplot`,
`jointplot`, `catplot`, `relplot`, `displot` and `lmplot` therefore ran the
*unpatched* function.

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
already right. `displot` and `catplot` are **not** fixed by this -- they drive
seaborn's plotter classes directly rather than importing the module-level
functions -- and are pinned at the foot of this file so the boundary is
visible rather than discovered.

The failure was invisible from a direct call -- `sns.histplot(ax=ax)` has
always given `hist` -- which is why it survived this long. So the first test
below asserts the *binding*, not the behaviour: it is the only thing that
fails the moment a new patch is added at one name and not the other.
"""

from __future__ import annotations

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


def test_the_grids_this_does_not_reach_are_named() -> None:
    """The boundary, asserted rather than left to be discovered per bug report.

    `displot` and `catplot` do not import the module-level functions at all --
    they drive `_DistributionPlotter` and `_CategoricalPlotter` directly -- so
    patching the defining module does not touch them. They are still read only
    by the matplotlib-level patches, and still wrong: a distribution arrives as
    a grouped bar chart.

    Pinned here so that the day either is fixed, this test fails and has to be
    rewritten, the way `test_hist2d.py` pinned `hexbin` before #368.
    """
    frame = _frame()
    frame["group"] = ["x", "y"] * 30

    # A histogram, announced as a grouped bar chart.
    assert _layers(sns.displot(data=frame, x="a").figure) == [PlotType.DODGED]

    # Bars plus the error-bar lines, neither read as what it is.
    assert _layers(
        sns.catplot(data=frame, x="group", y="a", kind="bar").figure
    ) == [PlotType.DODGED, PlotType.LINE]
