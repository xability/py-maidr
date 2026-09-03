"""Each ``ax.plot()`` call lists its own lines once, and only those.

``line()`` accumulates the lines a layer's calls drew on the axes, so that
several ``ax.plot()`` calls read as one multi-series layer. Appending used to
test ``item not in series`` for every line, an identity walk over everything
already listed -- so an axes built from thousands of ``ax.plot()`` calls paid
a scan per call that grew with the axes (#755).

On the ``Axes.plot`` path that walk could never find anything: matplotlib
hands back the lines it just made, none of which can be listed yet. The
seaborn path is the only one whose ``drawn`` is a diff against a snapshot and
so can overlap an earlier call's lines. These tests pin the invariant the
scan was upholding -- one entry per line, whichever path listed it -- so the
faster append cannot quietly start listing a line twice.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.patch.lineplot import DRAWN_SERIES  # noqa: E402

X = np.arange(4)


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _series(ax) -> list:
    """The lines the axes' layer lists, in the order they were listed."""
    return list(getattr(ax, DRAWN_SERIES))


def _emitted(fig) -> list[dict]:
    """Every layer the first subplot cell emits."""
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return grid[0][0].get("layers", [])


def test_each_plot_call_lists_its_lines_once() -> None:
    """Five calls, five lines; a call drawing two lines lists both."""
    fig, ax = plt.subplots()
    for offset in range(5):
        ax.plot(X, X + offset)
    ax.plot(X, X + 5, X, X + 6)

    series = _series(ax)
    assert len(series) == 7
    assert len({id(line) for line in series}) == 7
    assert series == list(ax.get_lines())

    (layer,) = _emitted(fig)
    assert layer["type"].value == "line"
    assert len(layer["data"]) == 7


def test_a_second_seaborn_lineplot_adds_only_its_own_line() -> None:
    """The path whose ``drawn`` is a diff against a snapshot.

    The second call's snapshot holds the first call's line, so the diff is
    the second line alone -- and the list must not grow by more than that,
    with or without ``ax=``, which is what decides which axes is snapshotted.
    """
    first = pd.DataFrame({"x": X, "y": X})
    second = pd.DataFrame({"x": X, "y": X * 2})

    fig, ax = plt.subplots()
    sns.lineplot(data=first, x="x", y="y", ax=ax)
    sns.lineplot(data=second, x="x", y="y", ax=ax)
    assert len(_series(ax)) == 2
    assert len({id(line) for line in _series(ax)}) == 2
    plt.close(fig)

    plt.figure()
    sns.lineplot(data=first, x="x", y="y")
    sns.lineplot(data=second, x="x", y="y")
    assert len(_series(plt.gca())) == 2
    assert len({id(line) for line in _series(plt.gca())}) == 2


def test_a_step_layer_over_a_plot_call_still_reads_its_own_series() -> None:
    """The type is asked of ``series``, so what it holds decides the layer."""
    fig, ax = plt.subplots()
    ax.step(X, X, where="post")
    ax.step(X, X * 2, where="post")

    assert len(_series(ax)) == 2
    (layer,) = _emitted(fig)
    assert layer["type"].value == "step"
