"""A plotly line or area titled Recall against Precision is a precision-recall curve.

The same claim the matplotlib line path reads (``maidr.util.named_pr_curve``):
the axis titles, with every value a fraction of one. plotly's own
documentation draws a PR curve as ``px.area(x=recall, y=precision)``.
"""

from __future__ import annotations

import pytest

go = pytest.importorskip("plotly.graph_objects")
px = pytest.importorskip("plotly.express")

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402


def types(fig):
    return [plot.render()["type"].value for plot in PlotlyMaidr(fig)._plots]


def test_lines_titled_recall_and_precision_are_a_pr_curve():
    fig = go.Figure(
        [
            go.Scatter(x=[0, 0.5, 1], y=[1, 0.8, 0.4], mode="lines", name="a"),
            go.Scatter(x=[0, 0.5, 1], y=[1, 0.6, 0.4], mode="lines", name="b"),
        ]
    )
    fig.update_layout(xaxis_title="Recall", yaxis_title="Precision")

    assert types(fig) == ["pr_curve"]


def test_the_area_plotly_documents_is_one_too():
    fig = px.area(
        x=[0, 0.5, 1], y=[1, 0.8, 0.4], labels={"x": "Recall", "y": "Precision"}
    )

    assert types(fig) == ["pr_curve"]


@pytest.mark.parametrize(
    "x_title, ys", [("Epoch", [1, 0.8, 0.4]), ("Recall", [1, 0.8, 1.4])]
)
def test_anything_short_of_the_claim_keeps_its_reading(x_title, ys):
    fig = go.Figure([go.Scatter(x=[0, 0.5, 1], y=ys, mode="lines")])
    fig.update_layout(xaxis_title=x_title, yaxis_title="Precision")

    assert types(fig) == ["line"]
