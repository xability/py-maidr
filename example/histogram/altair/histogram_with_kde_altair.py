"""
Histogram with KDE overlay using Altair
----------------------------------------
This example demonstrates how to overlay a kernel density estimate (KDE) on a
histogram using Altair. It uses MAIDR integration for interactive accessibility.
"""

import altair as alt
import numpy as np
import pandas as pd

import maidr

# Generate sample data (e.g., normally distributed data)
np.random.seed(0)
data = np.random.normal(loc=0, scale=1, size=200)
df = pd.DataFrame({"value": data})

# Create histogram (using density so that the histogram integrates to 1)
histogram = (
    alt.Chart(df)
    .mark_bar(opacity=0.6, color="blue")
    .encode(
        x=alt.X("value:Q", bin=alt.Bin(maxbins=20), title="Value"),
        y=alt.Y("count():Q", stack=None, title="Density").stack("normalize"),
    )
)

# Create KDE overlay using Altair's density transform
kde = (
    alt.Chart(df)
    .transform_density("value", as_=["value", "density"])
    .mark_line(color="red", strokeWidth=2)
    .encode(
        x="value:Q",
        y=alt.Y("density:Q", title="Density"),
    )
)

# Combine histogram and KDE
chart = (
    (histogram + kde)
    .properties(title="Histogram with KDE Overlay (Altair)", width=400, height=300)
)

# Show with MAIDR for interactive accessibility
maidr.show(chart)
