import plotly.graph_objects as go
import seaborn as sns

import maidr

# Load the dataset
iris = sns.load_dataset("iris")

# Choose a column for the histogram
data = iris["petal_length"]

# Create the histogram plot
fig = go.Figure(
    data=[
        go.Histogram(
            x=data.tolist(),
            nbinsx=20,
            marker=dict(color="steelblue", line=dict(color="black", width=1)),
        )
    ],
    layout=go.Layout(
        title="Histogram of Petal Lengths in Iris Dataset",
        xaxis=dict(title="Petal Length (cm)", tickformat=".1f"),
        yaxis=dict(title="Frequency", tickformat=".0f"),
    ),
)

maidr.show(fig)
