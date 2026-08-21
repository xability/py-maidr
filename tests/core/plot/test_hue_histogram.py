"""
A hue-grouped ``histplot`` announces every group, not just the first (#558).

``sns.histplot(hue=...)`` draws one ``BarContainer`` per group. The patch used
to register one layer and read the **first** container, so every other group
stayed on screen and vanished from the announcement -- with nothing raising,
which is the failure that reads as a complete single-distribution histogram.

Measured on seaborn 0.13.2, sixty observations over two groups, ``bins=5``::

    container 0 heights: [0, 4, 10, 9, 5]     <- group x
    container 1 heights: [1, 11, 8, 8, 4]     <- group y
    layer 0 hist y=[0, 4, 10, 9, 5]           <- only x was announced

The container the patch chose used to be justified as unobservable, on the
grounds that a hue's groups share one binning. The *edges* are shared; the
counts are not, which is what the two rows above show and what these cases
pin.

The split alone is not enough. Several ``hist`` layers over one axis with
nothing to tell them apart is the position ``MaidrLayer.name`` was added for
(xability/maidr#828), so each is named from the legend swatch drawn in its
own colour -- the match ``scatterplot.hue_groups`` already makes point by
point, one level up.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn as sns

import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame(groups: list[str], size: int = 60) -> pd.DataFrame:
    """A frame whose values are fixed, so the counts below are reproducible."""
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {"a": rng.normal(size=size), "g": rng.choice(groups, size=size)}
    )


def _layers(fig) -> list[dict]:
    """Every layer's rendered schema, in registration order."""
    return [plot.schema for plot in FigureManager.get_maidr(fig).plots]


def _counts(fig) -> list[list[float]]:
    """Each layer's per-bin counts."""
    return [[point["y"] for point in layer["data"]] for layer in _layers(fig)]


def _names(fig) -> list:
    """Each layer's group name, or None where it carries none."""
    return [layer.get("name") for layer in _layers(fig)]


def _true_counts(frame: pd.DataFrame, group: str, bins: int) -> list[int]:
    """What the group's own histogram holds, computed independently."""
    edges = np.histogram_bin_edges(frame.a, bins=bins)
    counts, _ = np.histogram(frame.a[frame.g == group], bins=edges)
    return list(counts)


def test_each_hue_group_becomes_its_own_layer():
    frame = _frame(["x", "y"])
    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", hue="g", bins=5, ax=ax)

    assert len(ax.containers) == 2
    assert len(_layers(fig)) == 2


def test_each_layer_announces_its_own_group_s_counts():
    # The heart of it: the second group used to be drawn and never spoken.
    frame = _frame(["x", "y"])
    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", hue="g", bins=5, ax=ax)

    assert _counts(fig) == [
        [float(count) for count in _true_counts(frame, "x", 5)],
        [float(count) for count in _true_counts(frame, "y", 5)],
    ]


def test_each_layer_is_named_from_the_legend():
    frame = _frame(["x", "y"])
    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", hue="g", bins=5, ax=ax)

    assert _names(fig) == ["x", "y"]


def test_a_third_group_is_read_and_named_too():
    # Not a restatement of the pair: the old reading dropped *every* group
    # after the first, so the loss grew with the chart.
    frame = _frame(["x", "y", "z"], size=90)
    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", hue="g", bins=5, ax=ax)

    assert len(ax.containers) == 3
    assert len(_layers(fig)) == 3

    # Paired rather than sorted: three names in *some* order says nothing
    # about whether each sits on its own group's counts, which is the whole
    # question a positional match gets wrong.
    by_name = dict(zip(_names(fig), _counts(fig)))
    assert sorted(by_name) == ["x", "y", "z"]
    for group in ("x", "y", "z"):
        assert by_name[group] == [
            float(count) for count in _true_counts(frame, group, 5)
        ]


@pytest.mark.parametrize("multiple", ["layer", "stack", "dodge", "fill"])
def test_every_layout_splits(multiple):
    # How the groups are arranged against each other is a drawing decision and
    # changes nothing about how many distributions there are.
    frame = _frame(["x", "y"])
    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", hue="g", bins=5, multiple=multiple, ax=ax)

    assert len(_layers(fig)) == 2


def test_a_name_is_matched_by_colour_rather_than_by_position():
    # The trap, measured rather than guarded against in the abstract: on this
    # chart seaborn draws the groups x then y and lists them y then x. So
    # zipping the containers with the legend's entries -- the obvious cheap
    # rule -- gives every layer the *other* group's name, with its own counts
    # underneath.
    #
    # Worth being exact about what these cases do and do not show. Measured on
    # seaborn 0.13.2 the legend is the *exact reverse* of the draw order, for
    # two groups and for three, so a positional rule that read the legend
    # backwards would agree with the colour match on every chart here. The
    # colour match is still what is implemented, because it does not rest on
    # that reversal holding -- it is nothing seaborn documents -- and because
    # it declines rather than mislabels when a legend carries entries that are
    # not group swatches, which `_named_colours` was written for.
    frame = _frame(["x", "y"])
    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", hue="g", bins=5, ax=ax)

    legend_order = [text.get_text() for text in ax.get_legend().get_texts()]
    assert legend_order == ["y", "x"]
    assert _names(fig) == ["x", "y"]

    # And each name really does sit on its own group's counts.
    by_name = dict(zip(_names(fig), _counts(fig)))
    for group in ("x", "y"):
        assert by_name[group] == [
            float(count) for count in _true_counts(frame, group, 5)
        ]


def test_a_single_level_hue_is_one_unnamed_layer():
    # A `hue` whose column holds one value: seaborn draws a single container
    # and still builds a legend naming its colour, which is the one case that
    # reaches the guard. Naming the layer would be *accurate* and still wrong
    # to say -- a name on the only layer of a chart reads as though there were
    # another to tell it from.
    #
    # `label=` plus a later `ax.legend()` does not reach it, measured: the
    # legend does not exist yet when the layer registers, so the colour match
    # declines a step earlier for a different reason.
    frame = _frame(["x", "y"])
    fig, ax = plt.subplots()
    sns.histplot(data=frame[frame.g == "x"], x="a", hue="g", bins=5, ax=ax)

    assert len(ax.containers) == 1
    assert [text.get_text() for text in ax.get_legend().get_texts()] == ["x"]
    assert _names(fig) == [None]


def test_an_ungrouped_histogram_is_one_unnamed_layer():
    # A single distribution has nothing to be told apart from, and a name
    # there would read as though the chart held more.
    frame = _frame(["x", "y"])
    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", bins=5, ax=ax)

    assert len(_layers(fig)) == 1
    assert _names(fig) == [None]


def test_a_suppressed_legend_still_reads_every_group():
    # `legend=False` takes away the only thing that names the colours. The
    # groups are still there and still drawn, so they are still read -- just
    # unnamed, which is the honest answer rather than inventing labels.
    frame = _frame(["x", "y"])
    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", hue="g", bins=5, legend=False, ax=ax)

    assert len(_layers(fig)) == 2
    assert _names(fig) == [None, None]


def test_displot_splits_too():
    # `displot` drives `_DistributionPlotter` directly and reaches only the
    # second patch site, so fixing one and not the other would leave the same
    # chart read differently through its two spellings (#446, #522).
    frame = _frame(["x", "y"])
    grid = sns.displot(data=frame, x="a", hue="g", bins=5)

    assert len(_layers(grid.figure)) == 2


def test_the_figure_still_renders():
    frame = _frame(["x", "y"])
    fig, ax = plt.subplots()
    sns.histplot(data=frame, x="a", hue="g", bins=5, ax=ax)

    assert len(maidr.render(fig)._repr_html_()) > 0
