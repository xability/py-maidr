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

    def test_axes_uses_canonical_per_axis_shape(self):
        trace = {"type": "bar", "x": ["A"], "y": [1]}
        layout = {"xaxis": {"title": "Cat"}, "yaxis": {"title": "Val"}}
        plot = PlotlyBarPlot(trace, layout)
        axes = plot.schema[MaidrKey.AXES]

        # Per-axis AxisConfig objects (never bare strings)
        assert isinstance(axes[MaidrKey.X], dict)
        assert isinstance(axes[MaidrKey.Y], dict)
        assert axes[MaidrKey.X][MaidrKey.LABEL] == "Cat"
        assert axes[MaidrKey.Y][MaidrKey.LABEL] == "Val"
        # No forbidden sibling keys (format/min/max/tickStep/fill/level)
        for forbidden in ("format", "min", "max", "tickStep", "fill", "level"):
            assert forbidden not in axes
            # also in enum form
            assert not any(
                (k.value if hasattr(k, "value") else k) == forbidden for k in axes
            )

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

    def test_scatter_axes_canonical_per_axis(self):
        trace = {"type": "scatter", "x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0]}
        layout = {
            "xaxis": {"title": "X"},
            "yaxis": {"title": "Y"},
        }
        plot = PlotlyScatterPlot(trace, layout)
        axes = plot.schema[MaidrKey.AXES]

        assert isinstance(axes[MaidrKey.X], dict)
        assert isinstance(axes[MaidrKey.Y], dict)
        # Grid-nav invalid (no explicit range/dtick): labels only.
        assert axes[MaidrKey.X][MaidrKey.LABEL] == "X"
        assert axes[MaidrKey.Y][MaidrKey.LABEL] == "Y"

    def test_scatter_axes_grid_config_nested(self):
        trace = {"type": "scatter", "x": [0, 10], "y": [0, 10]}
        layout = {
            "xaxis": {"title": "X", "range": [0, 10], "dtick": 1},
            "yaxis": {"title": "Y", "range": [0, 10], "dtick": 2},
        }
        plot = PlotlyScatterPlot(trace, layout)
        axes = plot.schema[MaidrKey.AXES]

        # min/max/tickStep nested inside each AxisConfig, not siblings.
        assert axes[MaidrKey.X][MaidrKey.MIN] == 0.0
        assert axes[MaidrKey.X][MaidrKey.MAX] == 10.0
        assert axes[MaidrKey.X][MaidrKey.TICK_STEP] == 1.0
        assert axes[MaidrKey.Y][MaidrKey.TICK_STEP] == 2.0
        # No sibling numeric fields at top of axes.
        for forbidden in ("min", "max", "tickStep", "format", "fill", "level"):
            assert forbidden not in axes


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
        assert data[0][0][MaidrKey.Z] == "Series A"

    def test_no_name_omits_z(self):
        trace = {"type": "scatter", "mode": "lines", "x": [1], "y": [2]}
        plot = PlotlyLinePlot(trace, {})
        data = plot._extract_plot_data()

        assert MaidrKey.Z not in data[0][0]


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
        assert data[0]["z"] == "A"
        assert data[1]["z"] == "B"


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

    def test_axes_z_is_axis_config_dict(self):
        trace = {
            "type": "heatmap",
            "z": [[1, 2], [3, 4]],
            "colorbar": {"title": {"text": "Intensity"}},
        }
        layout = {"xaxis": {"title": "Col"}, "yaxis": {"title": "Row"}}
        plot = PlotlyHeatmapPlot(trace, layout)
        axes = plot.schema[MaidrKey.AXES]

        # z must be a dict (AxisConfig), never a bare string
        assert isinstance(axes[MaidrKey.Z], dict)
        assert axes[MaidrKey.Z][MaidrKey.LABEL] == "Intensity"
        assert isinstance(axes[MaidrKey.X], dict)
        assert isinstance(axes[MaidrKey.Y], dict)

    def test_axes_omits_z_when_no_colorbar_title(self):
        trace = {"type": "heatmap", "z": [[1, 2], [3, 4]]}
        plot = PlotlyHeatmapPlot(trace, {})
        axes = plot.schema[MaidrKey.AXES]

        assert MaidrKey.Z not in axes


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
        assert data[0][0] == {"x": "A", "z": "G1", "y": 10}
        assert data[1][1] == {"x": "B", "z": "G2", "y": 25}

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
        assert data[0][0][MaidrKey.Z] == "A"
        assert data[1][0][MaidrKey.Z] == "B"

    def test_single_layer_schema(self):
        traces = [
            {"type": "scatter", "mode": "lines", "x": [1], "y": [2], "name": "L1"},
            {"type": "scatter", "mode": "lines", "x": [1], "y": [3], "name": "L2"},
        ]
        plot = PlotlyMultiLinePlot(traces, {})
        schema = plot.schema

        assert schema[MaidrKey.TYPE] == PlotType.LINE
        assert len(schema[MaidrKey.DATA]) == 2
