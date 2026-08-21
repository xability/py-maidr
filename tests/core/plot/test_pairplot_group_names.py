"""
A ``pairplot`` hue left its diagonal panels anonymous (#561).

#559 and #560 name a hue's layers by matching each artist's colour against
the legend swatch that names it, and both do the match **at registration**.
`sns.pairplot(hue=...)` is the one chart where that cannot fire, and the
reason is timing rather than the match: ``PairGrid.add_legend()`` builds one
figure-level legend after every panel has been drawn, so when the diagonals
register there is no legend anywhere -- not on the axes, not on the figure.

Measured before the fix, on the same figure::

    smooth  (no name)   smooth  (no name)     <- the diagonals
    smooth  (no name)   smooth  (no name)
    point   name='x'    point   name='y'      <- the scatters beside them

Two things were needed and neither works alone:

- **the match is deferred to render**, when the legend exists. ``GROUP_NAME``
  therefore accepts a callable as well as a string.
- **the figure's legend is read** when the axes has none of its own, which is
  where a ``PairGrid`` puts it.

A third thing was needed for the ``diag_kind="hist"`` spelling, and it is
the reason `_group_names` now delegates to `kdeplot._names_for`: a pairplot
draws its bars translucent and its swatches opaque -- measured, alpha 0.5
against 1.0 with identical hues -- so an exact RGBA comparison names
nothing. That second, hue-only pass already existed for the KDE side.

What is deliberately not fixed: the manual ``ax.scatter(c=[...])`` followed
by ``ax.legend(handles=[...])`` that #561 mentions. A hue-grouped scatter is
split into one layer *per group* at registration, so deferring its name
would mean deferring how many layers there are, which is a different change.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn as sns

import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "a": rng.normal(size=40),
            "b": rng.normal(size=40) + 1,
            "g": ["x"] * 20 + ["y"] * 20,
        }
    )


def _named(fig) -> list:
    """Every layer as ``(type, name)``, after a real render."""
    maidr.render(fig)._repr_html_()
    return [
        (plot.type.value, plot.schema.get("name"))
        for plot in FigureManager.get_maidr(fig).plots
    ]


def _diagonals(named: list, kind: str) -> list:
    return [name for layer, name in named if layer == kind]


def test_a_pairplots_kde_diagonals_are_named():
    named = _named(sns.pairplot(_frame(), hue="g").figure)

    # Two groups per diagonal panel, two panels.
    assert _diagonals(named, "smooth") == ["y", "x", "y", "x"]


def test_a_pairplots_histogram_diagonals_are_named():
    # The spelling that also needed the hue-only colour pass: these bars are
    # translucent and the figure legend's swatches are not.
    named = _named(sns.pairplot(_frame(), hue="g", diag_kind="hist").figure)

    assert _diagonals(named, "hist") == ["y", "x", "y", "x"]


def test_the_scatters_beside_them_are_unchanged():
    # They were already named, by a legend the off-diagonal panels do have at
    # registration. Asserted so the deferral cannot have cost them.
    named = _named(sns.pairplot(_frame(), hue="g").figure)

    assert _diagonals(named, "point") == ["x", "y", "x", "y"]


def test_a_plain_hue_grouped_kde_is_unchanged():
    fig, ax = plt.subplots()
    sns.kdeplot(data=_frame(), x="a", hue="g", ax=ax)

    assert _named(fig) == [("smooth", "y"), ("smooth", "x")]


def test_a_plain_hue_grouped_histogram_is_unchanged():
    fig, ax = plt.subplots()
    sns.histplot(data=_frame(), x="a", hue="g", bins=4, ax=ax)

    assert _named(fig) == [("hist", "y"), ("hist", "x")]


def test_a_histogram_with_its_kde_overlay_names_all_four_layers():
    # The case #560 was written for, where the bars are translucent and the
    # curves opaque. It runs through the deferred path now, so it is pinned
    # here as well as there.
    fig, ax = plt.subplots()
    sns.histplot(data=_frame(), x="a", hue="g", bins=4, kde=True, ax=ax)

    assert _named(fig) == [
        ("hist", "y"),
        ("hist", "x"),
        ("smooth", "y"),
        ("smooth", "x"),
    ]


@pytest.mark.parametrize("draw", ["hist", "kde"])
def test_an_ungrouped_chart_is_still_unnamed(draw):
    # A name on the only layer of a chart reads as though there were another
    # to tell it from.
    fig, ax = plt.subplots()
    if draw == "hist":
        sns.histplot(data=_frame(), x="a", bins=4, ax=ax)
    else:
        sns.kdeplot(data=_frame(), x="a", ax=ax)

    assert [name for _, name in _named(fig)] == [None]


def _drawn_curves(ax) -> list:
    from matplotlib.lines import Line2D

    return [line for line in ax.get_lines() if isinstance(line, Line2D)]


def _figure_legend(fig, ax, **kwargs):
    """A figure legend naming the drawn colours, as a `PairGrid` builds one."""
    from matplotlib.patches import Patch

    curves = _drawn_curves(ax)
    handles = [Patch(facecolor=curve.get_color()) for curve in curves]
    # Reversed, which is the order seaborn's own legend runs in -- so a match
    # by position would give each curve the other group's name and these two
    # tests would agree for the wrong reason.
    return fig.legend(handles=handles, labels=["x", "y"], **kwargs)


def test_one_figure_legend_names_the_axes_below_it():
    # The other half of the fix, on its own: the axes has no legend of its
    # own, and the figure's is where a `PairGrid` puts it.
    fig, ax = plt.subplots()
    sns.kdeplot(data=_frame(), x="a", hue="g", ax=ax, legend=False)
    _figure_legend(fig, ax, loc="upper left")

    assert [name for _, name in _named(fig)] == ["x", "y"]


def test_two_figure_legends_name_nothing():
    # The guard on reading the figure's legend: with two of them, nothing
    # says which names this axes' colours, and a wrong name is worse than
    # none. Both carry the real swatches, so the test above is what makes
    # this one bite -- either alone would name the curves.
    fig, ax = plt.subplots()
    sns.kdeplot(data=_frame(), x="a", hue="g", ax=ax, legend=False)
    _figure_legend(fig, ax, loc="upper left")
    _figure_legend(fig, ax, loc="upper right")

    assert [name for _, name in _named(fig)] == [None, None]


def test_an_axes_own_legend_wins_over_the_figures():
    # The mitigation for the case below: a panel that kept its own legend is
    # named by it and never consults the figure's. That is the ordinary
    # seaborn call, so the ambiguity needs a figure built by hand.
    fig, ax = plt.subplots()
    sns.kdeplot(data=_frame(), x="a", hue="g", ax=ax)
    _figure_legend(fig, ax, loc="upper right")

    # The axes legend names them the way it always did, not the figure's
    # reversed labels.
    assert [name for _, name in _named(fig)] == ["y", "x"]


def test_one_figure_legend_names_every_panel_below_it():
    # The accepted cost, pinned rather than left to be discovered. One figure
    # legend is read as naming every axes, and nothing in the artists can say
    # otherwise: two panels with independent hues draw the same default
    # colour cycle, so a legend built for the first matches the second too.
    #
    # It needs a figure built by hand with both panels' legends suppressed.
    # The trade is this against no name at all on every `pairplot`.
    from matplotlib.patches import Patch

    rng = np.random.default_rng(0)
    left = pd.DataFrame({"v": rng.normal(size=40), "g": ["p"] * 20 + ["q"] * 20})
    right = pd.DataFrame(
        {"v": rng.normal(size=40) + 2, "h": ["s"] * 20 + ["t"] * 20}
    )

    fig, (first, second) = plt.subplots(1, 2)
    sns.kdeplot(data=left, x="v", hue="g", ax=first, legend=False)
    sns.kdeplot(data=right, x="v", hue="h", ax=second, legend=False)
    fig.legend(
        handles=[Patch(facecolor=c.get_color()) for c in _drawn_curves(first)],
        labels=["p", "q"],
    )

    # The second panel's groups are `s` and `t`, and they are announced with
    # the first panel's names. Both panels drew the same two colours.
    assert [name for _, name in _named(fig)] == ["p", "q", "p", "q"]


def test_the_name_is_resolved_once_and_stays_put():
    # Rendered more than once -- `schema`, `elements` and `set_id` each
    # render when nothing is cached -- and the layers of one call have to
    # agree with each other and with themselves.
    figure = sns.pairplot(_frame(), hue="g").figure
    maidr.render(figure)._repr_html_()

    plots = FigureManager.get_maidr(figure).plots
    first = [plot.render().get("name") for plot in plots]
    second = [plot.render().get("name") for plot in plots]

    assert first == second
    assert first[:4] == ["y", "x", "y", "x"]


def test_a_translucent_bar_is_named_by_an_opaque_swatch():
    # The colour half, stated on its own. A pairplot's legend swatches are
    # opaque while its bars are not, so the exact-RGBA pass names nothing and
    # the hue-only pass is what answers.
    from maidr.patch.histogram import _container_colour
    from maidr.patch.kdeplot import _handle_colour, legend_of

    figure = sns.pairplot(_frame(), hue="g", diag_kind="hist").figure
    maidr.render(figure)._repr_html_()

    from matplotlib.container import BarContainer

    axes = [
        ax
        for ax in figure.axes
        if any(isinstance(c, BarContainer) for c in ax.containers)
    ]
    containers = [c for c in axes[0].containers if isinstance(c, BarContainer)]
    legend = legend_of(axes[0])

    bars = {_container_colour(c) for c in containers}
    swatches = {_handle_colour(h) for h in legend.legend_handles}

    # Same hues, different alpha -- which is why an exact comparison fails.
    assert bars.isdisjoint(swatches)
    assert {colour[:3] for colour in bars} == {colour[:3] for colour in swatches}
