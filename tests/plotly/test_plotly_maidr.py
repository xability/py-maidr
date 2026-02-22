from __future__ import annotations

import pytest

plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402


class TestPlotlyMaidr:
    """Integration tests for PlotlyMaidr."""

    def test_creates_plots_from_bar_fig(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_scatter_fig(self, plotly_scatter_fig):
        pm = PlotlyMaidr(plotly_scatter_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_line_fig(self, plotly_line_fig):
        pm = PlotlyMaidr(plotly_line_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_box_fig(self, plotly_box_fig):
        pm = PlotlyMaidr(plotly_box_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_heatmap_fig(self, plotly_heatmap_fig):
        pm = PlotlyMaidr(plotly_heatmap_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_histogram_fig(self, plotly_histogram_fig):
        pm = PlotlyMaidr(plotly_histogram_fig)
        assert len(pm._plots) == 1

    def test_flatten_maidr_schema_structure(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        schema = pm._flatten_maidr()

        assert "id" in schema
        assert "subplots" in schema
        assert len(schema["subplots"]) == 1
        assert len(schema["subplots"][0]) == 1
        assert "layers" in schema["subplots"][0][0]

    def test_render_returns_tag(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        tag = pm.render()
        assert tag is not None

    def test_render_contains_plotly_js(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        tag = pm.render()
        html_str = str(tag.get_html_string())
        assert "plotly" in html_str.lower()

    def test_render_contains_maidr_schema(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        tag = pm.render()
        html_str = str(tag.get_html_string())
        assert "maidrSchema" in html_str
        assert "maidr.js" in html_str

    def test_save_html(self, plotly_bar_fig, tmp_path):
        pm = PlotlyMaidr(plotly_bar_fig)
        output = tmp_path / "test_plotly.html"
        result = pm.save_html(str(output))
        assert result is not None

    def test_multi_trace_figure(self):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=["A", "B"], y=[1, 2]))
        fig.add_trace(go.Scatter(x=[1, 2], y=[3, 4], mode="markers"))
        fig.update_layout(title="Multi")

        pm = PlotlyMaidr(fig)
        assert len(pm._plots) == 2

    def test_unsupported_trace_skipped(self):
        fig = go.Figure()
        fig.add_trace(go.Pie(values=[1, 2, 3], labels=["a", "b", "c"]))
        fig.add_trace(go.Bar(x=["A"], y=[1]))

        pm = PlotlyMaidr(fig)
        # Pie is unsupported and skipped
        assert len(pm._plots) == 1
