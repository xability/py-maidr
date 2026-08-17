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
`_CategoricalPlotter` method behind each `kind` (#448, #449). `catplot` took
one reach per `kind`, since each is drawn by a different method -- so the foot
of this file asserts all eight against their axes-level equivalents rather
than naming the ones that agree.

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

import maidr  # noqa: E402  # activates patches
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


#: Every `kind` `sns.catplot` accepts, with the axes-level function that draws
#: the same chart. Six of the eight disagreed (#448), and the two that did not
#: are here as well, because "these two happen to agree" is not something a
#: reader can tell from a table that lists only the six.
CATPLOT_KINDS = [
    ("strip", "stripplot"),
    ("swarm", "swarmplot"),
    ("box", "boxplot"),
    ("violin", "violinplot"),
    ("boxen", "boxenplot"),
    ("point", "pointplot"),
    ("bar", "barplot"),
    ("count", "countplot"),
]


@pytest.mark.parametrize(
    "kind,axes_level", CATPLOT_KINDS, ids=[kind for kind, _ in CATPLOT_KINDS]
)
def test_a_catplot_kind_reads_the_same_as_its_axes_level_function(
    kind, axes_level
) -> None:
    """The whole of #448, as one assertion per `kind`.

    `catplot` drives `_CategoricalPlotter` directly and imports nothing, so
    neither the defining-module patching this file is about nor #446's
    plotter-level patching of `_DistributionPlotter` touched it -- and every
    panel was read by the matplotlib-level patches alone. Measured against the
    axes-level function that draws the same chart, six of eight disagreed, and
    they failed in three distinct ways::

        kind      catplot read              axes-level read
        strip     point, point              point, point        ok
        swarm     point, point              point, point        ok
        box       box                       box                 ok
        violin    line                      violin_box, violin_kde
        boxen     line, point, point        boxen
        point     line                      error_bar
        bar       dodged_bar, line          bar
        count     dodged_bar                bar

    A **distribution announced as a line chart** for `violin` and `boxen`: the
    violin's line is its inner box, the boxen's its median segments, with the
    point layers holding the outliers alone. **Uncertainty dropped** for
    `point`: the estimates read correctly and the confidence intervals had
    nowhere to go, so a reading with no intervals in it sounded exactly like a
    correct reading of a chart that draws none. And a **wrong type plus a
    phantom layer** for `bar`/`count`: `dodged_bar` names a chart that compares
    groups side by side, which a chart with no hue is not, and the extra `line`
    was the error-bar geometry travelling as a series of its own.

    `box` already agreed, and that is the evidence the approach works rather
    than a coincidence: `_CategoricalPlotter.plot_boxes` was already patched,
    for `seaborn.boxplot`. Each of the other five went the same way, to the
    plotter method the grid and the axes-level function share (#448, #449).

    Asserted as equality between the two interfaces rather than against
    expected types, because that is the property being fixed -- and because
    either alone would pass if both interfaces broke together.
    """
    frame = _frame()
    frame["group"] = ["x", "y"] * 30
    variables = {"x": "group"} if kind == "count" else {"x": "group", "y": "a"}

    grid = sns.catplot(data=frame, kind=kind, **variables)
    figure_level = _layers(grid.figure)
    plt.close("all")

    fig, ax = plt.subplots()
    getattr(sns, axes_level)(data=frame, ax=ax, **variables)

    assert figure_level == _layers(fig)
    assert figure_level, f"catplot(kind={kind!r}) registered nothing at all"


@pytest.mark.parametrize(
    "kind", ["bar", "count", "violin", "boxen", "point"], ids=lambda k: k
)
def test_an_unbalanced_facet_grid_still_renders(kind) -> None:
    """A `row`/`col` grid allocates an axes for combinations the data lacks.

    Seaborn draws nothing into those, and a patch that registered every axes
    the grid holds would promise a layer whose extraction has nothing to
    read -- which raises, and takes the **whole figure's** HTML down with it
    rather than only the empty panel's::

        ExtractionError: Error extracting data for bar plot type from <class 'list'>

    So the panels come from seaborn's own `iter_data(allow_empty=False)`
    rather than from the grid, and the layer count is the number of
    combinations that exist, not the number of axes.

    Every kind whose registration moved to a plotter method is checked,
    because the guard lives in one shared helper and a caller that stops using
    it fails silently everywhere else -- the figure renders fine until someone
    facets it two ways.
    """
    rng = np.random.default_rng(20260816)
    frame = pd.DataFrame(
        {
            "a": rng.normal(size=90),
            "group": list("abc") * 30,
            "col": ["x"] * 45 + ["y"] * 45,
            "row": ["p"] * 30 + ["q"] * 15 + ["p"] * 45,
        }
    )
    variables = {"x": "group"} if kind == "count" else {"x": "group", "y": "a"}

    grid = sns.catplot(data=frame, kind=kind, col="col", row="row", **variables)

    # Four axes, three combinations the data actually holds.
    assert len(list(grid.axes.flat)) == 4
    assert len(frame.groupby(["row", "col"], observed=True)) == 3
    assert "maidr" in str(maidr.render(grid.figure))


def test_every_catplot_kind_seaborn_dispatches_is_covered() -> None:
    """The table above has to keep up with seaborn.

    A ninth `kind` is a panel nothing above reads, and the test that would
    have caught it is the one that does not exist yet. So the list is checked
    against `catplot`'s own dispatch rather than trusted -- it branches on
    `kind == "..."` once per kind, and every one of those has to appear here.

    The count is asserted first because the reading is the fragile half: if
    seaborn ever replaces the chain with a table lookup, the regex finds
    nothing and a subset check against an empty set passes while proving
    nothing. Failing loudly there is the point -- it means this test needs
    rewriting, not that the coverage is fine.
    """
    import inspect
    import re

    dispatched = set(re.findall(r'kind == "(\w+)"', inspect.getsource(sns.catplot)))

    assert len(dispatched) >= 8, (
        "could not read catplot's kinds from its source -- it no longer "
        f"branches on `kind == \"...\"` (found {sorted(dispatched)})"
    )
    assert dispatched <= {kind for kind, _ in CATPLOT_KINDS}
