"""A colorbar must not move its panel out of the grid position it was drawn in.

Attaching a colorbar re-parents its panel into a fresh sub-gridspec where
the panel sits at the origin. A panel is keyed by where its span starts, so
two ``sns.heatmap`` calls into a ``subplots(1, 2)`` both reported ``(0, 0)``
and were emitted as one position holding two ``heat`` layers -- a reader
handed a single panel to page two layers of, with one set of titles and
axis labels, instead of two charts to move between (#518).

Only figures with more than one colorbar-bearing panel were affected: a
heatmap beside a bar chart was fine, because only the heatmap got
re-parented.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _occupied(fig) -> list[list[list[str]]]:
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return [
        [[layer["type"].value for layer in cell["layers"]] for cell in row]
        for row in grid
    ]


def _data() -> np.ndarray:
    return np.arange(16).reshape(4, 4)


def test_two_heatmaps_side_by_side_are_two_panels() -> None:
    """The reported reproduction."""
    fig, axs = plt.subplots(1, 2)
    sns.heatmap(_data(), ax=axs[0])
    sns.heatmap(_data(), ax=axs[1])

    assert _occupied(fig) == [[["heat"], ["heat"]]]


def test_a_grid_of_heatmaps_keeps_every_one_in_its_own_position() -> None:
    """Four, so a fix that merely separates two is not enough to pass."""
    fig, axs = plt.subplots(2, 2)
    for ax in axs.flat:
        sns.heatmap(_data(), ax=ax)

    assert _occupied(fig) == [
        [["heat"], ["heat"]],
        [["heat"], ["heat"]],
    ]


def test_a_lone_heatmap_is_still_one_panel() -> None:
    """Resolving through the nesting must not invent a position either."""
    fig, ax = plt.subplots()
    sns.heatmap(_data(), ax=ax)

    assert _occupied(fig) == [[["heat"]]]


def test_a_heatmap_beside_a_bar_chart_keeps_working() -> None:
    """The case that was already correct, because only one panel re-parents."""
    fig, axs = plt.subplots(1, 2)
    sns.heatmap(_data(), ax=axs[0])
    axs[1].bar(["p", "q"], [1, 2])

    assert _occupied(fig) == [[["heat"], ["bar"]]]
