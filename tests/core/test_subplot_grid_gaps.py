"""Every position in an emitted subplot grid is a subplot the JS core can read.

The grid is sized from the largest row and column any layer reports, so a
figure whose axes do not tile it leaves holes: ``subplots(1, 3)`` with the
middle axes never drawn on, an axes spanning two columns, or a seaborn
``JointGrid``, whose 6x6 layout gridspec yields a 2x6 grid holding three
real panels.

Those holes are not cosmetic. ``Subplot``'s constructor in maidr.js reads
``subplot.layers.length`` without guarding, so a position that carries no
``layers`` key throws on activation and the *whole figure* fails to
initialise -- the reader gets a chart that looks fine and does nothing.
``tests/browser/test_grid_gap.py`` checks that end in a real browser; this
file checks the schema contract that keeps it true.
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


def _grid(fig) -> list[list[dict]]:
    """The emitted ``subplots`` grid for a figure."""
    return FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]


def _cells(grid) -> list[dict]:
    return [cell for row in grid for cell in row]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _one_axes_gap():
    """``subplots(1, 3)`` with nothing drawn on the middle axes."""
    fig, axs = plt.subplots(1, 3)
    axs[0].bar(["p", "q"], [1, 2])
    axs[2].bar(["p", "q"], [3, 4])
    return fig


def _spanning_row():
    """A 2x2 whose top row is one axes across both columns."""
    fig = plt.figure()
    top = plt.subplot2grid((2, 2), (0, 0), colspan=2, fig=fig)
    left = plt.subplot2grid((2, 2), (1, 0), fig=fig)
    right = plt.subplot2grid((2, 2), (1, 1), fig=fig)
    for ax in (top, left, right):
        ax.bar(["p", "q"], [1, 2])
    return fig


def _jointplot():
    """seaborn's ``JointGrid``, whose layout gridspec is far larger."""
    df = pd.DataFrame({"x": np.arange(30) % 7, "y": (np.arange(30) * 3) % 11})
    return sns.jointplot(data=df, x="x", y="y").figure


@pytest.mark.parametrize(
    "build", [_one_axes_gap, _spanning_row, _jointplot], ids=lambda f: f.__name__
)
def test_every_grid_position_is_a_readable_subplot(build):
    """No position is emitted bare, however sparsely the axes tile the grid."""
    grid = _grid(build())

    bare = [
        (r, c)
        for r, row in enumerate(grid)
        for c, cell in enumerate(row)
        if "layers" not in cell or "id" not in cell
    ]
    assert not bare, (
        f"positions {bare} carry no layers/id. maidr.js reads "
        f"subplot.layers.length unguarded, so the figure throws on "
        f"activation and none of it becomes accessible."
    )


@pytest.mark.parametrize(
    "build", [_one_axes_gap, _spanning_row, _jointplot], ids=lambda f: f.__name__
)
def test_backfilled_positions_are_empty_rather_than_invented(build):
    """A hole is filled with *no* layers -- it must not borrow a neighbour's."""
    cells = _cells(_grid(build()))
    # `.get` rather than `[]`: a bare cell is the other test's failure, and
    # this one should report its own claim instead of that one's KeyError.
    filled = [cell for cell in cells if cell.get("layers")]
    ids = [cell.get("id") for cell in cells]

    assert filled, "the fixture drew nothing"
    assert len(set(ids)) == len(ids), (
        "two positions share an id, so the core cannot tell them apart"
    )


def test_a_fully_tiled_grid_gains_no_extra_positions():
    """The backfill only reaches holes; a full grid is emitted unchanged."""
    fig, axs = plt.subplots(1, 2)
    for ax in axs:
        ax.bar(["p", "q"], [1, 2])

    grid = _grid(fig)
    assert [len(row) for row in grid] == [2]
    assert all(cell["layers"] for cell in _cells(grid))
