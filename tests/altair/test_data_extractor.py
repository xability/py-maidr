"""Tests for Altair data extraction."""

import numpy as np
import pandas as pd
import pytest

altair = pytest.importorskip("altair")
import altair as alt  # noqa: E402

from maidr.altair.data_extractor import extract_chart_data  # noqa: E402
from maidr.core.enum import PlotType  # noqa: E402


class TestBarDataExtraction:
    def test_simple_bar(self):
        df = pd.DataFrame({"x": ["A", "B", "C"], "y": [10, 20, 30]})
        chart = alt.Chart(df).mark_bar().encode(x="x:N", y="y:Q")
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.BAR.value
        assert len(result["data"]) == 3
        assert result["data"][0]["x"] == "A"
        assert result["data"][0]["y"] == 10

    def test_count_bar(self):
        df = pd.DataFrame({"category": ["A", "A", "B", "B", "B"]})
        chart = alt.Chart(df).mark_bar().encode(x="category:N", y="count():Q")
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.BAR.value
        assert len(result["data"]) == 2


class TestScatterDataExtraction:
    def test_simple_scatter(self):
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0]})
        chart = alt.Chart(df).mark_point().encode(x="x:Q", y="y:Q")
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.SCATTER.value
        assert len(result["data"]) == 3
        assert result["data"][0]["x"] == 1.0
        assert result["data"][0]["y"] == 4.0


class TestLineDataExtraction:
    def test_single_line(self):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]})
        chart = alt.Chart(df).mark_line().encode(x="x:Q", y="y:Q")
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.LINE.value
        assert len(result["data"]) == 1  # one line
        assert len(result["data"][0]) == 3  # three points

    def test_multiline(self):
        df = pd.DataFrame(
            {
                "x": [1, 2, 3, 1, 2, 3],
                "y": [10, 20, 30, 5, 15, 25],
                "series": ["A", "A", "A", "B", "B", "B"],
            }
        )
        chart = alt.Chart(df).mark_line().encode(x="x:Q", y="y:Q", color="series:N")
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.LINE.value
        assert len(result["data"]) == 2  # two lines
        assert result["data"][0][0]["z"] == "A"
        assert result["data"][1][0]["z"] == "B"


class TestHeatmapDataExtraction:
    def test_heatmap(self):
        df = pd.DataFrame(
            {
                "x": ["A", "A", "B", "B"],
                "y": ["R1", "R2", "R1", "R2"],
                "value": [1.0, 2.0, 3.0, 4.0],
            }
        )
        chart = alt.Chart(df).mark_rect().encode(x="x:N", y="y:N", color="value:Q")
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.HEAT.value
        assert "points" in result["data"]
        assert "x" in result["data"]
        assert "y" in result["data"]
        assert len(result["data"]["x"]) == 2
        assert len(result["data"]["y"]) == 2


class TestHistogramDataExtraction:
    def test_histogram(self):
        np.random.seed(42)
        df = pd.DataFrame({"value": np.random.normal(0, 1, 100)})
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X("value:Q", bin=alt.Bin(maxbins=10)),
                y="count():Q",
            )
        )
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.HIST.value
        assert len(result["data"]) > 0
        assert "xMin" in result["data"][0]
        assert "xMax" in result["data"][0]
        assert "x" in result["data"][0]
        assert "y" in result["data"][0]


class TestBoxPlotDataExtraction:
    def test_boxplot(self):
        df = pd.DataFrame(
            {
                "species": ["A"] * 50 + ["B"] * 50,
                "value": list(np.random.normal(10, 2, 50))
                + list(np.random.normal(20, 3, 50)),
            }
        )
        chart = alt.Chart(df).mark_boxplot().encode(x="species:N", y="value:Q")
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.BOX.value
        assert result["orientation"] == "vert"
        assert len(result["data"]) == 2
        for box in result["data"]:
            assert "min" in box
            assert "q1" in box
            assert "q2" in box
            assert "q3" in box
            assert "max" in box
            assert "lowerOutliers" in box
            assert "upperOutliers" in box


class TestStackedBarDataExtraction:
    def test_stacked_bar(self):
        df = pd.DataFrame(
            {
                "category": ["A", "A", "B", "B"],
                "group": ["G1", "G2", "G1", "G2"],
                "value": [10, 20, 30, 40],
            }
        )
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x="category:N",
                y=alt.Y("value:Q", stack="zero"),
                color="group:N",
            )
        )
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.STACKED.value
        assert len(result["data"]) == 2  # two groups


class TestDodgedBarDataExtraction:
    def test_dodged_bar(self):
        df = pd.DataFrame(
            {
                "category": ["A", "A", "B", "B"],
                "group": ["G1", "G2", "G1", "G2"],
                "value": [10, 20, 30, 40],
            }
        )
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x="category:N",
                y="value:Q",
                color="group:N",
                xOffset="group:N",
            )
        )
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.DODGED.value
        assert len(result["data"]) == 2  # two groups


class TestSmoothDataExtraction:
    def test_density_transform(self):
        np.random.seed(0)
        df = pd.DataFrame({"value": np.random.normal(0, 1, 100)})
        chart = (
            alt.Chart(df)
            .transform_density("value", as_=["value", "density"])
            .mark_line()
            .encode(x="value:Q", y="density:Q")
        )
        spec = chart.to_dict()

        result = extract_chart_data(spec)

        assert result["type"] == PlotType.SMOOTH.value
        assert len(result["data"]) == 1  # one smooth line
        assert len(result["data"][0]) > 0  # has points
