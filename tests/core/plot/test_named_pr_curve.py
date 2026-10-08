"""A line titled Recall against Precision is read as a precision-recall curve.

A PR curve drawn by hand -- ``ax.plot(recall, precision)``, or the
``ax.step(..., where="post")`` scikit-learn's examples drew before
``PrecisionRecallDisplay`` -- carries no evidence of what it is except its
axis titles. Titled exactly so, with every value a fraction of one, the
layer is a ``pr_curve``. Anything short of that keeps the reading it had.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from maidr.core.enum import MaidrKey
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def emitted(fig):
    return [plot.schema for plot in FigureManager.get_maidr(fig).plots]


def titled(ax, x="Recall", y="Precision"):
    ax.set_xlabel(x)
    ax.set_ylabel(y)


def test_a_line_titled_recall_and_precision_is_a_pr_curve():
    fig, ax = plt.subplots()
    ax.plot([0, 0.5, 1], [1, 0.8, 0.4], label="model")
    titled(ax)

    (schema,) = emitted(fig)
    assert schema[MaidrKey.TYPE] == "pr_curve"
    assert [(p["x"], p["y"]) for p in schema[MaidrKey.DATA][0]] == [
        (0, 1),
        (0.5, 0.8),
        (1, 0.4),
    ]
    assert len(schema[MaidrKey.SELECTOR]) == 1


def test_a_step_titled_so_is_one_too_without_a_step_direction():
    fig, ax = plt.subplots()
    ax.step([0, 0.5, 1], [1, 0.8, 0.4], where="post")
    titled(ax)

    (schema,) = emitted(fig)
    assert schema[MaidrKey.TYPE] == "pr_curve"
    assert MaidrKey.STEP_DIRECTION not in schema


def test_several_curves_keep_their_names():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 0.5], label="a")
    ax.plot([0, 1], [1, 0.3], label="b")
    titled(ax, " recall ", "PRECISION")
    ax.legend()

    (schema,) = emitted(fig)
    assert schema[MaidrKey.TYPE] == "pr_curve"
    assert [s[0]["z"] for s in schema[MaidrKey.DATA]] == ["a", "b"]


@pytest.mark.parametrize(
    "x_title, y_title, ys",
    [
        ("Epoch", "Precision", [0.4, 0.6, 0.8]),
        ("Recall", "Accuracy", [0.4, 0.6, 0.8]),
        ("Precision", "Recall", [0.4, 0.6, 0.8]),
        ("Recall", "Precision", [1.0, 0.8, 1.4]),
        ("Recall (positive label: 1)", "Precision", [1.0, 0.8, 0.4]),
    ],
)
def test_anything_short_of_the_claim_keeps_the_line_reading(x_title, y_title, ys):
    fig, ax = plt.subplots()
    ax.plot([0, 0.5, 1], ys)
    titled(ax, x_title, y_title)

    (schema,) = emitted(fig)
    assert schema[MaidrKey.TYPE] == "line"


def test_a_step_short_of_the_claim_keeps_its_step_direction():
    fig, ax = plt.subplots()
    ax.step([0, 0.5, 1], [1, 0.8, 0.4], where="post")
    titled(ax, "Recall", "Count")

    (schema,) = emitted(fig)
    assert schema[MaidrKey.TYPE] == "step"
    assert schema[MaidrKey.STEP_DIRECTION] == "hv"
