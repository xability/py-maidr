"""A Bokeh line or step labelled Recall against Precision is a PR curve.

The same claim the matplotlib and Plotly line paths read
(``maidr.util.named_pr_curve``): the axis labels, with every value a fraction
of one. Anything short of it keeps the line or step reading.
"""

from __future__ import annotations

import pytest

pytest.importorskip("bokeh")

from bokeh.plotting import figure  # noqa: E402

from maidr.bokeh.layers import PlotReader  # noqa: E402

RECALL = [0, 0.25, 0.5, 1]
PRECISION = [1, 0.9, 0.7, 0.4]


def types(p):
    return [layer.schema["type"].value for layer in PlotReader(p).layers()]


def test_lines_labelled_recall_and_precision_are_one_pr_curve():
    p = figure(x_axis_label="Recall", y_axis_label="Precision")
    p.line(RECALL, PRECISION, legend_label="logistic")
    p.line(RECALL, [0.8, 0.7, 0.6, 0.4], legend_label="tree")

    (layer,) = PlotReader(p).layers()

    assert layer.schema["type"].value == "pr_curve"
    assert [row[0]["z"] for row in layer.schema["data"]] == ["logistic", "tree"]


def test_a_step_labelled_so_is_one_too():
    p = figure(x_axis_label=" recall ", y_axis_label="PRECISION")
    p.step(RECALL, PRECISION, mode="after")

    assert types(p) == ["pr_curve"]


@pytest.mark.parametrize(
    "x_label, ys", [("Epoch", PRECISION), ("Recall", [1, 0.9, 0.7, 1.4])]
)
def test_anything_short_of_the_claim_keeps_its_reading(x_label, ys):
    p = figure(x_axis_label=x_label, y_axis_label="Precision")
    p.line(RECALL, ys)

    assert types(p) == ["line"]
