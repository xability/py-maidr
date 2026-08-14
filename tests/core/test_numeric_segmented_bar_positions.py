"""A stacked or dodged bar chart with a numeric x produced no HTML.

The segmented half of #382. `GroupedBarPlot._extract_grouped_bar_data` carried
its own copy of the count check that #383 replaced in `BarPlot`::

    for i, container in enumerate(plot):
        if len(level) != len(container.patches):
            return None            # -> ExtractionError -> nothing renders

Same cause: matplotlib puts exactly one tick per category on a categorical
axis, so the counts agree by construction, and on a numeric axis the tick
locator picks its own breaks, so they do not (#384).

    stacked, categorical x              ok
    stacked, NUMERIC x                  ** ExtractionError
    stacked, numeric x + set_xticks     ok

Which is the stacked half of how anyone writes this::

    x = np.arange(len(species))
    ax.bar(x, first, label="first")
    ax.bar(x, second, bottom=first, label="second")

The labels are decided once for the layer rather than per container, because
every series of a segmented chart shares one category axis — a per-container
answer could name a category in one series and a position in the next.
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
LOWER = np.array([10.0, 20.0, 30.0])
UPPER = np.array([30.0, 20.0, 10.0])


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _layer(fig) -> dict:
    """The one emitted layer of the first subplot cell."""
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return grid[0][0]["layers"][0]


def _stack(ax, positions) -> None:
    """Two series stacked over *positions*, with a legend naming them."""
    ax.bar(positions, LOWER, bottom=np.zeros(len(LOWER)), label="lower")
    ax.bar(positions, UPPER, bottom=LOWER, label="upper")
    ax.legend()


def test_a_stacked_chart_over_numeric_positions_renders() -> None:
    """The reproduction, which produced no HTML at all.

    Rendered as well as read, because the old failure happened during
    extraction and there was no schema to inspect.
    """
    fig, ax = plt.subplots()
    _stack(ax, np.arange(len(SPECIES)))

    layer = _layer(fig)

    assert layer["type"].value == "stacked_bar"
    assert [[point["x"] for point in series] for series in layer["data"]] == [
        ["0", "1", "2"],
        ["0", "1", "2"],
    ]
    assert maidr.render(fig) is not None


def test_a_categorical_stacked_chart_still_announces_its_names() -> None:
    """The half that must not move.

    A reader has to hear "Adelie", not "0". Using positions unconditionally
    would pass silently as ``0 1 2`` and read as a working chart, which is
    worse than the failure being fixed.
    """
    fig, ax = plt.subplots()
    _stack(ax, SPECIES)

    assert [
        [point["x"] for point in series] for series in _layer(fig)["data"]
    ] == [SPECIES, SPECIES]


def test_the_series_names_are_unaffected() -> None:
    """`z` names the series and comes from the legend, not the category axis.

    Worth asserting in both readings: the labels changing source must not
    disturb which series a bar belongs to, and a reader who loses "upper" and
    "lower" cannot tell the two apart however good the categories are.
    """
    for positions in (SPECIES, np.arange(len(SPECIES))):
        fig, ax = plt.subplots()
        _stack(ax, positions)

        series_names = [series[0]["z"] for series in _layer(fig)["data"]]

        assert series_names == ["lower", "upper"]
        plt.close(fig)


def test_the_same_chart_with_ticks_set_is_unchanged() -> None:
    """The spelling that always worked, because the counts lined up.

    `set_xticks(x, labels)` gives one tick per bar, so the labels win. This is
    the control showing the fallback is a fallback rather than a replacement.
    """
    fig, ax = plt.subplots()
    positions = np.arange(len(SPECIES))
    _stack(ax, positions)
    ax.set_xticks(positions, SPECIES)

    assert [
        [point["x"] for point in series] for series in _layer(fig)["data"]
    ] == [SPECIES, SPECIES]


def test_a_horizontal_stack_over_numeric_positions() -> None:
    """The mirror, which could not be written until `left=` was recognised.

    `ax.barh(..., left=...)` is how a stacked bar is written horizontally.
    The patch used to classify on ``"bottom" in kwargs`` alone, so this
    arrived as two independent `bar` layers -- the numbers right, the layer
    count plausible, and a reader never told the second sits on top of the
    first. This test was originally named for that defect so it would fail
    the day it was fixed; #385 fixed it, so here is what it should say.

    A horizontal bar reads its label off y and its magnitude off x, through
    the mirrored branch of the shared position formatter, so it exercises
    what the vertical cases above cannot.
    """
    fig, ax = plt.subplots()
    positions = np.arange(len(SPECIES))
    ax.barh(positions, LOWER, left=np.zeros(len(LOWER)), label="lower")
    ax.barh(positions, UPPER, left=LOWER, label="upper")
    ax.legend()

    layer = _layer(fig)

    assert layer["type"].value == "stacked_bar"
    assert [[point["y"] for point in series] for series in layer["data"]] == [
        ["0", "1", "2"],
        ["0", "1", "2"],
    ]
    assert [[point["x"] for point in series] for series in layer["data"]] == [
        list(LOWER),
        list(UPPER),
    ]
    assert [series[0]["z"] for series in layer["data"]] == ["lower", "upper"]


def test_a_plain_horizontal_bar_is_still_plain() -> None:
    """The control for reading `left`: no baseline, no stack.

    `left` names a stacked bar's baseline the way `bottom` does for a
    vertical one, so a `barh` without it must stay a plain bar -- otherwise
    every horizontal bar chart would be announced as a stack of one.
    """
    fig, ax = plt.subplots()
    ax.barh(SPECIES, LOWER)

    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]

    assert [layer["type"].value for layer in grid[0][0]["layers"]] == ["bar"]


def test_an_explicit_none_baseline_still_reaches_dodge_detection() -> None:
    """`bottom=None` is not a baseline, and used to skip the dodge check.

    The old test was ``if "bottom" in kwargs``, so passing it explicitly as
    ``None`` -- which matplotlib treats exactly as omitting it -- took the
    stacked branch's `else` away and dodge detection never ran. The inner
    ``is not None`` guard kept the layer from being called stacked, so the
    result was a *plain* bar where a dodged one was drawn.

    Reading the value rather than the key fixes it as a side effect, and this
    is here so the fix is deliberate rather than incidental.
    """
    fig, ax = plt.subplots()
    positions = np.arange(len(SPECIES), dtype=float)
    ax.bar(positions - 0.2, LOWER, 0.4, bottom=None, label="lower")
    ax.bar(positions + 0.2, UPPER, 0.4, bottom=None, label="upper")
    ax.legend()

    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    types = [layer["type"].value for layer in grid[0][0]["layers"]]

    assert "stacked_bar" not in types, "None is not a baseline"
    assert types == ["dodged_bar"], types
