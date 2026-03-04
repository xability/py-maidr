import altair as alt
import numpy as np
import pandas as pd

import maidr

# Create sample data points
x = np.array([1, 2, 3, 4, 5, 6, 7, 8])
y1 = np.array([2, 4, 1, 5, 3, 7, 6, 8])
y2 = np.array([1, 3, 5, 2, 4, 6, 8, 7])
y3 = np.array([3, 1, 4, 6, 5, 2, 4, 5])

# Convert to long-form DataFrame for Altair
df = pd.DataFrame(
    {
        "x": np.tile(x, 3),
        "y": np.concatenate([y1, y2, y3]),
        "series": np.repeat(["Series 1", "Series 2", "Series 3"], len(x)),
    }
)

# Create a multiline plot
multiline_plot = (
    alt.Chart(df)
    .mark_line(point=True)
    .encode(
        x=alt.X("x:Q", title="X values"),
        y=alt.Y("y:Q", title="Y values"),
        color=alt.Color("series:N", title="Series"),
        strokeDash=alt.StrokeDash("series:N"),
    )
    .properties(title="Altair Multiline Plot", width=400, height=300)
)

maidr.show(multiline_plot)
