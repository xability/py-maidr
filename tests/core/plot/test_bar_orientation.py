"""Tests that bar and histogram layers support both orientations.

A horizontal bar layer reaches the renderer as ``{"x": value, "y": label}``
with ``orientation: "horz"``, the mirror of the vertical layout, so the
magnitude is read off the axis it actually grows along. Before this was
handled, ``Axes.barh`` and ``seaborn.barplot(orient="h")`` raised
``TypeError`` while extracting, and a horizontal histogram emitted bin edges
as counts.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


LABELS = ["a", "b", "c"]
VALUES = [1.0, 2.0, 3.0]
SAMPLES = [1, 2, 2, 3, 3, 3]


def _schema(fig) -> dict:
    """Return the first layer's schema with plain string keys."""
    plot = FigureManager.get_maidr(fig).plots[0]
    return {(k.value if hasattr(k, "value") else k): v for k, v in plot.schema.items()}


def test_vertical_bar_keeps_labels_on_x() -> None:
    fig, ax = plt.subplots()
    try:
        ax.bar(LABELS, VALUES)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert schema["orientation"] == "vert"
    assert schema["data"] == [
        {"x": "a", "y": 1.0},
        {"x": "b", "y": 2.0},
        {"x": "c", "y": 3.0},
    ]


def test_horizontal_bar_puts_the_value_on_x_and_the_label_on_y() -> None:
    fig, ax = plt.subplots()
    try:
        ax.barh(LABELS, VALUES)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert schema["orientation"] == "horz"
    assert schema["data"] == [
        {"x": 1.0, "y": "a"},
        {"x": 2.0, "y": "b"},
        {"x": 3.0, "y": "c"},
    ]


def test_seaborn_horizontal_barplot() -> None:
    fig, ax = plt.subplots()
    try:
        sns.barplot(x=VALUES, y=LABELS, orient="h", ax=ax)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert schema["orientation"] == "horz"
    assert schema["data"] == [
        {"x": 1.0, "y": "a"},
        {"x": 2.0, "y": "b"},
        {"x": 3.0, "y": "c"},
    ]


def test_seaborn_horizontal_countplot() -> None:
    """A count plot is registered as a bar layer, so it orients the same way."""
    fig, ax = plt.subplots()
    try:
        sns.countplot(y=["a", "b", "b", "c", "c", "c"], ax=ax)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert schema["orientation"] == "horz"
    assert schema["data"] == [
        {"x": 1.0, "y": "a"},
        {"x": 2.0, "y": "b"},
        {"x": 3.0, "y": "c"},
    ]


def test_vertical_histogram_bins_run_along_x() -> None:
    fig, ax = plt.subplots()
    try:
        ax.hist(SAMPLES, bins=3)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert schema["orientation"] == "vert"
    counts = [bin_["y"] for bin_ in schema["data"]]
    assert counts == [1.0, 2.0, 3.0]
    first = schema["data"][0]
    assert first["xMin"] == 1.0
    assert first["x"] == (first["xMin"] + first["xMax"]) / 2
    assert first["yMin"] == 0
    assert first["yMax"] == first["y"]


def test_horizontal_histogram_bins_run_along_y() -> None:
    fig, ax = plt.subplots()
    try:
        ax.hist(SAMPLES, bins=3, orientation="horizontal")
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert schema["orientation"] == "horz"
    # The counts are the same numbers as the vertical case, read off x.
    counts = [bin_["x"] for bin_ in schema["data"]]
    assert counts == [1.0, 2.0, 3.0]
    first = schema["data"][0]
    assert first["yMin"] == 1.0
    assert first["y"] == (first["yMin"] + first["yMax"]) / 2
    assert first["xMin"] == 0
    assert first["xMax"] == first["x"]


@pytest.mark.parametrize("horizontal", [False, True])
def test_a_label_count_mismatch_announces_positions(horizontal: bool) -> None:
    """Three bars against two tick labels: positions, not an error.

    This used to raise, and this test used to assert that it did. What it was
    really guarding is in its old name -- an `ExtractionError` **rather than a
    `TypeError`**: the magnitudes and the labels are zipped straight after the
    None check, so before that check was reordered this surfaced as
    `TypeError: 'NoneType' object is not iterable`.

    Failing cleanly was an improvement on failing messily. Not failing is an
    improvement on both: labels are one presentation of x, not x itself, and
    a bar drawn at x=0 with no tick beside it still has a position (#382).
    The guarantee the old test encoded survives -- no `TypeError`, and every
    bar gets exactly one label -- which is what is asserted here.

    Both orientations are driven because each zips its own way round.
    """
    fig, ax = plt.subplots()
    try:
        if horizontal:
            ax.barh(LABELS, VALUES)
            ax.set_yticks([0, 1])
            ax.set_yticklabels(LABELS[:2])
        else:
            ax.bar(LABELS, VALUES)
            ax.set_xticks([0, 1])
            ax.set_xticklabels(LABELS[:2])
        plot = FigureManager.get_maidr(fig).plots[0]

        data = plot._extract_plot_data()
    finally:
        plt.close(fig)

    assert len(data) == len(VALUES)
    label_key, value_key = ("y", "x") if horizontal else ("x", "y")
    assert [point[label_key] for point in data] == ["0", "1", "2"]
    assert [point[value_key] for point in data] == list(VALUES)


def test_an_axis_with_no_tick_labels_announces_positions() -> None:
    """A bar axis stripped of its ticks, which used to delete the chart.

    The guarantee this test has always encoded is that a bar never gets a
    **blank** label. The old `_extract_bar_container_data` swapped an empty
    level list for a list of empty strings, which reads as though it emitted
    one blank label per bar; it did not, because the substitution was local
    to that method while the caller zipped against the real, still-empty
    list -- and the whole figure raised instead.

    That guarantee is intact and the outcome is no longer an error: hiding
    tick marks is a styling choice, and it should not delete the chart.
    """
    fig, ax = plt.subplots()
    try:
        ax.bar(LABELS, VALUES)
        ax.set_xticks([])
        plot = FigureManager.get_maidr(fig).plots[0]

        data = plot._extract_plot_data()
    finally:
        plt.close(fig)

    assert [point["x"] for point in data] == ["0", "1", "2"]
    assert all(point["x"] for point in data), "no blank labels"


def test_seaborn_horizontal_histplot() -> None:
    """`sns.histplot(y=...)` reaches the same extractor as `hist()`.

    Seaborn asks for a horizontal histogram by binning `y` rather than by an
    `orientation` argument, so this is a distinct entry point into the code
    the matplotlib tests above cover.
    """
    fig, ax = plt.subplots()
    try:
        sns.histplot(y=SAMPLES, bins=3, ax=ax)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert schema["orientation"] == "horz"
    counts = [bin_["x"] for bin_ in schema["data"]]
    assert counts == [1.0, 2.0, 3.0]
    first = schema["data"][0]
    assert first["yMin"] == 1.0
    assert first["y"] == (first["yMin"] + first["yMax"]) / 2
    assert first["xMin"] == 0
    assert first["xMax"] == first["x"]
