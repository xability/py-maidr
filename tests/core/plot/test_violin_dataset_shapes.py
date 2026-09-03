"""
The box layer of ``ax.violinplot`` counts datasets the way matplotlib does.

Matplotlib hands the ``dataset`` argument to ``cbook._reshape_2D``, whose rule
is: a list of iterables is one dataset per *element*, while a 2-D ndarray is
one dataset per *column* (a DataFrame is unpacked to an ndarray first). The
KDE layer is built from the ``bodies`` matplotlib drew and so always agrees
with it. The box layer read the call's arguments itself and applied the list
rule to everything, so a ``(100, 3)`` array -- three drawn violins -- emitted
100 box records named ``Group 1..100``, each summarising three numbers, with
100 ``nth-child`` selectors pointing at segments that do not exist. A
DataFrame passed positionally, or any data passed as ``dataset=`` (the
parameter's real name), was not recognised at all, and the box layer was
silently not registered (#705).

What these assert is the one thing a reader depends on: the box layer has
exactly one record and one selector per violin matplotlib drew.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402,F401  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

#: Two violins of five values, the shape the orientation tests draw.
LIST_OF_LISTS = [[1, 2, 3, 4, 9], [2, 3, 4, 5, 6]]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _rng() -> np.random.Generator:
    return np.random.default_rng(705)


def _box_layer(fig):
    """The figure's ``violin_box`` layer, or ``None`` when none registered."""
    layers = [
        plot
        for plot in FigureManager.get_maidr(fig).plots
        if plot.type is PlotType.VIOLIN_BOX
    ]
    assert len(layers) <= 1, f"expected at most one box layer, got {len(layers)}"
    return layers[0] if layers else None


#: ``(positional dataset, keyword arguments)`` pairs, one per shape
#: ``Axes.violinplot`` accepts; the ``id`` names the shape.
SHAPES = [
    pytest.param(LIST_OF_LISTS, {}, id="list of lists"),
    pytest.param(np.array(LIST_OF_LISTS), {}, id="ndarray of the same lists"),
    pytest.param(_rng().normal(size=(100, 3)), {}, id="ndarray (100, 3)"),
    pytest.param(
        [_rng().normal(size=100) for _ in range(3)], {}, id="list of 3 arrays"
    ),
    pytest.param([[1, 2, 3], [4, 5, 6, 7, 8]], {}, id="ragged list"),
    pytest.param(_rng().normal(size=100), {}, id="1-D array"),
    pytest.param(pd.DataFrame(_rng().normal(size=(100, 3))), {}, id="DataFrame"),
]


@pytest.mark.parametrize(("dataset", "kwargs"), SHAPES)
def test_one_box_record_and_selector_per_drawn_violin(dataset, kwargs) -> None:
    fig, ax = plt.subplots()
    parts = ax.violinplot(dataset, **kwargs)
    drawn = len(parts["bodies"])
    assert drawn > 0

    layer = _box_layer(fig)
    assert layer is not None, "the box layer was not registered"
    schema = layer.render()

    assert len(schema["data"]) == drawn
    assert len(schema["selectors"]) == drawn


def test_dataset_keyword_gets_a_box_layer() -> None:
    """``dataset=`` is the parameter's real name and reads like the positional."""
    fig, ax = plt.subplots()
    parts = ax.violinplot(dataset=[_rng().normal(size=100) for _ in range(3)])
    drawn = len(parts["bodies"])
    assert drawn == 3

    layer = _box_layer(fig)
    assert layer is not None, "the box layer was not registered"
    schema = layer.render()

    assert len(schema["data"]) == drawn
    assert len(schema["selectors"]) == drawn


def test_columns_of_a_2d_array_are_the_violins() -> None:
    """Each box record summarises the column matplotlib drew, not a row of it."""
    data = _rng().normal(size=(100, 3)) + np.array([0.0, 10.0, 20.0])
    fig, ax = plt.subplots()
    ax.violinplot(data)

    layer = _box_layer(fig)
    assert layer is not None
    medians = [record["q2"] for record in layer.render()["data"]]

    assert medians == pytest.approx([float(np.median(data[:, j])) for j in range(3)])
