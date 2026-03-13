#!/usr/bin/env python3
"""
Example of creating a facet plot with Plotly.

This script demonstrates how to create a figure with multiple panels
containing bar plots that share the same axes, creating a facet plot.
Each panel represents data for a different category or condition,
mirroring the matplotlib facet bar plot example.
"""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import maidr

categories = ["A", "B", "C", "D", "E"]

np.random.seed(42)
data_group1 = (np.random.rand(5) * 10).tolist()
data_group2 = (np.random.rand(5) * 100).tolist()
data_group3 = (np.random.rand(5) * 36).tolist()
data_group4 = (np.random.rand(5) * 42).tolist()

data_sets = [data_group1, data_group2, data_group3, data_group4]
condition_names = ["Group 1", "Group 2", "Group 3", "Group 4"]

# Compute consistent y-axis limits across all groups
all_data = np.concatenate(data_sets)
y_min = float(np.min(all_data) * 0.9)
y_max = float(np.max(all_data) * 1.1)

# Colors matching C0..C3 from matplotlib's default cycle
colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

# Create a 2x2 faceted layout
fig = make_subplots(
    rows=2,
    cols=2,
    subplot_titles=tuple(condition_names),
    shared_xaxes=True,
    shared_yaxes=True,
)

# Add a bar trace to each subplot
for i, (data, condition) in enumerate(zip(data_sets, condition_names)):
    row = i // 2 + 1
    col = i % 2 + 1
    fig.add_trace(
        go.Bar(
            x=categories,
            y=data,
            name=condition,
            marker_color=colors[i],
            opacity=0.7,
            text=[f"{v:.1f}" for v in data],
            textposition="outside",
        ),
        row=row,
        col=col,
    )

# Apply consistent y-axis range and tick formatting
for i in range(1, 5):
    yaxis_key = f"yaxis{i}" if i > 1 else "yaxis"
    fig.layout[yaxis_key].update(range=[y_min, y_max], tickformat=".1f")

# Axes labels
fig.update_xaxes(title_text="Categories", row=2, col=1)
fig.update_xaxes(title_text="Categories", row=2, col=2)
fig.update_yaxes(title_text="Values", row=1, col=1)
fig.update_yaxes(title_text="Values", row=2, col=1)

fig.update_layout(
    title="Facet Plot: Bar Charts by Condition",
    height=700,
    showlegend=False,
)

maidr.show(fig)
