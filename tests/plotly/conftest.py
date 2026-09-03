from __future__ import annotations

import numpy as np
import pytest

# Not ``pytest.importorskip`` at module scope: the ``Skipped`` it raises
# escapes a conftest, and on pytest 7 that skips the *session* being
# collected -- zero tests, exit 5 -- rather than this directory.  Each
# fixture skips instead, which pytest scopes to the test asking for it;
# the modules in this directory guard their own ``plotly`` imports.
try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover - only without the plotly extra
    go = None


@pytest.fixture
def plotly_bar_fig():
    """Create a simple Plotly bar chart."""
    pytest.importorskip("plotly")
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
    pytest.importorskip("plotly")
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
    pytest.importorskip("plotly")
    fig = go.Figure(
        data=[go.Scatter(x=[1, 2, 3], y=[10, 20, 15], mode="lines", name="Series A")],
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
    pytest.importorskip("plotly")
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
    pytest.importorskip("plotly")
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
    pytest.importorskip("plotly")
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


@pytest.fixture
def plotly_pie_fig():
    """Create a simple Plotly pie chart."""
    pytest.importorskip("plotly")
    fig = go.Figure(
        data=[go.Pie(labels=["Apples", "Bananas", "Cherries"], values=[30, 50, 20])],
        layout=go.Layout(
            title="Test Pie Chart",
            xaxis=dict(title="Fruit"),
            yaxis=dict(title="Units"),
        ),
    )
    return fig


@pytest.fixture
def plotly_dodged_fig():
    """Create a grouped (dodged) bar chart."""
    pytest.importorskip("plotly")
    fig = go.Figure(
        data=[
            go.Bar(name="Male", x=["A", "B"], y=[10, 20]),
            go.Bar(name="Female", x=["A", "B"], y=[15, 25]),
        ],
        layout=go.Layout(
            title="Dodged Bar",
            xaxis=dict(title="Category"),
            yaxis=dict(title="Value"),
            barmode="group",
        ),
    )
    return fig


@pytest.fixture
def plotly_stacked_fig():
    """Create a stacked bar chart."""
    pytest.importorskip("plotly")
    fig = go.Figure(
        data=[
            go.Bar(name="Q1", x=["A", "B"], y=[10, 20]),
            go.Bar(name="Q2", x=["A", "B"], y=[15, 25]),
        ],
        layout=go.Layout(
            title="Stacked Bar",
            xaxis=dict(title="Category"),
            yaxis=dict(title="Value"),
            barmode="stack",
        ),
    )
    return fig


@pytest.fixture
def plotly_multiline_fig():
    """Create a multi-line chart."""
    pytest.importorskip("plotly")
    fig = go.Figure(
        data=[
            go.Scatter(x=[1, 2, 3], y=[10, 20, 15], mode="lines", name="A"),
            go.Scatter(x=[1, 2, 3], y=[5, 15, 25], mode="lines", name="B"),
        ],
        layout=go.Layout(
            title="Multi-line Chart",
            xaxis=dict(title="X"),
            yaxis=dict(title="Y"),
        ),
    )
    return fig
