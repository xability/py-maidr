"""
A hue-grouped KDE names its curves (#558, the half #559 left).

``sns.kdeplot(hue=...)`` draws one curve per group and #559 left both of them
announced -- but with nothing to tell them apart, so a reader hears the
identical announcement twice::

    smooth(name=None, n=1), smooth(name=None, n=1)

Several ``smooth`` layers over one axis with nothing to tell them apart is the
position ``MaidrLayer.name`` was added for (xability/maidr#828). Each is named
from the legend swatch drawn in **its own colour**, which is the match
``scatterplot.hue_groups`` makes point by point and ``patch/histogram``
container by container.

Not by position: measured on seaborn 0.13.2 the legend runs the reverse of the
draw order -- curves drawn orange then blue against entries listed
``['y', 'x']`` -- so pairing them off gives each curve the other group's name.

Two artists, not one. Measured, ``fill=True`` draws **no lines at all**: two
groups give two ``PolyCollection`` bands and zero ``Line2D`` curves, so a fix
that only matched lines would leave the filled spelling of the same chart
anonymous.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn as sns

from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {"a": rng.normal(size=60), "g": rng.choice(["x", "y"], size=60)}
    )


def _names(fig) -> list:
    """Each layer's group name, or None where it carries none."""
    return [plot.schema.get("name") for plot in FigureManager.get_maidr(fig).plots]


def test_each_curve_is_named_from_the_legend():
    fig, ax = plt.subplots()
    sns.kdeplot(data=_frame(), x="a", hue="g", ax=ax)

    assert len(ax.get_lines()) == 2
    assert _names(fig) == ["x", "y"]


def test_a_filled_kde_is_named_too():
    # The branch a line-only match misses: no `Line2D` at all, two bands.
    fig, ax = plt.subplots()
    sns.kdeplot(data=_frame(), x="a", hue="g", fill=True, ax=ax)

    assert len(ax.get_lines()) == 0
    assert len(ax.collections) == 2
    assert _names(fig) == ["x", "y"]


def test_a_name_is_matched_by_colour_rather_than_by_position():
    # The trap: seaborn lists the legend in the reverse of the draw order, so
    # zipping curves against legend entries gives each the other's name.
    fig, ax = plt.subplots()
    sns.kdeplot(data=_frame(), x="a", hue="g", ax=ax)

    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["y", "x"]
    assert _names(fig) == ["x", "y"]


def test_an_ungrouped_kde_is_one_unnamed_curve():
    # Nothing to be told apart from, and a name would read as though there
    # were.
    fig, ax = plt.subplots()
    sns.kdeplot(data=_frame(), x="a", ax=ax)

    assert _names(fig) == [None]


def test_a_suppressed_legend_leaves_the_curves_unnamed():
    # `legend=False` takes away the only thing that names the colours. The
    # curves are still read; inventing labels for them would not be better.
    fig, ax = plt.subplots()
    sns.kdeplot(data=_frame(), x="a", hue="g", legend=False, ax=ax)

    assert len(_names(fig)) == 2
    assert _names(fig) == [None, None]


def test_a_histogram_s_kde_overlay_is_named_beside_its_bars():
    # `histplot(kde=True, hue=...)` draws both, and #559 named only the bars.
    fig, ax = plt.subplots()
    sns.histplot(data=_frame(), x="a", hue="g", bins=5, kde=True, ax=ax)

    assert sorted(name for name in _names(fig) if name) == ["x", "x", "y", "y"]


# ---------------------------------------------------------------------------
# The guard on the second matching pass, which no seaborn chart reaches.
#
# Comparing the three colour channels alone is what lets an opaque overlay
# curve find the translucent swatch that names it. Two artists separated *by*
# their opacity would then both match the same swatch, so the pass runs only
# where the drawn colours are already distinct without their alpha. Nothing
# seaborn draws puts two hue levels on one hue, so this is asserted against
# the function directly rather than through a chart.
# ---------------------------------------------------------------------------


class _Handle:
    """A legend handle that names one colour, the way seaborn's do."""

    def __init__(self, colour):
        self._colour = colour

    def get_facecolor(self):
        return self._colour


class _Text:
    """A legend entry's label."""

    def __init__(self, text):
        self._text = text

    def get_text(self):
        return self._text


class _Legend:
    """Just enough legend for the colour match."""

    def __init__(self, entries):
        self.legend_handles = [_Handle(colour) for colour, _ in entries]
        self._texts = [_Text(name) for _, name in entries]

    def get_texts(self):
        return self._texts


class _Axes:
    """Just enough axes to carry a legend."""

    def __init__(self, legend):
        self._legend = legend

    def get_legend(self):
        return self._legend


def test_the_hue_pass_names_an_opaque_artist_from_a_translucent_swatch():
    from maidr.patch.kdeplot import _names_for

    legend = _Legend([((0.1, 0.4, 0.7, 0.5), "y"), ((1.0, 0.5, 0.05, 0.5), "x")])
    drawn = [(1.0, 0.5, 0.05, 1.0), (0.1, 0.4, 0.7, 1.0)]

    assert _names_for(_Axes(legend), drawn) == ["x", "y"]


def test_the_hue_pass_declines_when_two_artists_share_a_hue():
    from maidr.patch.kdeplot import _names_for

    # Both drawn in the same colour at different opacities. Whichever swatch
    # the hue matched would claim both, so neither is named.
    legend = _Legend([((0.1, 0.4, 0.7, 0.5), "y"), ((1.0, 0.5, 0.05, 0.5), "x")])
    drawn = [(1.0, 0.5, 0.05, 1.0), (1.0, 0.5, 0.05, 0.3)]

    assert _names_for(_Axes(legend), drawn) == [None, None]


def test_an_exact_match_is_preferred_to_the_hue_pass():
    from maidr.patch.kdeplot import _names_for

    # Where the alphas already agree, the first pass answers and the guard on
    # the second never comes into it -- which is what keeps a chart whose
    # groups really are told apart by opacity working, so long as it names
    # them exactly.
    legend = _Legend([((1.0, 0.5, 0.05, 1.0), "opaque"), ((1.0, 0.5, 0.05, 0.3), "faint")])
    drawn = [(1.0, 0.5, 0.05, 1.0), (1.0, 0.5, 0.05, 0.3)]

    assert _names_for(_Axes(legend), drawn) == ["opaque", "faint"]
