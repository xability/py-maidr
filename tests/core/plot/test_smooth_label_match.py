"""A smooth keyword is a whole word of a line's label, not a substring (#710).

``regplot.patched_plot`` decides that an ``ax.plot`` call drew a fitted
curve by its label, against ``SMOOTH_KEYWORDS``. The match was a substring
one, so ``fit`` answered to Profit, Benefit and Fitness, ``kde`` to Kde and
``density`` to Density, and each such line registered as a SMOOTH layer.

That alone would be a mild mis-typing. What made it a loss is the per-axes
rule in ``Maidr._superseded_line_layers`` (#378): an axes holding a smooth
drops every LINE layer on it, as the duplicate of the curve. Measured::

    ax.plot(..., label="Profit"); ax.plot(..., label="Revenue")
        smooth(1 series)          -- Revenue is not in the schema at all

A reader of that chart hears one "fitted" series and never learns there was
a second. The label is the plainest public API there is, and Profit is an
ordinary thing to plot.

The match is now on whole words for single-word keywords and on the phrase
for multi-word ones, so every label the docs use -- ``LOWESS smooth``,
``KDE``, ``Group 1 KDE``, ``linear fit`` -- still types as a fit, and
``fitted`` joins the list so "Fitted values" keeps its reading.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.patch.regplot import _looks_smooth  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _layers(fig) -> list[tuple[str, int]]:
    """Each emitted layer of the figure's one panel as ``(type, series)``.

    Read from the flattened schema rather than from the registered plots,
    because the flattening pass is where a sibling line is dropped -- the
    registrations alone would show the Revenue line present.
    """
    flat = FigureManager.get_maidr(fig)._flatten_maidr()
    layers = flat["subplots"][0][0]["layers"]
    return [(layer["type"].value, len(layer["data"])) for layer in layers]


def _two_lines(label: str):
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [10, 12, 9], label=label)
    ax.plot([1, 2, 3], [20, 25, 21], label="Other")
    return fig


@pytest.mark.parametrize("label", ["Profit", "Benefit", "Fitness", "Profit margin"])
def test_a_label_that_merely_contains_a_keyword_is_a_line(label):
    assert _layers(_two_lines(label)) == [("line", 2)]


@pytest.mark.parametrize(
    "label",
    ["fit", "KDE", "LOWESS smooth", "linear fit", "Group 1 KDE", "Fitted values"],
)
def test_a_label_that_is_a_keyword_is_still_a_fit(label):
    kinds = [kind for kind, _ in _layers(_two_lines(label))]
    assert "smooth" in kinds


def test_a_phrase_straddling_two_words_does_not_take_the_revenue_line_with_it():
    # The same loss by another door. The phrase keyword "linear fit" was
    # still a substring test, and "Nonlinear fitness" holds those letters
    # across a word break -- so the line typed as a fit and Revenue went
    # with it, exactly the reading #710 was about.
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [10, 12, 9], label="Nonlinear fitness")
    ax.plot([1, 2, 3], [20, 25, 21], label="Revenue")

    assert _layers(fig) == [("line", 2)]


def test_a_profit_line_does_not_take_the_revenue_line_with_it():
    # The regression itself, by name. The mis-typing was the cause; the
    # missing sibling series is what a reader would have met.
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [10, 12, 9], label="Profit")
    ax.plot([1, 2, 3], [20, 25, 21], label="Revenue")

    flat = FigureManager.get_maidr(fig)._flatten_maidr()
    (layer,) = flat["subplots"][0][0]["layers"]
    assert [series[0]["y"] for series in layer["data"]] == [10, 20]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Profit", False),
        ("Benefit", False),
        ("Kde", True),
        ("kde_1", True),
        ("Density", True),
        ("linear regression", True),
        # A multi-word keyword is a phrase that starts on a word boundary. Its
        # last word may run on, as a single-word keyword's may not.
        ("Linear fit", True),
        ("Linear fitting", True),
        ("a linear fit of y", True),
        # The phrase's words are not a boundary of their own: as a substring,
        # "linear fit" spans "...linear" and "fit..." here (#710, again).
        ("Nonlinear fitness", False),
        ("Nonlinear fits", False),
        ("Nonlinear fitting", False),
        # Though "fit" as a whole word of its own still is one.
        ("Nonlinear fit", True),
        ("Fitness benefit", False),
        ("", False),
    ],
)
def test_looks_smooth_asks_for_a_whole_word_or_phrase(label, expected):
    assert _looks_smooth(label) is expected
