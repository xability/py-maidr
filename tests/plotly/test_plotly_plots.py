from __future__ import annotations

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.bar import PlotlyBarPlot
from maidr.plotly.scatter import PlotlyScatterPlot
from maidr.plotly.line import PlotlyLinePlot
from maidr.plotly.box import PlotlyBoxPlot
from maidr.plotly.heatmap import PlotlyHeatmapPlot
from maidr.plotly.histogram import PlotlyHistogramPlot
from maidr.plotly.grouped_bar import PlotlyGroupedBarPlot
from maidr.plotly.candlestick import PlotlyCandlestickPlot
from maidr.plotly.multiline import PlotlyMultiLinePlot


class TestPlotlyBarPlot:
    def test_extract_data(self):
        trace = {"type": "bar", "x": ["A", "B", "C"], "y": [10, 20, 30]}
        layout = {"title": "Bar", "xaxis": {"title": "Cat"}, "yaxis": {"title": "Val"}}
        plot = PlotlyBarPlot(trace, layout)
        data = plot._extract_plot_data()

        assert len(data) == 3
        assert data[0] == {MaidrKey.X: "A", MaidrKey.Y: 10}
        assert data[2] == {MaidrKey.X: "C", MaidrKey.Y: 30}

    def test_schema_has_required_keys(self):
        trace = {"type": "bar", "x": ["A"], "y": [1]}
        layout = {"title": "Test"}
        plot = PlotlyBarPlot(trace, layout)
        schema = plot.schema

        assert MaidrKey.ID in schema
        assert MaidrKey.TYPE in schema
        assert MaidrKey.TITLE in schema
        assert MaidrKey.AXES in schema
        assert MaidrKey.DATA in schema

    def test_horizontal_bar(self):
        trace = {
            "type": "bar",
            "x": [10, 20],
            "y": ["A", "B"],
            "orientation": "h",
        }
        plot = PlotlyBarPlot(trace, {})
        data = plot._extract_plot_data()

        assert data[0][MaidrKey.X] == 10
        assert data[0][MaidrKey.Y] == "A"


class TestPlotlyScatterPlot:
    def test_extract_data(self):
        trace = {"type": "scatter", "x": [1.0, 2.0], "y": [3.0, 4.0]}
        plot = PlotlyScatterPlot(trace, {})
        data = plot._extract_plot_data()

        assert len(data) == 2
        assert data[0] == {MaidrKey.X: 1.0, MaidrKey.Y: 3.0}

    def test_numpy_scalars_converted(self):
        trace = {
            "type": "scatter",
            "x": [np.float64(1.5)],
            "y": [np.int64(2)],
        }
        plot = PlotlyScatterPlot(trace, {})
        data = plot._extract_plot_data()

        assert isinstance(data[0][MaidrKey.X], float)
        assert isinstance(data[0][MaidrKey.Y], int)


class TestPlotlyLinePlot:
    def test_extract_data(self):
        trace = {
            "type": "scatter",
            "mode": "lines",
            "x": [1, 2, 3],
            "y": [10, 20, 15],
            "name": "Series A",
        }
        plot = PlotlyLinePlot(trace, {})
        data = plot._extract_plot_data()

        # Line data is wrapped in an outer list
        assert len(data) == 1
        assert len(data[0]) == 3
        assert data[0][0][MaidrKey.X] == 1
        assert data[0][0][MaidrKey.Y] == 10
        assert data[0][0][MaidrKey.FILL] == "Series A"

    def test_no_name_omits_fill(self):
        trace = {"type": "scatter", "mode": "lines", "x": [1], "y": [2]}
        plot = PlotlyLinePlot(trace, {})
        data = plot._extract_plot_data()

        assert MaidrKey.FILL not in data[0][0]


class TestPlotlyBoxPlot:
    def test_extract_from_raw_data(self):
        np.random.seed(0)
        values = np.random.randn(100).tolist()
        trace = {"type": "box", "y": values, "name": "G1"}
        plot = PlotlyBoxPlot(trace, {})
        data = plot._extract_plot_data()

        assert len(data) == 1
        box = data[0]
        assert "q1" in box
        assert "q2" in box
        assert "q3" in box
        assert "min" in box
        assert "max" in box
        assert box["q1"] <= box["q2"] <= box["q3"]

    def test_extract_precomputed(self):
        trace = {
            "type": "box",
            "q1": [25],
            "median": [50],
            "q3": [75],
            "lowerfence": [5],
            "upperfence": [95],
        }
        plot = PlotlyBoxPlot(trace, {})
        data = plot._extract_plot_data()

        assert len(data) == 1
        assert data[0]["q1"] == 25
        assert data[0]["q2"] == 50
        assert data[0]["max"] == 95

    def test_grouped_box(self):
        trace = {
            "type": "box",
            "x": ["A", "A", "A", "B", "B", "B"],
            "y": [1, 2, 3, 4, 5, 6],
        }
        plot = PlotlyBoxPlot(trace, {})
        data = plot._extract_plot_data()

        assert len(data) == 2
        assert data[0]["fill"] == "A"
        assert data[1]["fill"] == "B"


class TestPlotlyHeatmapPlot:
    def test_extract_data(self):
        trace = {
            "type": "heatmap",
            "z": [[1, 2, 3], [4, 5, 6]],
            "x": ["a", "b", "c"],
            "y": ["r1", "r2"],
        }
        plot = PlotlyHeatmapPlot(trace, {})
        data = plot._extract_plot_data()

        assert MaidrKey.POINTS in data
        assert data[MaidrKey.POINTS] == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
        assert data[MaidrKey.X] == ["a", "b", "c"]
        assert data[MaidrKey.Y] == ["r1", "r2"]

    def test_no_labels(self):
        trace = {"type": "heatmap", "z": [[1, 2], [3, 4]]}
        plot = PlotlyHeatmapPlot(trace, {})
        data = plot._extract_plot_data()

        assert MaidrKey.POINTS in data
        assert MaidrKey.X not in data
        assert MaidrKey.Y not in data


class TestPlotlyHistogramPlot:
    def test_extract_data(self):
        np.random.seed(42)
        values = np.random.randn(100).tolist()
        trace = {"type": "histogram", "x": values}
        plot = PlotlyHistogramPlot(trace, {})
        data = plot._extract_plot_data()

        assert len(data) > 0
        for bin_data in data:
            assert "x" in bin_data
            assert "y" in bin_data
            assert "xMin" in bin_data
            assert "xMax" in bin_data
            assert bin_data["xMin"] <= bin_data["x"] <= bin_data["xMax"]

    def test_empty_data(self):
        trace = {"type": "histogram"}
        plot = PlotlyHistogramPlot(trace, {})
        data = plot._extract_plot_data()

        assert data == []

    def test_nbinsx(self):
        trace = {"type": "histogram", "x": list(range(100)), "nbinsx": 5}
        plot = PlotlyHistogramPlot(trace, {})
        data = plot._extract_plot_data()

        assert len(data) == 5


class TestPlotlyGroupedBarPlot:
    def test_dodged_bar_data(self):
        traces = [
            {"type": "bar", "x": ["A", "B"], "y": [10, 20], "name": "G1"},
            {"type": "bar", "x": ["A", "B"], "y": [15, 25], "name": "G2"},
        ]
        layout = {"barmode": "group"}
        plot = PlotlyGroupedBarPlot(traces, layout, PlotType.DODGED)
        data = plot._extract_plot_data()

        assert len(data) == 2
        assert len(data[0]) == 2
        assert data[0][0] == {"x": "A", "fill": "G1", "y": 10}
        assert data[1][1] == {"x": "B", "fill": "G2", "y": 25}

    def test_stacked_bar_data(self):
        traces = [
            {"type": "bar", "x": ["X", "Y"], "y": [5, 10], "name": "S1"},
            {"type": "bar", "x": ["X", "Y"], "y": [3, 7], "name": "S2"},
        ]
        layout = {"barmode": "stack"}
        plot = PlotlyGroupedBarPlot(traces, layout, PlotType.STACKED)
        data = plot._extract_plot_data()

        assert len(data) == 2
        assert plot.type == PlotType.STACKED

    def test_schema_type(self):
        traces = [
            {"type": "bar", "x": ["A"], "y": [1], "name": "G1"},
            {"type": "bar", "x": ["A"], "y": [2], "name": "G2"},
        ]
        plot = PlotlyGroupedBarPlot(traces, {}, PlotType.DODGED)
        assert plot.schema[MaidrKey.TYPE] == PlotType.DODGED


class TestPlotlyCandlestickPlot:
    def test_extract_data(self):
        trace = {
            "type": "candlestick",
            "x": ["2024-01-02", "2024-01-03"],
            "open": [150.0, 152.5],
            "high": [155.0, 156.0],
            "low": [148.0, 149.0],
            "close": [152.5, 148.0],
        }
        plot = PlotlyCandlestickPlot(trace, {})
        data = plot._extract_plot_data()

        assert len(data) == 2
        assert data[0]["value"] == "2024-01-02"
        assert data[0]["open"] == 150.0
        assert data[0]["high"] == 155.0
        assert data[0]["low"] == 148.0
        assert data[0]["close"] == 152.5

    def test_schema_title_default(self):
        trace = {
            "type": "candlestick",
            "x": ["2024-01-02"],
            "open": [100],
            "high": [110],
            "low": [90],
            "close": [105],
        }
        plot = PlotlyCandlestickPlot(trace, {})
        schema = plot.schema

        assert schema[MaidrKey.TITLE] == "Candlestick Chart"
        assert schema[MaidrKey.TYPE] == PlotType.CANDLESTICK

    def test_axes_defaults(self):
        trace = {
            "type": "candlestick",
            "x": ["2024-01-02"],
            "open": [100],
            "high": [110],
            "low": [90],
            "close": [105],
        }
        plot = PlotlyCandlestickPlot(trace, {})
        schema = plot.schema

        assert schema[MaidrKey.AXES][MaidrKey.X] == "Date"
        assert schema[MaidrKey.AXES][MaidrKey.Y] == "Price"


class TestPlotlyMultiLinePlot:
    def test_merges_traces_into_list_of_lists(self):
        traces = [
            {"type": "scatter", "mode": "lines", "x": [1, 2], "y": [10, 20], "name": "A"},
            {"type": "scatter", "mode": "lines", "x": [1, 2], "y": [5, 15], "name": "B"},
        ]
        plot = PlotlyMultiLinePlot(traces, {})
        data = plot._extract_plot_data()

        assert len(data) == 2
        assert len(data[0]) == 2
        assert data[0][0][MaidrKey.X] == 1
        assert data[0][0][MaidrKey.FILL] == "A"
        assert data[1][0][MaidrKey.FILL] == "B"

    def test_single_layer_schema(self):
        traces = [
            {"type": "scatter", "mode": "lines", "x": [1], "y": [2], "name": "L1"},
            {"type": "scatter", "mode": "lines", "x": [1], "y": [3], "name": "L2"},
        ]
        plot = PlotlyMultiLinePlot(traces, {})
        schema = plot.schema

        assert schema[MaidrKey.TYPE] == PlotType.LINE
        assert len(schema[MaidrKey.DATA]) == 2
