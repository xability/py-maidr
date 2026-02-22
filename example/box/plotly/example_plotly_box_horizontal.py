import numpy as np
import plotly.graph_objects as go

import maidr

# Horizontal box plot with three groups
np.random.seed(42)

fig = go.Figure()
fig.add_trace(
    go.Box(
        x=np.random.normal(100, 10, 200).tolist(),
        name="Group 1",
        marker_color="lightblue",
    )
)
fig.add_trace(
    go.Box(
        x=np.random.normal(90, 20, 200).tolist(),
        name="Group 2",
        marker_color="lightgreen",
    )
)
fig.add_trace(
    go.Box(
        x=np.random.normal(80, 30, 200).tolist(),
        name="Group 3",
        marker_color="tan",
    )
)

fig.update_layout(
    title="Horizontal Box Plot",
    xaxis=dict(title="Values"),
    yaxis=dict(title="Group"),
)

maidr.show(fig)
