"""
Single KDE Plot with Altair and MAIDR
--------------------------------------
This example demonstrates how to plot a single kernel density estimate (KDE)
using Altair's built-in density transform, with MAIDR integration for
interactive accessibility and exploration.
"""

import altair as alt
import numpy as np
import pandas as pd

import maidr

# Generate sample data
np.random.seed(42)
data = np.random.normal(loc=1, scale=2, size=300)
df = pd.DataFrame({"value": data})

# Create KDE plot using Altair's density transform
kde_plot = (
    alt.Chart(df)
    .transform_density("value", as_=["value", "density"])
    .mark_line(color="blue", strokeWidth=2)
    .encode(
        x=alt.X("value:Q", title="Value"),
        y=alt.Y("density:Q", title="Density"),
    )
    .properties(title="Single KDE Plot with Altair", width=400, height=300)
)

# Show with MAIDR for interactive accessibility
maidr.show(kde_plot)
