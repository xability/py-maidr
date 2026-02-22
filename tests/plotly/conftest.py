from __future__ import annotations

import numpy as np
import pytest

plotly = pytest.importorskip("plotly")
import plotly.graph_objects as go  # noqa: E402


@pytest.fixture
def plotly_bar_fig():
    """Create a simple Plotly bar chart."""
    fig = go.Figure(
        data=[go.Bar(x=["A", "B", "C"], y=[10, 20, 30])],
        layout=go.Layout(
            title="Test Bar Chart",
            xaxis=dict(title="Category"),
            yaxis=dict(title="Value"),
        ),
    )
    return fig


@pytest.fixture
def plotly_scatter_fig():
    """Create a simple Plotly scatter plot."""
    fig = go.Figure(
        data=[go.Scatter(x=[1, 2, 3], y=[4, 5, 6], mode="markers")],
        layout=go.Layout(
            title="Test Scatter Plot",
            xaxis=dict(title="X Axis"),
            yaxis=dict(title="Y Axis"),
        ),
    )
    return fig


@pytest.fixture
def plotly_line_fig():
    """Create a simple Plotly line chart."""
    fig = go.Figure(
        data=[
            go.Scatter(
                x=[1, 2, 3], y=[10, 20, 15], mode="lines", name="Series A"
            )
        ],
        layout=go.Layout(
            title="Test Line Chart",
            xaxis=dict(title="Time"),
            yaxis=dict(title="Value"),
        ),
    )
    return fig


@pytest.fixture
def plotly_box_fig():
    """Create a simple Plotly box plot from raw data."""
    np.random.seed(42)
    fig = go.Figure(
        data=[go.Box(y=np.random.randn(50).tolist(), name="Group A")],
        layout=go.Layout(
            title="Test Box Plot",
            yaxis=dict(title="Value"),
        ),
    )
    return fig


@pytest.fixture
def plotly_heatmap_fig():
    """Create a simple Plotly heatmap."""
    fig = go.Figure(
        data=[
            go.Heatmap(
                z=[[1, 2, 3], [4, 5, 6]],
                x=["a", "b", "c"],
                y=["row1", "row2"],
            )
        ],
        layout=go.Layout(
            title="Test Heatmap",
            xaxis=dict(title="Columns"),
            yaxis=dict(title="Rows"),
        ),
    )
    return fig


@pytest.fixture
def plotly_histogram_fig():
    """Create a simple Plotly histogram."""
    np.random.seed(42)
    fig = go.Figure(
        data=[go.Histogram(x=np.random.randn(100).tolist())],
        layout=go.Layout(
            title="Test Histogram",
            xaxis=dict(title="Value"),
            yaxis=dict(title="Count"),
        ),
    )
    return fig
