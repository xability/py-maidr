import plotly.graph_objects as go
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")

# Plot sepal_length vs sepal_width
fig = go.Figure(
    data=[
        go.Scatter(
            x=iris["sepal_length"].tolist(),
            y=iris["sepal_width"].tolist(),
            mode="markers",
            marker=dict(color="blue", size=6),
            name="Iris Data Points",
        )
    ],
    layout=go.Layout(
        title="Iris Dataset: Sepal Length vs Sepal Width",
        xaxis=dict(title="Sepal Length (cm)"),
        yaxis=dict(title="Sepal Width (cm)"),
    ),
)

maidr.show(fig)
