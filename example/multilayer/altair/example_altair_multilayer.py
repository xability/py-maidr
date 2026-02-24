import altair as alt
import numpy as np
import pandas as pd

import maidr

# Generate sample data
x = np.arange(5)
bar_data = np.array([3, 5, 2, 7, 3])
line_data = np.array([10, 8, 12, 14, 9])

df = pd.DataFrame({"x": x, "bar_values": bar_data, "line_values": line_data})

# Create the bar chart
bar = (
    alt.Chart(df)
    .mark_bar(color="skyblue")
    .encode(
        x=alt.X("x:O", title="X values"),
        y=alt.Y("bar_values:Q", title="Bar values"),
    )
)

# Create the line chart on a secondary y-axis
line = (
    alt.Chart(df)
    .mark_line(color="red", point=True, strokeWidth=2)
    .encode(
        x=alt.X("x:O"),
        y=alt.Y("line_values:Q", title="Line values"),
    )
)

# Combine using layer with independent y-axes
chart = (
    alt.layer(bar, line)
    .resolve_scale(y="independent")
    .properties(title="Multilayer Plot Example", width=400, height=300)
)

maidr.show(chart)
