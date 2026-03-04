"""
Example of creating a multipanel plot with Altair.

This script demonstrates how to create a figure with multiple panels
containing different types of plots: line plot, bar plot, and bar plot,
using Altair's vertical concatenation.
"""

import altair as alt
import numpy as np
import pandas as pd

import maidr

# Data for line plot
x_line = np.array([1, 2, 3, 4, 5, 6, 7, 8])
y_line = np.array([2, 4, 1, 5, 3, 7, 6, 8])
line_df = pd.DataFrame({"x": x_line, "y": y_line})

# Data for first bar plot
np.random.seed(42)
categories = ["A", "B", "C", "D", "E"]
values = np.random.rand(5) * 10
bar_df = pd.DataFrame({"categories": categories, "values": values})

# Data for second bar plot
values_2 = np.random.randn(5) * 100
bar_df_2 = pd.DataFrame({"categories": categories, "values": values_2})

# First panel: Line plot
line_panel = (
    alt.Chart(line_df)
    .mark_line(color="blue", point=True, strokeWidth=2)
    .encode(
        x=alt.X("x:Q", title="X-axis"),
        y=alt.Y("y:Q", title="Values"),
    )
    .properties(title="Line Plot: Random Data", width=400, height=200)
)

# Second panel: Bar plot
bar_panel_1 = (
    alt.Chart(bar_df)
    .mark_bar(color="green", opacity=0.7)
    .encode(
        x=alt.X("categories:N", title="Categories"),
        y=alt.Y("values:Q", title="Values"),
    )
    .properties(title="Bar Plot: Random Values", width=400, height=200)
)

# Third panel: Bar plot
bar_panel_2 = (
    alt.Chart(bar_df_2)
    .mark_bar(color="blue", opacity=0.7)
    .encode(
        x=alt.X("categories:N", title="Categories"),
        y=alt.Y("values:Q", title="Values"),
    )
    .properties(title="Bar Plot 2: Random Values", width=400, height=200)
)

# Vertically concatenate all panels
chart = alt.vconcat(line_panel, bar_panel_1, bar_panel_2).properties(
    title="Multipanel Plot Example"
)

maidr.show(chart)
