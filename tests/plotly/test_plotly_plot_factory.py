from __future__ import annotations

import pytest

from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot_factory import PlotlyPlotFactory
from maidr.plotly.bar import PlotlyBarPlot
from maidr.plotly.scatter import PlotlyScatterPlot
from maidr.plotly.line import PlotlyLinePlot
from maidr.plotly.box import PlotlyBoxPlot
from maidr.plotly.heatmap import PlotlyHeatmapPlot
from maidr.plotly.histogram import PlotlyHistogramPlot
from maidr.plotly.pie import PlotlyPiePlot
from maidr.plotly.candlestick import PlotlyCandlestickPlot

plotly = pytest.importorskip("plotly")


class TestPlotlyPlotFactory:
    """Tests for PlotlyPlotFactory.create()."""

    def test_bar_trace(self):
        trace = {"type": "bar", "x": ["A"], "y": [1]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyBarPlot)
        assert plot.type == PlotType.BAR

    def test_scatter_markers_trace(self):
        trace = {"type": "scatter", "mode": "markers", "x": [1], "y": [2]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyScatterPlot)
        assert plot.type == PlotType.SCATTER

    def test_scatter_lines_trace(self):
        trace = {"type": "scatter", "mode": "lines", "x": [1], "y": [2]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyLinePlot)
        assert plot.type == PlotType.LINE

    def test_scatter_lines_markers_is_scatter(self):
        trace = {
            "type": "scatter",
            "mode": "lines+markers",
            "x": [1],
            "y": [2],
        }
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyScatterPlot)

    def test_scatter_default_mode_is_markers(self):
        trace = {"type": "scatter", "x": [1], "y": [2]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyScatterPlot)

    def test_box_trace(self):
        trace = {"type": "box", "y": [1, 2, 3]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyBoxPlot)
        assert plot.type == PlotType.BOX

    def test_heatmap_trace(self):
        trace = {"type": "heatmap", "z": [[1, 2], [3, 4]]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyHeatmapPlot)
        assert plot.type == PlotType.HEAT

    def test_histogram_trace(self):
        trace = {"type": "histogram", "x": [1, 2, 3]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyHistogramPlot)
        assert plot.type == PlotType.HIST

    def test_pie_trace(self):
        trace = {"type": "pie", "labels": ["A", "B"], "values": [1, 2]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyPiePlot)
        assert plot.type == PlotType.PIE

    def test_donut_trace_is_still_a_pie(self):
        # `hole` cuts the middle out of the wedges; the data is unchanged.
        trace = {"type": "pie", "labels": ["A", "B"], "values": [1, 2], "hole": 0.4}
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyPiePlot)

    def test_pie_assumes_it_is_the_only_one(self):
        # This factory sees one trace and cannot know what else the figure
        # holds, so it scopes the selector to the first pie. `PlotlyMaidr`
        # passes real positions precisely because it does know.
        trace = {"type": "pie", "labels": ["A"], "values": [1]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert "nth-child(1)" in plot._get_selector()

    def test_candlestick_trace(self):
        trace = {
            "type": "candlestick",
            "x": ["d1"],
            "open": [1.0],
            "high": [2.0],
            "low": [0.0],
            "close": [1.5],
        }
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyCandlestickPlot)
        assert plot.type == PlotType.CANDLESTICK

    def test_ohlc_trace_is_the_same_type(self):
        # `ohlc` draws the same numbers differently, so it is one MAIDR type
        # with the candlestick -- but a different DOM layer, which is what
        # the selector below is checking has followed the trace type.
        trace = {
            "type": "ohlc",
            "x": ["d1"],
            "open": [1.0],
            "high": [2.0],
            "low": [0.0],
            "close": [1.5],
        }
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyCandlestickPlot)
        assert plot.type == PlotType.CANDLESTICK
        assert ".ohlclayer" in plot._get_selector()

    def test_candlestick_assumes_it_is_the_only_one(self):
        # Same reasoning as the pie above: this factory sees one trace and
        # cannot know what else shares its `boxlayer`, so it scopes to the
        # first slot. `PlotlyMaidr` passes real positions because it does know.
        trace = {
            "type": "candlestick",
            "x": ["d1"],
            "open": [1.0],
            "high": [2.0],
            "low": [0.0],
            "close": [1.5],
        }
        plot = PlotlyPlotFactory.create(trace, {})
        assert "nth-child(1)" in plot._get_selector()

    def test_unsupported_trace_returns_none(self):
        trace = {"type": "sunburst", "labels": ["a"], "values": [1]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert plot is None

    def test_a_violin_is_not_built_here(self):
        # A violin *is* supported, but only through `PlotlyMaidr`: its two
        # layers are shared by every violin trace on the subplot, and the
        # selectors need each trace's position among them -- neither of which
        # this factory can see from one trace. Returning `None` is therefore
        # "not mine to build", not "not supported", and this test says which.
        trace = {"type": "violin", "y": [1, 2, 3]}
        assert PlotlyPlotFactory.create(trace, {}) is None
