"""
A ``jointplot`` hue left its two marginals anonymous (#610).

A ``JointGrid`` draws three panels off one hue mapping and hangs the one
legend that names it on ``ax_joint``. ``legend_of`` reads an axes' own legend
and, failing that, a **figure** legend -- which is where a ``PairGrid`` puts
one (#561) and is what made that chart readable. A `JointGrid` puts it in
neither place as far as a marginal is concerned, so the marginals found
nothing and every resolver downstream declined correctly on the input it was
given.

Measured before the fix, two levels `p` and `q`::

    [0][0] smooth  name=None       <- top marginal
    [0][0] smooth  name=None
    [1][0] point   name='p'        <- joint
    [1][0] point   name='q'
    [1][1] smooth  name=None       <- right marginal
    [1][1] smooth  name=None

The data is right in every panel. A reader who moves onto a marginal finds
two density curves with identical announcements and nothing to tell them
apart, which is the defect #558 named -- on the two panels of the chart where
it was not yet fixed.

**Not the lone-artist floor** (#608): each marginal holds two curves. There
was simply no legend for them to be matched against.

What the fix reads is narrower than the figure fallback, not wider: an axes
an axis is *shared* with. A `JointGrid` builds its marginals sharing one with
the joint axes, because that is how a marginal lines up with the scatter
beside it, and matplotlib records it::

    jointplot                        ax0 legend=True   shares=[1, 2]
                                     ax1 legend=False  shares=[0]
                                     ax2 legend=False  shares=[0]
    plt.subplots(1, 2)                                 shares=[]
    plt.subplots(1, 2, sharex=True)                    shares=[1]

So the hazard `legend_of` already documents and
`test_pairplot_group_names.py` already pins -- two unrelated panels named
from one figure legend -- is untouched, because those panels share nothing.
The tests below hold that line from the other side.
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
            "b": rng.normal(size=40) + 20,
            "g": ["p"] * 20 + ["q"] * 20,
        }
    )


def _named(fig) -> list:
    """Every layer as ``(type, name)``, after a real render."""
    maidr.render(fig)._repr_html_()
    return [
        (plot.type.value, plot.schema.get("name"))
        for plot in FigureManager.get_maidr(fig).plots
    ]


def _of_kind(named: list, kind: str) -> list:
    return [name for layer, name in named if layer == kind]


def test_a_hue_split_jointplots_marginals_are_named():
    """Two curves per marginal, two marginals, all four named.

    Sorted rather than asserted in order: what must hold is that no curve is
    left anonymous and that the names are the hue's levels, while which of
    the two comes first is the legend order #502 settled and not this
    change's business.
    """
    named = _named(sns.jointplot(data=_frame(), x="a", y="b", hue="g").figure)

    assert sorted(_of_kind(named, "smooth")) == ["p", "p", "q", "q"]


def test_the_joint_panel_is_unchanged():
    """Additive. The joint axes has a legend of its own and always did, so
    its two point layers must be named exactly as before -- a fix that
    reached them would mean the new fallback was running where the old rule
    already answered."""
    named = _named(sns.jointplot(data=_frame(), x="a", y="b", hue="g").figure)

    assert sorted(_of_kind(named, "point")) == ["p", "q"]


def test_a_jointplot_without_a_hue_is_untouched():
    """Nothing to name, and nothing pretending to."""
    named = _named(sns.jointplot(data=_frame(), x="a", y="b").figure)

    assert {name for _, name in named} == {None}


def _drawn_curves(ax) -> list:
    from matplotlib.lines import Line2D

    return [line for line in ax.get_lines() if isinstance(line, Line2D)]


def _axes_legend(ax, source, labels):
    """An axes legend naming another axes' drawn colours.

    Parameters
    ----------
    ax : Axes
        Where to hang it.
    source : Axes
        Whose curves supply the swatch colours.
    labels : list of str
        The names, in legend order.
    """
    from matplotlib.patches import Patch

    handles = [Patch(facecolor=curve.get_color()) for curve in _drawn_curves(source)]
    return ax.legend(handles=handles, labels=labels)


def test_an_unshared_panels_legend_is_not_read():
    """The line this fix holds, from the other side.

    Two panels of a hand-built figure with a legend on one of them: the
    second's colours match those swatches -- both panels draw the same
    default cycle -- and it is still not named, because the panels share no
    axis and nothing says they are one chart. This is the same figure
    `test_one_figure_legend_names_every_panel_below_it` measures as the
    accepted cost of the *figure* fallback; the sharer fallback does not
    extend that cost to axes legends.
    """
    rng = np.random.default_rng(0)
    left = pd.DataFrame({"v": rng.normal(size=40), "g": ["p"] * 20 + ["q"] * 20})
    right = pd.DataFrame({"v": rng.normal(size=40) + 2, "h": ["s"] * 20 + ["t"] * 20})

    fig, (first, second) = plt.subplots(1, 2)
    sns.kdeplot(data=left, x="v", hue="g", ax=first, legend=False)
    sns.kdeplot(data=right, x="v", hue="h", ax=second, legend=False)
    _axes_legend(first, first, ["p", "q"])

    # The first panel has the legend and is named by it; the second shares
    # nothing with it and stays anonymous.
    assert [name for _, name in _named(fig)] == ["p", "q", None, None]


def test_a_shared_panels_legend_is_read():
    """The same figure declared to be on one scale.

    `sharex=True` is the author saying these panels are one chart, which is
    what a `JointGrid` says structurally. Newly in scope, and pinned so the
    widening is visible rather than implied.
    """
    frame = _frame()

    fig, (first, second) = plt.subplots(1, 2, sharex=True)
    sns.kdeplot(data=frame, x="a", hue="g", ax=first, legend=False)
    sns.kdeplot(data=frame, x="a", hue="g", ax=second, legend=False)
    _axes_legend(first, first, ["p", "q"])

    assert [name for _, name in _named(fig)] == ["p", "q", "p", "q"]


def test_two_sharers_with_legends_name_nothing():
    """The guard, the same one the figure fallback has: two of them cannot
    say which names this axes' colours, and a wrong name is worse than none.

    Both legends carry the real swatches, so the test above is what makes
    this one bite -- either alone would name the curves.
    """
    frame = _frame()

    fig, (first, second, third) = plt.subplots(1, 3, sharex=True)
    for panel in (first, second, third):
        sns.kdeplot(data=frame, x="a", hue="g", ax=panel, legend=False)
    _axes_legend(first, first, ["p", "q"])
    _axes_legend(second, second, ["p", "q"])

    # The third shares with both of the legend-bearing panels.
    assert [name for _, name in _named(fig)][-2:] == [None, None]


def test_a_panels_own_legend_wins_over_a_sharers():
    """The mitigation, unchanged in shape from the figure fallback: a panel
    that kept its own legend is named by it and never consults a sibling's.

    The two legends carry the same swatches under **different** labels, so a
    reading that consulted the sharer would be visible rather than agreeing
    by luck.
    """
    frame = _frame()

    fig, (first, second) = plt.subplots(1, 2, sharex=True)
    sns.kdeplot(data=frame, x="a", hue="g", ax=first, legend=False)
    sns.kdeplot(data=frame, x="a", hue="g", ax=second, legend=False)
    _axes_legend(first, first, ["wrong", "answer"])
    _axes_legend(second, second, ["p", "q"])

    assert [name for _, name in _named(fig)][-2:] == ["p", "q"]
