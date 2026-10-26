"""Naming an axis's ticks leaves its numbers to maidr.js's default format.

``ax.set_xticks(positions, labels)`` installs a ``FuncFormatter`` around
matplotlib's own lookup of each tick's label, which names the ticks and
formats no other value. It was read as an unknown function and the axis was
given the format ``String(value)``, which spells a number out in full: the
gallery's Manhattan plot names its chromosome ticks this way and announced
every position as "Genomic position is 2.8689008371944547".
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.format_config import JSBodyConverter, extract_axis_format  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def test_ticks_named_with_their_positions_set_no_format() -> None:
    fig, ax = plt.subplots()
    ax.scatter([2.87, 140.5, 396.76], [0.07, 9.4, 1.2])
    ax.set_xticks([60.0, 200.0, 330.0], ["chr1", "chr2", "chr3"])

    assert "x" not in extract_axis_format(ax)


def test_tick_labels_set_on_fixed_ticks_set_no_format() -> None:
    fig, ax = plt.subplots()
    ax.plot([10, 20, 30], [1.5, 2.5, 3.5])
    ax.set_yticks([2, 3])
    ax.set_yticklabels(["low", "high"])

    assert "y" not in extract_axis_format(ax)


def test_a_function_of_the_callers_own_still_reads_the_value_as_is() -> None:
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 5, 6])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"<{value}>"))

    assert extract_axis_format(ax)["x"]["function"] == (
        JSBodyConverter.default_format_to_js()
    )


def test_a_manhattan_plot_with_named_chromosomes_leaves_x_unformatted() -> None:
    """The gallery's chart, cut down: positions along x, chromosome ticks."""
    rng = np.random.default_rng(1)
    positions = np.sort(rng.uniform(0, 400, 40))
    pvalues = rng.uniform(0.001, 1, 40)
    fig, ax = plt.subplots()
    points = ax.scatter(positions, -np.log10(pvalues))
    ax.set_xticks([100.0, 300.0], ["chr1", "chr2"])
    ax.set_xlabel("Genomic position")
    ax.set_ylabel("-log10 p")
    maidr.manhattan(
        points,
        significance=2.0,
        labels=[f"rs{1000 + i}" for i in range(40)],
        groups=["chr1" if p < 200 else "chr2" for p in positions],
    )

    (plot,) = FigureManager.get_maidr(fig).plots
    axes = plot.schema["axes"]
    assert "format" not in axes["x"]
