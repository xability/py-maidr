"""A scatter drawn with ``label=`` is named by it.

Several ``Axes.scatter`` calls, each labelled, are one ``point`` layer per
call. No hue split and no patch names them, so before the collection's own
label was read every layer shipped without a ``name``: a reader of a two-group
scatter got two identical unnamed layers, while matplotlib's legend told the
same groups apart. The line layer already read its line's label; this holds
the point layer to the same rule.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402
from maidr.core.enum import MaidrKey  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _points(figure) -> list[dict]:
    """The rendered ``point`` layers, in registration order."""
    maidr.render(figure)
    return [
        plot.schema
        for plot in FigureManager.get_maidr(figure)._plots
        if plot.schema.get(MaidrKey.TYPE) == "point"
    ]


def test_each_labelled_scatter_call_is_named_by_its_label():
    figure, ax = plt.subplots()
    ax.scatter([1, 2], [2, 3], label="A")
    ax.scatter([3, 4], [4, 5], label="B")
    ax.legend()

    layers = _points(figure)

    assert [layer.get(MaidrKey.NAME) for layer in layers] == ["A", "B"]
    assert [len(layer[MaidrKey.DATA]) for layer in layers] == [2, 2]


def test_the_name_does_not_need_a_legend():
    # The label is the caller's name for the series whether or not a legend
    # is drawn, as it is for a line.
    figure, ax = plt.subplots()
    ax.scatter([1, 2], [2, 3], label="control")

    assert [layer.get(MaidrKey.NAME) for layer in _points(figure)] == ["control"]


@pytest.mark.parametrize("label", [None, "_nolegend_", "_hidden"])
def test_a_scatter_matplotlib_named_stays_unnamed(label):
    # `_child0` for an unlabelled call, `_nolegend_` and any other leading
    # underscore for one kept out of the legend: none is a name the caller
    # chose, so none is announced as one.
    figure, ax = plt.subplots()
    kwargs = {} if label is None else {"label": label}
    ax.scatter([1, 2], [2, 3], **kwargs)
    ax.scatter([3, 4], [4, 5], **kwargs)

    layers = _points(figure)

    assert len(layers) == 2
    assert all(MaidrKey.NAME not in layer for layer in layers)


def test_a_labelled_and_an_unlabelled_call_are_told_apart():
    figure, ax = plt.subplots()
    ax.scatter([1, 2], [2, 3], label="measured")
    ax.scatter([3, 4], [4, 5])

    layers = _points(figure)

    assert [layer.get(MaidrKey.NAME) for layer in layers] == ["measured", None]
