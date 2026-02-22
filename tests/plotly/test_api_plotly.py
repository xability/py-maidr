from __future__ import annotations

import pytest

plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.api import _is_plotly_figure, render, save_html, close  # noqa: E402


# Minimal valid SVG for mocking to_image
_MOCK_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100"/></svg>'


class TestApiPlotlyDetection:
    """Test that the API correctly detects and routes Plotly figures."""

    def test_is_plotly_figure_positive(self):
        fig = go.Figure()
        assert _is_plotly_figure(fig) is True

    def test_is_plotly_figure_negative(self):
        assert _is_plotly_figure("not a figure") is False
        assert _is_plotly_figure(42) is False
        assert _is_plotly_figure(None) is False

    def test_render_plotly(self, plotly_bar_fig, mocker):
        mocker.patch.object(
            plotly_bar_fig, "to_image", return_value=_MOCK_SVG
        )
        tag = render(plotly_bar_fig)
        assert tag is not None

    def test_save_html_plotly(self, plotly_bar_fig, tmp_path, mocker):
        mocker.patch.object(
            plotly_bar_fig, "to_image", return_value=_MOCK_SVG
        )
        output = tmp_path / "api_plotly_test.html"
        result = save_html(plotly_bar_fig, file=str(output))
        assert result is not None

    def test_close_plotly_no_error(self, plotly_bar_fig):
        # close() for Plotly should be a no-op without errors
        close(plotly_bar_fig)
