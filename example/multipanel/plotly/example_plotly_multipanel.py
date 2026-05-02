"""
Example of creating a multipanel plot with Plotly.

This script demonstrates how to create a figure with multiple panels
containing different types of plots: line plot, bar plot, and scatter plot,
mirroring the matplotlib multipanel example.
"""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import maidr

# Data for line plot
x_line = np.array([1, 2, 3, 4, 5, 6, 7, 8])
y_line = np.array([2, 4, 1, 5, 3, 7, 6, 8])

# Data for bar plot
np.random.seed(42)
categories = ["A", "B", "C", "D", "E"]
values = (np.random.rand(5) * 10).tolist()

# Data for scatter plot
np.random.seed(42)
x_scatter = np.random.randn(50).tolist()
y_scatter = np.random.randn(50).tolist()

# Create a figure with 3 subplots arranged vertically
fig = make_subplots(
    rows=3,
    cols=1,
    subplot_titles=("Line Plot: Random Data", "Bar Plot: Random Values", "Scatter Plot"),
)

# First panel: Line plot
fig.add_trace(
    go.Scatter(
        x=x_line.tolist(),
        y=y_line.tolist(),
        mode="lines",
        name="Line Data",
        line=dict(color="blue", width=2),
    ),
    row=1,
    col=1,
)

# Second panel: Bar plot
fig.add_trace(
    go.Bar(
        x=categories,
        y=values,
        name="Bar Data",
        marker_color="green",
        opacity=0.7,
    ),
    row=2,
    col=1,
)

# Third panel: Scatter plot
fig.add_trace(
    go.Scatter(
        x=x_scatter,
        y=y_scatter,
        mode="markers",
        name="Scatter Data",
        marker=dict(color="red", size=6),
    ),
    row=3,
    col=1,
)

# Update axes labels and formatting
fig.update_xaxes(title_text="X-axis", tickformat=".0f", row=1, col=1)
fig.update_yaxes(title_text="Values", tickformat=".0f", row=1, col=1)
fig.update_xaxes(title_text="Categories", row=2, col=1)
fig.update_yaxes(title_text="Values", tickformat=".1f", row=2, col=1)
fig.update_xaxes(title_text="X", tickformat=".1f", row=3, col=1)
fig.update_yaxes(title_text="Y", tickformat=".1f", row=3, col=1)

fig.update_layout(
    title="Multipanel Plot: Line, Bar, and Scatter",
    height=900,
    showlegend=False,
)

maidr.show(fig)
