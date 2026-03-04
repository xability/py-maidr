"""
Multiple KDE overlays with Altair and MAIDR
--------------------------------------------
This example demonstrates how to plot multiple kernel density estimates (KDEs)
for different groups using Altair's density transform, with MAIDR integration
for interactive accessibility and exploration.
"""

import altair as alt
import numpy as np
import pandas as pd

import maidr

# Generate sample data for three groups
np.random.seed(0)
data1 = np.random.normal(loc=0, scale=1, size=200)
data2 = np.random.normal(loc=2, scale=0.5, size=200)
data3 = np.random.normal(loc=-2, scale=1.5, size=200)

# Combine into a single DataFrame with group labels
df = pd.DataFrame(
    {
        "value": np.concatenate([data1, data2, data3]),
        "group": (
            ["Group 1"] * len(data1)
            + ["Group 2"] * len(data2)
            + ["Group 3"] * len(data3)
        ),
    }
)

# Create multiple KDE plots using density transform grouped by 'group'
kde_plot = (
    alt.Chart(df)
    .transform_density("value", groupby=["group"], as_=["value", "density"])
    .mark_line(strokeWidth=2)
    .encode(
        x=alt.X("value:Q", title="Value"),
        y=alt.Y("density:Q", title="Density"),
        color=alt.Color("group:N", title="Group"),
    )
    .properties(title="Multiple KDE Plots with Altair", width=400, height=300)
)

# Show with MAIDR for interactive accessibility
maidr.show(kde_plot)
