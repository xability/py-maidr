"""
The KDE layer keeps the bottom level of every violin, and renders quietly.

A violin polygon repeats its start vertex as its closing vertex and its
turn-around at the top, so one side of the outline holds 103 knots for 100
distinct y values -- the duplicates at the very bottom and the very top, at
identical x. ``interp1d(assume_sorted=True)`` built on those knots and asked
for exactly ``y_min`` divides by the zero gap between the two bottom knots:
scipy printed ``invalid value encountered in divide`` to the user's console
on every violin render, the level came back NaN, and the NaN guard silently
dropped it. The emitted y range began one level above the drawn one (#705).

Seaborn and matplotlib both draw the polygon this way, so both are covered.
"""

from __future__ import annotations

import warnings

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

import maidr  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _seaborn_violins():
    rng = np.random.default_rng(705)
    cats = [cat for cat in ("ash", "birch", "cedar") for _ in range(40)]
    vals = np.concatenate([rng.normal(loc, 1.0, 40) for loc in range(3)]).tolist()
    fig, ax = plt.subplots()
    sns.violinplot(x=cats, y=vals, ax=ax)
    return fig, ax


def _matplotlib_violins():
    rng = np.random.default_rng(705)
    fig, ax = plt.subplots()
    ax.violinplot([rng.normal(loc, 1.0, 40) for loc in range(3)])
    return fig, ax


FIGURES = [
    pytest.param(_seaborn_violins, id="seaborn"),
    pytest.param(_matplotlib_violins, id="matplotlib"),
]


def _kde_layer(fig):
    layers = [
        plot
        for plot in FigureManager.get_maidr(fig).plots
        if plot.type is PlotType.VIOLIN_KDE
    ]
    assert len(layers) == 1, f"expected one KDE layer, got {len(layers)}"
    return layers[0]


@pytest.mark.parametrize("draw", FIGURES)
def test_render_raises_no_runtime_warning(draw) -> None:
    """Nothing scipy has to say reaches a screen-reader user's console."""
    fig, _ = draw()

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        maidr.render(fig)


@pytest.mark.parametrize("draw", FIGURES)
def test_the_lowest_level_of_every_violin_is_read(draw) -> None:
    """The emitted y range of each violin starts where the drawn polygon does."""
    fig, ax = draw()
    maidr.render(fig)
    violins = _kde_layer(fig).schema["data"]

    bodies = [c for c in ax.collections if isinstance(c, PolyCollection)]
    assert len(bodies) == len(violins) == 3

    for body, points in zip(bodies, violins):
        drawn_min = float(np.asarray(body.get_paths()[0].vertices)[:, 1].min())
        assert min(point["y"] for point in points) == drawn_min
