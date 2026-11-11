"""A title that is not drawn is not read.

``set_visible(False)`` hides a title and keeps its string, which
``Axes.get_title()`` and ``Figure.get_suptitle()`` return as readily as a
drawn one's. The legacy candlestick example titles its volume axes "Volume
Chart" and hides it, and the volume layer was read as "Volume Chart" over a
chart that shows only "Stock Price Candlestick Chart".
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


def _titles(fig) -> list[str]:
    """Each layer's title, in the order the layers were drawn."""
    return [plot.schema["title"] for plot in FigureManager.get_maidr(fig).plots]


def test_a_hidden_title_names_no_layer() -> None:
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    ax.set_title("Hidden")
    ax.title.set_visible(False)

    assert _titles(fig) == [""]


def test_a_hidden_title_gives_way_to_the_twins_drawn_one() -> None:
    """The legacy candlestick example: the volume axes' title is hidden."""
    fig, ax1 = plt.subplots()
    ax1.bar(["a", "b"], [1, 2])
    ax2 = ax1.twinx()
    ax2.plot(["a", "b"], [3, 4])
    ax2.set_title("Volume Chart")
    ax2.title.set_visible(False)
    ax1.set_title("Stock Price Candlestick Chart")

    assert _titles(fig) == ["Stock Price Candlestick Chart"] * 2


def test_a_twins_hidden_title_names_neither_layer() -> None:
    fig, ax1 = plt.subplots()
    ax1.bar(["a", "b"], [1, 2])
    ax2 = ax1.twinx()
    ax2.plot(["a", "b"], [3, 4])
    ax2.set_title("Volume Chart")
    ax2.title.set_visible(False)

    assert _titles(fig) == ["", ""]


def test_a_hidden_suptitle_names_no_figure() -> None:
    fig, axs = plt.subplots(1, 2)
    axs[0].bar(["a"], [1])
    axs[1].bar(["b"], [2])
    fig.suptitle("Two panels").set_visible(False)

    schema = FigureManager.get_maidr(fig)._flatten_maidr()

    assert "title" not in {getattr(key, "value", key) for key in schema}
