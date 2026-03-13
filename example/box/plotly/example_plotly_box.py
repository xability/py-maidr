import numpy as np
import plotly.graph_objects as go

import maidr

# Vertical box plot with three groups
np.random.seed(42)
data_group1 = np.append(np.random.normal(100, 10, 200), [150, 160, 50, 40])
data_group2 = np.append(np.random.normal(90, 20, 200), [180, 190, 10, 20])
data_group3 = np.append(np.random.normal(80, 30, 200), [200, 210, -10, -20])

fig = go.Figure()
fig.add_trace(
    go.Box(y=data_group1.tolist(), name="Group 1", marker_color="lightblue")
)
fig.add_trace(
    go.Box(y=data_group2.tolist(), name="Group 2", marker_color="lightgreen")
)
fig.add_trace(
    go.Box(y=data_group3.tolist(), name="Group 3", marker_color="tan")
)

fig.update_layout(
    title="Vertical Box Plot",
    xaxis=dict(title="Group"),
    yaxis=dict(title="Values", tickformat=".1f"),
)

maidr.show(fig)
