"""
A violin plot's two layers must call the same violin by the same name (#469).

``ax.violinplot()`` emits a ``violin_box`` layer and a ``violin_kde`` layer.
The box layer refuses tick labels unless there is exactly one per violin, so a
bare call -- whose category axis is still numeric -- keeps ``Group 1/2/3``.
The KDE layer had no such test and took whatever the axis offered, so it named
three violins after the first three of seven numeric ticks: the violin drawn at
x = 2 was called ``"1.5"``.

A reader moving between the two layers of one chart was told they were on two
different things, and one of the names was not even the position the violin
sits at. ``sns.violinplot()`` was unaffected -- its axis carries one tick per
violin with the real names -- which is why the categorical path, where labels
matter most, is the one that always worked.

These assert on the emitted schema rather than on internals, because the
contract is what the two layers publish about the same chart.
"""

from __future__ import annotations

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402,F401
from maidr.core.figure_manager import FigureManager  # noqa: E402

SAMPLES = [
    [1, 2, 2, 3, 3, 3, 4, 4, 5],
    [2, 3, 3, 4, 4, 4, 5, 5, 6],
    [3, 4, 4, 5, 5, 5, 6, 6, 7],
]
NAMES = ["apple", "banana", "cherry"]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _layers(fig) -> dict[str, list]:
    """Map each layer type of the figure to its emitted data."""
    schema = FigureManager.figs[fig]._flatten_maidr()
    return {
        layer["type"]: layer.get("data") or []
        for layer in schema["subplots"][0][0]["layers"]
    }


def _box_names(fig) -> list[str]:
    """What the box layer calls each violin."""
    return [point["z"] for point in _layers(fig)["violin_box"]]


def _kde_names(fig) -> list[str]:
    """What the KDE layer calls each violin, one per series."""
    return [series[0]["x"] for series in _layers(fig)["violin_kde"]]


def _bare(vert: bool = True):
    fig, ax = plt.subplots()
    ax.violinplot(SAMPLES, vert=vert)
    return fig


def _labelled(vert: bool = True):
    fig, ax = plt.subplots()
    ax.violinplot(SAMPLES, vert=vert)
    if vert:
        ax.set_xticks([1, 2, 3])
        ax.set_xticklabels(NAMES)
    else:
        ax.set_yticks([1, 2, 3])
        ax.set_yticklabels(NAMES)
    return fig


class TestTheTwoLayersAgree:
    @pytest.mark.parametrize("vert", [True, False], ids=["vertical", "horizontal"])
    def test_on_a_chart_whose_violins_were_never_named(self, vert) -> None:
        fig = _bare(vert=vert)

        assert _kde_names(fig) == _box_names(fig)

    @pytest.mark.parametrize("vert", [True, False], ids=["vertical", "horizontal"])
    def test_on_a_chart_labelled_after_the_call(self, vert) -> None:
        # The case the render-time lookup exists for: `set_xticklabels()` runs
        # after `violinplot()`, so the names are not available at patch time.
        fig = _labelled(vert=vert)

        assert _kde_names(fig) == _box_names(fig)
        # Set rather than sequence: a horizontal violin plot is emitted
        # top-to-bottom by both layers, so the order is reversed there. Which
        # end a horizontal chart should be read from is a separate question
        # and not one this fix touches -- what matters here is that the two
        # layers name the same violins, and that the names are the caller's.
        assert set(_kde_names(fig)) == set(NAMES)


class TestTheNamesThemselves:
    def test_an_unnamed_violin_is_not_named_after_an_axis_tick(self) -> None:
        # The defect, stated as what the reader was told. A bare violinplot
        # leaves seven ticks at half-units across three violins, and the first
        # three were handed out as names -- so the violin at x = 2 answered to
        # "1.5", a number belonging to neither its position nor its data.
        names = _kde_names(_bare())

        assert not any(_looks_numeric(name) for name in names), names

    def test_an_unnamed_violin_gets_the_box_layer_s_generic_name(self) -> None:
        assert _kde_names(_bare()) == ["Group 1", "Group 2", "Group 3"]

    def test_a_real_category_still_reaches_the_kde_layer(self) -> None:
        # The guard must not throw away labels that are genuine: a categorical
        # axis has one tick per violin and has to pass.
        assert _kde_names(_labelled()) == NAMES

    def test_every_violin_gets_its_own_name(self) -> None:
        # An off-by-one in the index pairing is what made "1.5" name the
        # second violin, so the names have to be distinct and as many as the
        # violins rather than merely non-numeric.
        names = _kde_names(_bare())

        assert len(names) == len(SAMPLES)
        assert len(set(names)) == len(SAMPLES)


def _looks_numeric(value: object) -> bool:
    """Whether a label is a bare number wearing a category's clothes."""
    try:
        float(str(value))
    except ValueError:
        return False
    return True
