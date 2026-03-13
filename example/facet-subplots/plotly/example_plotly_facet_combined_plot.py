#!/usr/bin/env python3
"""
Example of creating a facet plot with Plotly that combines different plot types.

This script demonstrates how to create a figure with multiple panels
where the left column contains line plots and the right column contains
bar plots, mirroring the matplotlib facet combined plot example.
"""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import maidr


def generate_simple_data(
    num_rows: int = 3, num_points: int = 5
) -> tuple[np.ndarray, list[np.ndarray], list[np.ndarray]]:
    """Generate simple data for line and bar plots.

    Parameters
    ----------
    num_rows : int, optional
        Number of rows (facets) to generate data for, by default 3.
    num_points : int, optional
        Number of data points per plot, by default 5.

    Returns
    -------
    tuple[np.ndarray, list[np.ndarray], list[np.ndarray]]
        A tuple containing:
        - x values common for all plots
        - list of y values for line plots
        - list of y values for bar plots
    """
    x = np.arange(num_points)

    np.random.seed(42)
    line_data = [np.random.rand(num_points) * 10 for _ in range(num_rows)]
    bar_data = [np.abs(np.sin(x + i) * 5) + i for i in range(num_rows)]

    return x, line_data, bar_data


# Generate data
x, line_data, bar_data = generate_simple_data(num_rows=3)
num_rows = len(line_data)

# Build subplot titles: "Line Plot 1", "Bar Plot 1", "Line Plot 2", ...
subplot_titles = []
for r in range(1, num_rows + 1):
    subplot_titles.extend([f"Line Plot {r}", f"Bar Plot {r}"])

# Colors matching C0..C2 from matplotlib's default cycle
colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]

# Create a num_rows x 2 faceted layout (line plots left, bar plots right)
fig = make_subplots(
    rows=num_rows,
    cols=2,
    subplot_titles=tuple(subplot_titles),
    shared_yaxes="rows",
)

for row in range(num_rows):
    # Left column: line plot
    fig.add_trace(
        go.Scatter(
            x=x.tolist(),
            y=line_data[row].tolist(),
            mode="lines+markers",
            name=f"Line {row + 1}",
            line=dict(color=colors[row], width=2),
            marker=dict(size=6),
        ),
        row=row + 1,
        col=1,
    )

    # Right column: bar plot
    fig.add_trace(
        go.Bar(
            x=x.tolist(),
            y=bar_data[row].tolist(),
            name=f"Bar {row + 1}",
            marker_color=colors[row],
            opacity=0.7,
        ),
        row=row + 1,
        col=2,
    )

    # Y-axis label on left column only
    fig.update_yaxes(
        title_text=f"Values (Row {row + 1})",
        tickformat=".1f",
        row=row + 1,
        col=1,
    )
    fig.update_yaxes(tickformat=".1f", row=row + 1, col=2)

# X-axis labels on bottom row
fig.update_xaxes(title_text="X Values", tickformat=".0f", row=num_rows, col=1)
fig.update_xaxes(title_text="X Values", tickformat=".0f", row=num_rows, col=2)

fig.update_layout(
    title="Facet Plot Example with Shared Y-Axes",
    height=300 * num_rows,
    showlegend=False,
)

maidr.show(fig)
