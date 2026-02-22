from __future__ import annotations


from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot_factory import PlotlyPlotFactory
from maidr.plotly.bar import PlotlyBarPlot
from maidr.plotly.scatter import PlotlyScatterPlot
from maidr.plotly.line import PlotlyLinePlot
from maidr.plotly.box import PlotlyBoxPlot
from maidr.plotly.heatmap import PlotlyHeatmapPlot
from maidr.plotly.histogram import PlotlyHistogramPlot
from maidr.plotly.candlestick import PlotlyCandlestickPlot


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

    def test_candlestick_trace(self):
        trace = {
            "type": "candlestick",
            "x": ["2024-01-02"],
            "open": [100],
            "high": [110],
            "low": [90],
            "close": [105],
        }
        plot = PlotlyPlotFactory.create(trace, {})
        assert isinstance(plot, PlotlyCandlestickPlot)
        assert plot.type == PlotType.CANDLESTICK

    def test_unsupported_trace_returns_none(self):
        trace = {"type": "pie", "values": [1, 2, 3]}
        plot = PlotlyPlotFactory.create(trace, {})
        assert plot is None
