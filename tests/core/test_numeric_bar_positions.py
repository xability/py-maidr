"""A bar chart with a numeric x produced no HTML at all.

`BarPlot` paired its bars with the labels on the categorical axis and raised
when the counts disagreed. For a categorical x matplotlib puts exactly one
tick per category, so they agree by construction. For a numeric x the tick
locator picks its own breaks, so they have no reason to:

                                                   bars  labels  render
    x = np.arange(len(labels))  [mpl's own recipe]    3      5    raised
    x = np.arange(...), + set_xticks(x, labels)       3      3    ok
    plain categorical strings                         3      3    ok
    numeric x, barh                                   3      8    raised
    numeric x, many bars (20)                        20      8    raised

`ExtractionError` is fatal to the whole render rather than to its own layer,
so the figure produced nothing (#382).

The shape in the first row is matplotlib's own grouped bar chart::

    x = np.arange(len(species))
    ax.bar(x + offset, measurement, width, label=attribute)

which survives in the gallery only because the example goes on to call
`ax.set_xticks(x + width, species)` and make the counts line up by accident.

The count check was guarding something real -- three bars against five labels
would announce the wrong name for every bar -- so it still decides. What
changed is what it decides *between*: labels when they line up, the bars' own
positions when they do not, rather than a reading and nothing.
"""

from __future__ import annotations

import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402

SPECIES = ["Adelie", "Chinstrap", "Gentoo"]
MEASUREMENTS = np.array([18.0, 18.4, 14.9])


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _points(fig) -> list[dict]:
    """The first emitted layer's data."""
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return grid[0][0]["layers"][0]["data"]


def test_matplotlibs_own_grouped_bar_recipe_renders() -> None:
    """The reproduction, in the shape the gallery writes it.

    Without the ``set_xticks`` line the gallery goes on to add, this produced
    no HTML at all. Rendered as well as read, because the old failure happened
    during extraction and there was no schema to inspect.
    """
    fig, ax = plt.subplots()
    ax.bar(np.arange(len(SPECIES)), MEASUREMENTS, 0.25)

    points = _points(fig)

    assert [point["x"] for point in points] == ["0", "1", "2"]
    assert [point["y"] for point in points] == list(MEASUREMENTS)
    assert maidr.render(fig) is not None


def test_a_categorical_bar_still_announces_its_names() -> None:
    """The half that must not move, and the reason the check still decides.

    A reader of a categorical chart has to hear "Adelie", not "0". If the
    positions were used unconditionally this would pass silently as ``0 1 2``
    and every bar would lose its name -- which is a worse defect than the one
    being fixed, because it reads as a working chart.
    """
    fig, ax = plt.subplots()
    ax.bar(SPECIES, MEASUREMENTS)

    assert [point["x"] for point in _points(fig)] == SPECIES


def test_the_gallery_example_with_its_ticks_is_unchanged() -> None:
    """The spelling that always worked, because the counts lined up.

    Calling ``set_xticks(x, labels)`` gives one tick per bar, so the labels
    win and the names are announced -- exactly as before. This is the control
    that shows the fallback is a fallback rather than a replacement.
    """
    fig, ax = plt.subplots()
    positions = np.arange(len(SPECIES))
    ax.bar(positions, MEASUREMENTS, 0.25)
    ax.set_xticks(positions, SPECIES)

    assert [point["x"] for point in _points(fig)] == SPECIES


def test_a_horizontal_numeric_bar_announces_its_positions() -> None:
    """``barh`` reads its label off y and its magnitude off x.

    The centre of a horizontal bar is its ``y + height / 2``, a different
    branch from the vertical case, so the mirror is worth driving rather than
    assuming.
    """
    fig, ax = plt.subplots()
    ax.barh(np.arange(len(SPECIES)), MEASUREMENTS)

    points = _points(fig)

    assert [point["y"] for point in points] == ["0", "1", "2"]
    assert [point["x"] for point in points] == list(MEASUREMENTS)


def test_a_position_is_printed_the_way_an_axis_prints_it() -> None:
    """A bar at x=0 is at "0", not "0.0".

    The centre is a float because the rectangle's geometry is, but a numeric
    axis writes whole numbers without a trailing zero and the announcement
    should match what is on the chart. Half-steps keep their fraction, so
    this is formatting rather than rounding -- a bar really at 1.5 still says
    so.
    """
    fig, ax = plt.subplots()
    ax.bar([0.0, 1.5, 3.0], MEASUREMENTS, 0.5)

    assert [point["x"] for point in _points(fig)] == ["0", "1.5", "3"]


def test_a_large_position_is_not_announced_in_scientific_notation() -> None:
    """``f"{x:g}"`` alone would say "1.23457e+06" for a bar at 1234567.

    Six significant figures, then exponential -- lossy and hard to listen to.
    A large x is overwhelmingly an integer one (an index, an id, a year), so
    integers are formatted exactly and only fractions fall back to ``:g``.
    """
    fig, ax = plt.subplots()
    ax.bar([0, 1234567, 2.5], MEASUREMENTS, 0.4)

    assert [point["x"] for point in _points(fig)] == ["0", "1234567", "2.5"]
