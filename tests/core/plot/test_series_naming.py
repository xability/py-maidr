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


def test_a_hidden_series_does_not_take_its_neighbours_legend_name() -> None:
    """matplotlib's legend skips an underscored label, so the legend is
    shorter than the series list and pairing the two by position handed the
    hidden line the name of the series after it."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 9, 2], label="_nolegend_")
    ax.plot([1, 2, 3], [1, 2, 3], label="revenue")
    ax.legend()

    assert _names(ax) == [None, "revenue"]

    plt.close(fig)


def test_the_hidden_series_may_come_second_too() -> None:
    """The other order, because only one direction can be broken."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3], label="revenue")
    ax.plot([1, 2, 3], [4, 9, 2], label="_nolegend_")
    ax.legend()

    assert _names(ax) == ["revenue", None]

    plt.close(fig)


def test_two_hidden_series_around_a_named_one() -> None:
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 9, 2], label="_nolegend_")
    ax.plot([1, 2, 3], [1, 2, 3], label="revenue")
    ax.plot([1, 2, 3], [3, 1, 2], label="_child9")
    ax.legend()

    assert _names(ax) == [None, "revenue", None]

    plt.close(fig)


def test_a_legend_that_renames_every_series_still_wins() -> None:
    """`ax.legend(["A", "B"])` renames positionally and means to; the fix
    must not take that away."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 9, 2], label="p")
    ax.plot([1, 2, 3], [1, 2, 3], label="q")
    ax.legend(["A", "B"])

    assert _names(ax) == ["A", "B"]

    plt.close(fig)


def test_a_hue_split_is_still_named_from_its_legend() -> None:
    """seaborn labels its lines with `_child` sentinels and puts the group
    names in the legend, which is the case #502 settled. It also leaves
    lines with no data among the real ones, so the pairing has to run over
    the series that are actually announced."""
    import pandas as pd
    import seaborn as sns

    frame = pd.DataFrame(
        {
            "x": [1, 2, 3, 1, 2, 3],
            "y": [1, 2, 3, 3, 2, 1],
            "g": ["a", "a", "a", "b", "b", "b"],
        }
    )
    fig, ax = plt.subplots()
    sns.lineplot(frame, x="x", y="y", hue="g", ax=ax)

    assert _names(ax) == ["a", "b"]

    plt.close(fig)


def test_a_legend_shorter_than_the_series_still_renames_the_one_it_names() -> None:
    """The case that makes the shorter-legend pairing load-bearing rather
    than a longer way of falling back to the line's own label.

    `ax.legend(["Renamed"])` beside a hidden line produces one entry, and it
    belongs to the visible series -- which must then be announced as
    "Renamed" and not as its own "revenue".
    """
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [4, 9, 2], label="_nolegend_")
    ax.plot([1, 2, 3], [1, 2, 3], label="revenue")
    ax.legend(["Renamed"])

    assert _names(ax) == [None, "Renamed"]

    plt.close(fig)


def test_a_legend_given_an_explicit_order_still_names_each_line_itself() -> None:
    """`ax.legend(handles=[...])` reorders a legend without redrawing, and
    pairing by position then announced each series under the other's name
    (#578). The legend's handles are proxy artists, so the pairing is
    recovered from the text instead."""
    fig, ax = plt.subplots()
    (first,) = ax.plot([1, 2, 3], [1, 2, 3], label="p")
    (second,) = ax.plot([1, 2, 3], [3, 2, 1], label="q")
    ax.legend(handles=[second, first])

    assert [text.get_text() for text in ax.legend_.get_texts()] == ["q", "p"]
    assert _names(ax) == ["p", "q"]

    plt.close(fig)


def test_an_ordinary_legend_is_unaffected_by_that() -> None:
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3], label="p")
    ax.plot([1, 2, 3], [3, 2, 1], label="q")
    ax.legend()

    assert _names(ax) == ["p", "q"]

    plt.close(fig)


def test_two_series_sharing_a_name_keep_the_positional_pairing() -> None:
    """Matching by name needs the names to identify a line; two lines called
    the same thing cannot be told apart that way, so position stands."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3], label="same")
    ax.plot([1, 2, 3], [3, 2, 1], label="same")
    ax.legend()

    assert _names(ax) == ["same", "same"]

    plt.close(fig)
