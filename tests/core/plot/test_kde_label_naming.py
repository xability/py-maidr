"""Curves drawn one call each are named by the labels the legend shows.

A chart of several density curves is often drawn a call per curve, each
given its name directly, and the legend prints those names::

    sns.kdeplot(data1, label="Group 1 KDE", ax=ax)
    sns.kdeplot(data2, label="Group 2 KDE", ax=ax)
    ax.legend()

Each call drew one curve, which the colour match that names a ``hue`` split
declines, so the three ``smooth`` layers carried no name and were announced
identically. The same held for curves drawn with ``ax.plot(..., label=...)``.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from scipy.stats import gaussian_kde  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

LABELS = ["Group 1 KDE", "Group 2 KDE", "Group 3 KDE"]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _samples() -> list[np.ndarray]:
    rng = np.random.default_rng(0)
    return [rng.normal(loc, scale, 200) for loc, scale in ((0, 1), (2, 0.5), (-2, 1.5))]


def _names(fig) -> list[str | None]:
    """The name of each smooth layer, in the order drawn."""
    return [
        plot.schema.get("name")
        for plot in FigureManager.get_maidr(fig).plots
        if plot.type == PlotType.SMOOTH
    ]


def test_seaborn_curves_drawn_a_call_each_are_named_by_their_labels() -> None:
    fig, ax = plt.subplots()
    for data, label in zip(_samples(), LABELS):
        sns.kdeplot(data, label=label, ax=ax)
    ax.legend(title="Group")

    assert _names(fig) == LABELS


def test_plotted_kde_curves_are_named_by_their_labels() -> None:
    fig, ax = plt.subplots()
    for data, label in zip(_samples(), LABELS):
        grid = np.linspace(data.min() - 1, data.max() + 1, 200)
        ax.plot(grid, gaussian_kde(data)(grid), label=label)
    ax.legend(title="Group")

    assert _names(fig) == LABELS


def test_the_only_curve_of_a_legend_is_left_unnamed() -> None:
    """A name on the chart's only named thing implies another to tell apart."""
    fig, ax = plt.subplots()
    sns.kdeplot(_samples()[0], label="Group 1 KDE", ax=ax)
    ax.legend()

    assert _names(fig) == [None]


def test_labels_no_legend_shows_are_not_names() -> None:
    fig, ax = plt.subplots()
    for data, label in zip(_samples(), LABELS):
        sns.kdeplot(data, label=label, ax=ax)

    assert _names(fig) == [None, None, None]


def test_a_hue_split_is_still_named_by_its_colours() -> None:
    """The colour match keeps naming the curves of one call."""
    samples = _samples()
    fig, ax = plt.subplots()
    sns.kdeplot(
        x=np.concatenate(samples[:2]),
        hue=np.repeat(["a", "b"], 200),
        ax=ax,
    )

    assert sorted(_names(fig)) == ["a", "b"]
