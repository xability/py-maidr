"""A series carries the name its caller chose, and no other."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from maidr.core.enum import MaidrKey
from maidr.core.figure_manager import FigureManager
from maidr.util.artist_label import series_name


def _names(ax) -> list:
    """Return the ``z`` announced for the first point of every series."""
    figure = FigureManager.get_maidr(ax.get_figure())
    announced = []
    for plot in figure.plots:
        data = plot.schema.get(MaidrKey.DATA)
        if not isinstance(data, list) or not data:
            continue
        for series in data:
            first = series[0] if isinstance(series, list) else series
            announced.append(first.get(MaidrKey.Z))
    return announced


@pytest.mark.parametrize(
    "label",
    [
        "_nolegend_",
        "_child0",
        "_line5",
        "_",
    ],
)
def test_a_label_matplotlib_would_hide_is_not_a_name(label: str) -> None:
    """matplotlib's legend skips a leading underscore; so does the reading."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 9, 2], label=label)

    assert _names(ax) == [None]

    plt.close(fig)


def test_the_name_a_caller_chose_is_announced() -> None:
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 9, 2], label="revenue")

    assert _names(ax) == ["revenue"]

    plt.close(fig)


def test_an_unlabelled_line_is_announced_without_a_name() -> None:
    """The case that already worked, pinned so the rule cannot narrow to it."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 9, 2])

    assert _names(ax) == [None]

    plt.close(fig)


def test_a_named_series_beside_a_hidden_one_keeps_its_name() -> None:
    """Suppressing one series' name must not cost the other its own."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 9, 2], label="_nolegend_")
    ax.plot([1, 2, 3], [1, 2, 3], label="revenue")

    # A legend makes the legend labels the source of the names, so this is
    # the no-legend path: each line answers for itself.
    assert _names(ax) == [None, "revenue"]

    plt.close(fig)


def test_series_name_answers_for_anything_without_a_label() -> None:
    """The helper is handed matplotlib artists, but must not assume one."""
    assert series_name(object()) == ""


def test_series_name_answers_for_a_label_that_is_not_a_string() -> None:
    class Odd:
        def get_label(self):
            return 42

    assert series_name(Odd()) == ""
