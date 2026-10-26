"""Neighbouring histogram bins share one number for the edge between them.

A bin's edges are computed from its bar's position and width, and a bin's
upper edge and the next bin's lower edge come out of different sums. On the
iris petal lengths (1.0 to 6.9 cm in twenty bins) one bin ended at 3.95 and
the next began at 3.9499999999999997, so with the axis's one decimal they were
announced as overlapping: "3.7 through 4.0", then "3.9 through 4.2".
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _bins(fig) -> list[dict]:
    (plot,) = FigureManager.get_maidr(fig).plots
    return plot.schema["data"]


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_each_bin_starts_where_the_last_one_ended(orientation: str) -> None:
    fig, ax = plt.subplots()
    ax.hist(np.linspace(1.0, 6.9, 150), bins=20, orientation=orientation)
    low, high = ("xMin", "xMax") if orientation == "vertical" else ("yMin", "yMax")

    bins = _bins(fig)
    assert len(bins) == 20
    for before, after in zip(bins, bins[1:]):
        assert before[high] == after[low]


def test_the_iris_edge_is_one_number() -> None:
    """The edge the reader heard as both 4.0 and 3.9."""
    fig, ax = plt.subplots()
    ax.hist(np.linspace(1.0, 6.9, 150), bins=20)

    bins = _bins(fig)
    assert bins[9]["xMax"] == bins[10]["xMin"] == 3.95
    assert bins[10]["x"] == pytest.approx((3.95 + 4.245) / 2)
