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
