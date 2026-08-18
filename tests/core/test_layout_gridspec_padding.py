"""A gridspec used for proportions is not a grid of navigable positions.

A panel is keyed by where its span starts and the emitted grid is sized
from the largest start seen. That reads a gridspec as a grid of positions,
which it is only when every panel occupies exactly one cell.

``seaborn.jointplot`` does not. ``JointGrid`` lays three panels out on a
6x6 gridspec to get the marginal-to-joint size ratio, so the largest start
forced six columns for two occupied ones and the reader met nine panels
holding nothing on the way between the three real ones (#513).

The counterpart matters as much: a figure whose gridspec really is its
grid must keep the indices it authored, including a position it left
empty on purpose between two panels.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _shape(fig) -> tuple[int, int]:
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return len(grid), len(grid[0])


def _occupied(fig) -> list[list[list[str]]]:
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return [
        [[layer["type"].value for layer in cell["layers"]] for cell in row]
        for row in grid
    ]


def _joint(**kwargs):
    df = pd.DataFrame({"x": np.arange(30) % 7, "y": (np.arange(30) * 3) % 11})
    return sns.jointplot(data=df, x="x", y="y", **kwargs).figure


@pytest.mark.parametrize(
    "kwargs", [{}, {"marginal_ticks": True}], ids=["plain", "ticks"]
)
def test_a_jointplot_is_the_three_panels_it_draws(kwargs) -> None:
    """Not those three plus nine of layout padding."""
    fig = _joint(**kwargs)

    assert _shape(fig) == (2, 2)
    assert _occupied(fig) == [
        [["hist"], []],
        [["point"], ["hist"]],
    ]


def test_a_grid_that_is_a_grid_keeps_the_positions_it_authored() -> None:
    """An empty panel between two drawn ones is on the screen, so keep it.

    Every panel here occupies one cell, which is what makes the gridspec's
    indices positions rather than proportions.
    """
    fig, axs = plt.subplots(1, 3)
    axs[0].bar(["p", "q"], [1, 2])
    axs[2].bar(["p", "q"], [3, 4])

    assert _shape(fig) == (1, 3)
    assert _occupied(fig) == [[["bar"], [], ["bar"]]]


def test_a_spanning_panel_still_leaves_its_neighbour_empty() -> None:
    """Ranking must not collapse a hole a spanning panel really leaves."""
    fig = plt.figure()
    top = plt.subplot2grid((2, 2), (0, 0), colspan=2, fig=fig)
    left = plt.subplot2grid((2, 2), (1, 0), fig=fig)
    right = plt.subplot2grid((2, 2), (1, 1), fig=fig)
    for ax in (top, left, right):
        ax.bar(["p", "q"], [1, 2])

    assert _shape(fig) == (2, 2)
    assert _occupied(fig) == [[["bar"], []], [["bar"], ["bar"]]]


def test_a_colorbar_does_not_become_a_row_and_column_of_its_own() -> None:
    """A ranked axes that holds no panel must not enlarge the grid.

    A heatmap's colorbar carries a subplotspec of its own -- row 1,
    column 1 of a 3x2 -- so it takes a rank. The grid is sized from the
    largest rank a *panel* reaches rather than the largest rank issued,
    which is what keeps that from handing the reader a second row and
    column to arrow through: the phantom panel #369 removed at the layer
    level, back at grid level.
    """
    fig, ax = plt.subplots()
    sns.heatmap(np.arange(16).reshape(4, 4), ax=ax)

    assert _shape(fig) == (1, 1)
    assert _occupied(fig) == [[["heat"]]]


def test_a_pairplot_keeps_every_one_of_its_cells() -> None:
    """Its panels are one cell each, so nothing is ranked away."""
    df = pd.DataFrame(
        {
            "a": np.arange(20) % 5,
            "b": (np.arange(20) * 2) % 7,
            "c": (np.arange(20) * 3) % 4,
        }
    )

    assert _shape(sns.pairplot(df).figure) == (3, 3)
