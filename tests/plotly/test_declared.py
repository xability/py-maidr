"""A plotly trace's ``meta.maidr`` block declares a PR curve or a fan chart.

The same blocks maidr.js's own Plotly adapter reads, with the same keys and
rules, so a figure declared once reads the same through py-maidr.
"""

from __future__ import annotations

import pytest

go = pytest.importorskip("plotly.graph_objects")

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

X = [0, 1, 2, 3]
MEDIAN = [5.0, 6.0, 7.0, 8.0]


def layers(fig):
    return [plot.render() for plot in PlotlyMaidr(fig)._plots]


def edge(offset, name, fill=None):
    return go.Scatter(
        x=X,
        y=[m + offset for m in MEDIAN],
        name=name,
        mode="lines",
        line_width=0,
        fill=fill,
    )


def fan(bands, median_meta=True):
    meta = {"maidr": {"type": "percentile_band", "bands": bands}}
    return go.Figure(
        [
            edge(-2, "p5"),
            edge(2, "p5-95", "tonexty"),
            edge(-1, "p25"),
            edge(1, "p25-75", "tonexty"),
            go.Scatter(
                x=X,
                y=MEDIAN,
                name="median",
                mode="lines",
                meta=meta if median_meta else None,
            ),
        ]
    )


NESTED = [
    {"series": "p25-75", "lower": 0.25, "upper": 0.75},
    {"series": "p5-95", "lower": 0.05, "upper": 0.95},
]


def test_a_declared_fan_is_one_percentile_band():
    (layer,) = layers(fan(NESTED))

    assert layer["type"] == "percentile_band"
    assert layer["title"] == "median"
    assert layer["data"][1] == {
        "x": 1,
        "quantiles": [
            {"level": 0.05, "value": 4.0},
            {"level": 0.25, "value": 5.0},
            {"level": 0.5, "value": 6.0},
            {"level": 0.75, "value": 7.0},
            {"level": 0.95, "value": 8.0},
        ],
    }
    # Each band's fill, outermost first, is drawn in the group of the trace
    # it fills to; then the median's line.
    assert layer["selectors"] == [
        ".subplot.xy .scatterlayer > .trace.scatter:nth-child(1) path.js-fill",
        ".subplot.xy .scatterlayer > .trace.scatter:nth-child(3) path.js-fill",
        ".subplot.xy .scatterlayer > .trace.scatter:nth-child(5) path.js-line",
    ]


def test_a_band_named_by_uid_and_drawn_high_edge_first():
    fig = go.Figure(
        [
            edge(2, "upper"),
            go.Scatter(
                x=X,
                y=[m - 2 for m in MEDIAN],
                uid="band90",
                mode="lines",
                fill="tonexty",
            ),
            go.Scatter(
                x=X,
                y=MEDIAN,
                mode="lines",
                meta={
                    "maidr": {
                        "type": "percentile_band",
                        "title": "Forecast",
                        "bands": [{"series": "band90", "lower": 0.05, "upper": 0.95}],
                    }
                },
            ),
        ]
    )

    (layer,) = layers(fig)

    assert layer["title"] == "Forecast"
    assert layer["data"][0]["quantiles"] == [
        {"level": 0.05, "value": 3.0},
        {"level": 0.5, "value": 5.0},
        {"level": 0.95, "value": 7.0},
    ]


def test_without_a_declaration_the_fan_stays_lines():
    assert [layer["type"] for layer in layers(fan(NESTED, median_meta=False))] == [
        "line"
    ]


def test_bands_that_do_not_nest_are_the_undeclared_chart():
    crossing = [
        {"series": "p25-75", "lower": 0.25, "upper": 0.95},
        {"series": "p5-95", "lower": 0.05, "upper": 0.75},
    ]
    with pytest.warns(UserWarning, match="do not nest"):
        assert [layer["type"] for layer in layers(fan(crossing))] == ["line"]


def test_a_band_not_filled_to_another_trace_is_left_out():
    bands = [*NESTED[:1], {"series": "p5", "lower": 0.05, "upper": 0.95}]
    with pytest.warns(UserWarning, match="tonexty"):
        found = layers(fan(bands))

    band = next(layer for layer in found if layer["type"] == "percentile_band")
    assert [q["level"] for q in band["data"][0]["quantiles"]] == [0.25, 0.5, 0.75]
    assert len(band["selectors"]) == 2


RECALL = [0, 0.25, 0.5, 1]
PRECISION = [1, 0.9, 0.7, 0.4]


def test_a_declared_pr_curve_takes_the_other_lines_as_curves():
    fig = go.Figure(
        [
            go.Scatter(
                x=RECALL,
                y=PRECISION,
                name="logistic",
                mode="lines",
                customdata=[{"cut": t} for t in (0.9, 0.6, 0.4, 0.1)],
                meta={
                    "maidr": {
                        "type": "pr_curve",
                        "threshold": "cut",
                        "prevalence": 0.3,
                        "ap": 0.81,
                    }
                },
            ),
            go.Scatter(x=RECALL, y=[0.8, 0.7, 0.6, 0.4], name="tree", mode="lines"),
        ]
    )

    (layer,) = layers(fig)

    assert layer["type"] == "pr_curve"
    first, second = layer["data"]
    assert first[0] == {
        "x": 0.0,
        "y": 1.0,
        "z": "logistic",
        "threshold": 0.9,
        "prevalence": 0.3,
        "ap": 0.81,
    }
    # A curve merged in borrows nothing from the block.
    assert second[0] == {"x": 0.0, "y": 0.8, "z": "tree"}
    assert len(layer["selectors"]) == 2


def test_merge_false_takes_only_the_declaring_curves():
    fig = go.Figure(
        [
            go.Scatter(
                x=RECALL,
                y=PRECISION,
                mode="lines",
                meta={"maidr": {"type": "pr_curve", "merge": False}},
            ),
            go.Scatter(x=RECALL, y=[0.5, 0.5, 0.5, 0.5], mode="lines"),
        ]
    )

    assert [layer["type"] for layer in layers(fig)] == ["pr_curve", "line"]


def test_a_percentage_prevalence_is_refused():
    fig = go.Figure(
        go.Scatter(
            x=RECALL,
            y=PRECISION,
            mode="lines",
            meta={"maidr": {"type": "pr_curve", "prevalence": 30}},
        )
    )

    with pytest.warns(UserWarning, match="prevalence"):
        (layer,) = layers(fig)

    assert layer["type"] == "pr_curve"
    assert "prevalence" not in layer["data"][0][0]


def test_a_meta_that_is_not_a_declaration_changes_nothing():
    fig = go.Figure(
        go.Scatter(x=RECALL, y=PRECISION, mode="lines", meta="a plain string")
    )

    assert [layer["type"] for layer in layers(fig)] == ["line"]
