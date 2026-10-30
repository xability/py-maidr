"""A layer on either axes of a ``twinx`` chart carries the chart's title.

``ax.twinx()`` draws a second axes over the first, and the layers of both are
read as one chart. A title set on either is drawn over both, but each layer
took its title from its own axes alone, so the layers on the untitled one had
none. ``plt.title()`` after ``twinx()`` titles the twin, so on the gallery's
bar-and-line chart the bars had no title and the chart was named "Chart with
2 layers"; Excel's combo chart titles the primary axes, so its secondary-axis
line had none.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _titles(fig) -> list[tuple[str, str]]:
    """Each layer's type and title, in the order they were drawn."""
    return [
        (plot.type.value, plot.schema["title"])
        for plot in FigureManager.get_maidr(fig).plots
    ]


def test_a_title_set_on_the_twin_names_the_layer_under_it() -> None:
    """The gallery's chart: bars on the first axes, ``plt.title`` on the twin."""
    fig, ax1 = plt.subplots()
    ax1.bar(["a", "b", "c"], [3, 5, 2])
    ax2 = ax1.twinx()
    ax2.plot(["a", "b", "c"], [10, 30, 20])
    plt.title("Multilayer Plot Example")

    assert _titles(fig) == [
        ("bar", "Multilayer Plot Example"),
        ("line", "Multilayer Plot Example"),
    ]


def test_a_title_set_on_the_first_axes_names_the_twins_layer() -> None:
    """Excel's combo chart: the title on the primary axes, a line on the twin."""
    fig, ax1 = plt.subplots()
    ax1.set_title("North revenue and margin")
    ax1.bar(["Q1", "Q2", "Q3"], [3, 5, 2])
    ax1.twinx().plot(["Q1", "Q2", "Q3"], [0.1, 0.3, 0.2])

    assert [title for _, title in _titles(fig)] == ["North revenue and margin"] * 2


def test_a_twiny_layer_takes_the_title_too() -> None:
    """``twiny`` twins the other way round, and the title is shared the same."""
    fig, ax1 = plt.subplots()
    ax1.set_title("Two scales")
    ax1.plot([1, 2, 3], [4, 5, 6])
    ax1.twiny().plot([10, 20, 30], [4, 5, 6])

    assert [title for _, title in _titles(fig)] == ["Two scales"] * 2


def test_three_twinned_axes_share_the_one_title() -> None:
    fig, ax1 = plt.subplots()
    ax1.bar(["a", "b"], [1, 2])
    ax2 = ax1.twinx()
    ax2.plot(["a", "b"], [3, 4])
    ax3 = ax1.twinx()
    ax3.plot(["a", "b"], [30, 40])
    ax3.set_title("Three axes")

    assert [title for _, title in _titles(fig)] == ["Three axes"] * 3


def test_each_axes_keeps_a_title_of_its_own() -> None:
    fig, ax1 = plt.subplots()
    ax1.set_title("Left")
    ax1.bar(["a", "b"], [1, 2])
    ax2 = ax1.twinx()
    ax2.set_title("Right", loc="center")
    ax2.plot(["a", "b"], [3, 4])

    assert [title for _, title in _titles(fig)] == ["Left", "Right"]


def test_subplots_sharing_an_axis_are_not_twins() -> None:
    """``sharex=True`` panels are separate charts; one's title stays its own."""
    fig, (top, bottom) = plt.subplots(2, 1, sharex=True)
    top.set_title("Top panel")
    top.plot([1, 2, 3], [1, 2, 3])
    bottom.plot([1, 2, 3], [3, 2, 1])

    assert [title for _, title in _titles(fig)] == ["Top panel", ""]
