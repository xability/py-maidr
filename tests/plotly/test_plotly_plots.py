from __future__ import annotations

import numpy as np
import pytest

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
from maidr.plotly.pie import PlotlyPiePlot

pytest.importorskip("plotly")


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
        plot = PlotlyLinePlot(trace, {}, scatter_position=0)
        data = plot._extract_plot_data()

        # Line data is wrapped in an outer list
        assert len(data) == 1
        assert len(data[0]) == 3
        assert data[0][0][MaidrKey.X] == 1
        assert data[0][0][MaidrKey.Y] == 10
        assert data[0][0][MaidrKey.Z] == "Series A"

    def test_no_name_omits_z(self):
        trace = {"type": "scatter", "mode": "lines", "x": [1], "y": [2]}
        plot = PlotlyLinePlot(trace, {}, scatter_position=0)
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
        # Turned over: plotly numbers a heatmap's rows from the bottom, so
        # "r2" is the one drawn at the top and the schema leads with it
        # (#487). What this case is about is that the fields are extracted
        # at all; the order is tests/plotly/test_plotly_heatmap_row_order.py.
        assert data[MaidrKey.POINTS] == [[4.0, 5.0, 6.0], [1.0, 2.0, 3.0]]
        assert data[MaidrKey.X] == ["a", "b", "c"]
        assert data[MaidrKey.Y] == ["r2", "r1"]

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


class TestPlotlyPiePlot:
    """One flat point per drawn wedge, in the order plotly draws them.

    Plotly does not draw one wedge per ``values`` entry in the order given:
    ``pie/calc.js`` builds its own slice list first, dropping and merging
    entries and then — by default — sorting them. The emitted data has to
    follow that list exactly, because the selector is positional, so the
    first divergence lands every later slice on another wedge.
    """

    def test_extract_data(self):
        trace = {
            "type": "pie",
            "labels": ["Apples", "Bananas", "Cherries"],
            "values": [30, 50, 20],
            "sort": False,
        }
        plot = PlotlyPiePlot(trace, {})
        data = plot._extract_plot_data()

        assert data == [
            {MaidrKey.X: "Apples", MaidrKey.Y: 30},
            {MaidrKey.X: "Bananas", MaidrKey.Y: 50},
            {MaidrKey.X: "Cherries", MaidrKey.Y: 20},
        ]

    def test_data_is_flat_and_carries_no_percentage(self):
        # Percentage is derived from the values by the renderer, so a layer
        # that emitted one would be a second source of truth.
        trace = {"type": "pie", "labels": ["A", "B"], "values": [1, 3]}
        plot = PlotlyPiePlot(trace, {})
        schema = plot.schema

        assert schema[MaidrKey.TYPE] == PlotType.PIE
        data = schema[MaidrKey.DATA]
        assert all(set(point) == {MaidrKey.X, MaidrKey.Y} for point in data)
        assert "orientation" not in schema

    def test_sort_default_orders_slices_largest_first(self):
        # This is the rule that silently misaligns every selector if ignored:
        # plotly sorts by default, so data order is not slice order.
        trace = {"type": "pie", "labels": ["A", "B", "C"], "values": [30, 50, 20]}
        plot = PlotlyPiePlot(trace, {})
        data = plot._extract_plot_data()

        assert [point[MaidrKey.X] for point in data] == ["B", "A", "C"]

    def test_duplicate_labels_merge_at_the_first_position(self):
        trace = {
            "type": "pie",
            "labels": ["A", "B", "A"],
            "values": [1, 2, 3],
            "sort": False,
        }
        plot = PlotlyPiePlot(trace, {})

        assert plot._slices() == [("A", 4), ("B", 2)]

    def test_a_non_numeric_value_draws_no_wedge(self):
        trace = {
            "type": "pie",
            "labels": ["A", "B", "C"],
            "values": [1, "not a number", 3],
            "sort": False,
        }
        plot = PlotlyPiePlot(trace, {})

        assert plot._slices() == [("A", 1), ("C", 3)]

    def test_a_negative_wedge_is_dropped(self):
        trace = {
            "type": "pie",
            "labels": ["A", "B"],
            "values": [-1, 2],
            "sort": False,
        }
        plot = PlotlyPiePlot(trace, {})

        assert plot._slices() == [("B", 2)]

    def test_a_zero_valued_slice_is_kept(self):
        # Plotly's calc filters `v >= 0`, not `v > 0`, so a zero-valued entry
        # stays in the slice list and takes a position in it. Dropping it here
        # would shift every later slice onto the wrong element.
        trace = {
            "type": "pie",
            "labels": ["A", "B", "C"],
            "values": [0, 5, 3],
            "sort": False,
        }
        plot = PlotlyPiePlot(trace, {})

        assert plot._slices() == [("A", 0), ("B", 5), ("C", 3)]

    def test_slices_that_cancel_to_zero_are_kept(self):
        # Two entries sharing a label merge, and the merged total is what the
        # `>= 0` filter sees.
        trace = {
            "type": "pie",
            "labels": ["A", "A", "B"],
            "values": [-2, 2, 5],
            "sort": False,
        }
        plot = PlotlyPiePlot(trace, {})

        assert plot._slices() == [("A", 0), ("B", 5)]

    def test_a_hidden_label_is_not_emitted(self):
        trace = {"type": "pie", "labels": ["A", "B"], "values": [1, 2], "sort": False}
        plot = PlotlyPiePlot(trace, {"hiddenlabels": ["A"]})

        assert plot._slices() == [("B", 2)]

    def test_a_null_label_hides_by_its_wedge_name(self):
        trace = {"type": "pie", "labels": [None, "B"], "values": [1, 2], "sort": False}
        plot = PlotlyPiePlot(trace, {"hiddenlabels": ["null"]})

        assert plot._slices() == [("B", 2)]

    def test_a_raw_none_hides_nothing_because_plotly_hides_nothing(self):
        # Plotly compares with `indexOf` against the stringified label, and
        # `[null].indexOf("null")` is -1 -- so it keeps drawing the wedge.
        # Dropping it here would leave a drawn wedge with no data point and
        # shift every later slice onto the wrong element.
        trace = {"type": "pie", "labels": [None, "B"], "values": [1, 2], "sort": False}
        plot = PlotlyPiePlot(trace, {"hiddenlabels": [None]})

        assert plot._slices() == [("null", 1), ("B", 2)]

    def test_a_numeric_hidden_entry_hides_nothing(self):
        # Same rule: `[5].indexOf("5")` is -1, so plotly draws it.
        trace = {"type": "pie", "labels": [5, "B"], "values": [1, 2], "sort": False}
        plot = PlotlyPiePlot(trace, {"hiddenlabels": [5]})

        assert plot._slices() == [("5", 1), ("B", 2)]

    def test_a_numeric_label_hides_by_its_stringified_name(self):
        trace = {"type": "pie", "labels": [5, "B"], "values": [1, 2], "sort": False}
        plot = PlotlyPiePlot(trace, {"hiddenlabels": ["5"]})

        assert plot._slices() == [("B", 2)]

    def test_an_empty_hidden_label_matches_nothing(self):
        # An empty label became the entry's own index, so `""` names no wedge.
        trace = {"type": "pie", "labels": ["", "B"], "values": [1, 2], "sort": False}
        plot = PlotlyPiePlot(trace, {"hiddenlabels": [""]})

        assert plot._slices() == [("0", 1), ("B", 2)]

    def test_an_empty_label_hides_by_the_index_it_became(self):
        trace = {"type": "pie", "labels": ["", "B"], "values": [1, 2], "sort": False}
        plot = PlotlyPiePlot(trace, {"hiddenlabels": ["0"]})

        assert plot._slices() == [("B", 2)]

    def test_nothing_positive_draws_nothing(self):
        trace = {"type": "pie", "labels": ["A", "B"], "values": [0, 0]}
        plot = PlotlyPiePlot(trace, {})

        assert plot._extract_plot_data() == []

    def test_a_pie_with_no_drawn_slice_still_builds_a_schema(self):
        # An empty layer has to reach the wire intact rather than raise part
        # way through: the figure around it is still describable, and a plot
        # that throws here takes every other layer down with it.
        trace = {"type": "pie", "labels": ["A", "B"], "values": [0, 0]}
        plot = PlotlyPiePlot(trace, {})

        schema = plot.schema

        assert schema["type"] == PlotType.PIE
        assert schema["data"] == []
        assert set(schema["axes"]) == {"x", "y"}

    def test_an_all_hidden_pie_still_builds_a_schema(self):
        trace = {"type": "pie", "labels": ["A", "B"], "values": [1, 2]}
        plot = PlotlyPiePlot(trace, {"hiddenlabels": ["A", "B"]})

        schema = plot.schema

        assert schema["data"] == []

    def test_labels_without_values_count_the_labels(self):
        trace = {"type": "pie", "labels": ["A", "B", "A"], "sort": False}
        plot = PlotlyPiePlot(trace, {})

        assert plot._slices() == [("A", 2), ("B", 1)]

    def test_values_without_labels_are_numbered(self):
        trace = {"type": "pie", "values": [1, 2], "sort": False}
        plot = PlotlyPiePlot(trace, {})

        assert plot._slices() == [("0", 1), ("1", 2)]

    def test_typed_array_values_are_decoded(self):
        # ``plotly.express`` exports every numeric column as the base64
        # typed-array spec plotly.js consumes; iterating it would otherwise
        # walk the two dict keys.
        import base64

        bdata = base64.b64encode(np.array([30.0, 50.0, 20.0]).tobytes()).decode()
        trace = {
            "type": "pie",
            "labels": ["A", "B", "C"],
            "values": {"dtype": "f8", "bdata": bdata},
            "sort": False,
        }
        plot = PlotlyPiePlot(trace, {})

        assert plot._slices() == [("A", 30.0), ("B", 50.0), ("C", 20.0)]

    def test_selector_is_scoped_to_the_pie_layer(self):
        # Pies are drawn into a figure-level `pielayer`, never into a
        # `.subplot.xy` group, so a subplot-prefixed selector would match
        # nothing.
        trace = {"type": "pie", "labels": ["A"], "values": [1]}
        plot = PlotlyPiePlot(trace, {}, pie_position=2)
        selector = plot.schema[MaidrKey.SELECTOR]

        assert selector == ".pielayer > .trace:nth-child(3) > .slice > path.surface"

    def test_a_negative_position_is_rejected(self):
        # `nth-child(0)` matches nothing, so the highlight would simply never
        # appear -- a silent failure worth refusing at construction.
        trace = {"type": "pie", "labels": ["A"], "values": [1]}
        with pytest.raises(ValueError, match="pie position"):
            PlotlyPiePlot(trace, {}, pie_position=-1)

    def test_axes_name_the_slice_dimensions(self):
        trace = {"type": "pie", "labels": ["A"], "values": [1]}
        layout = {"xaxis": {"title": "Fruit"}, "yaxis": {"title": "Units"}}
        plot = PlotlyPiePlot(trace, layout)
        axes = plot.schema[MaidrKey.AXES]

        assert axes[MaidrKey.X][MaidrKey.LABEL] == "Fruit"
        assert axes[MaidrKey.Y][MaidrKey.LABEL] == "Units"
        assert MaidrKey.Z not in axes

    def test_unnamed_axes_read_as_english(self):
        # Plotly names neither axis of a pie, and MAIDR reads a slice out as
        # those two names. The pair matches the matplotlib pie's own fallback:
        # the announcement follows the plot type, not the library behind it.
        plot = PlotlyPiePlot({"type": "pie", "labels": ["A"], "values": [1]}, {})
        axes = plot.schema[MaidrKey.AXES]

        assert axes[MaidrKey.X][MaidrKey.LABEL] == "Category"
        assert axes[MaidrKey.Y][MaidrKey.LABEL] == "Value"


class TestPlotlyMultiLinePlot:
    def test_merges_traces_into_list_of_lists(self):
        traces = [
            {"type": "scatter", "mode": "lines", "x": [1, 2], "y": [10, 20], "name": "A"},
            {"type": "scatter", "mode": "lines", "x": [1, 2], "y": [5, 15], "name": "B"},
        ]
        plot = PlotlyMultiLinePlot(traces, {}, scatter_positions=[0, 1])
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
        plot = PlotlyMultiLinePlot(traces, {}, scatter_positions=[0, 1])
        schema = plot.schema

        assert schema[MaidrKey.TYPE] == PlotType.LINE
        assert len(schema[MaidrKey.DATA]) == 2
