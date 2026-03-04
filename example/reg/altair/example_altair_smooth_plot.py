import altair as alt
import numpy as np
import pandas as pd

import maidr

# Generate synthetic data
np.random.seed(0)
x = np.linspace(0, 10, 100)
y = np.sin(x) + 0.3 * np.random.randn(100)
df = pd.DataFrame({"x": x, "y": y})

# Create scatter points
scatter = (
    alt.Chart(df)
    .mark_point(color="blue", opacity=0.6)
    .encode(
        x=alt.X("x:Q", title="x"),
        y=alt.Y("y:Q", title="y"),
    )
)

# Create LOESS smooth line using Altair's loess transform
smooth = (
    alt.Chart(df)
    .mark_line(color="red", strokeWidth=2)
    .transform_loess("x", "y")
    .encode(
        x="x:Q",
        y="y:Q",
    )
)

# Combine scatter and smooth line
chart = (scatter + smooth).properties(
    title="Altair: Scatter with LOESS Smooth Line", width=400, height=300
)

maidr.show(chart)
