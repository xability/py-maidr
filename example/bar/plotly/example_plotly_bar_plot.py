import plotly.graph_objects as go
import seaborn as sns

import maidr

# Load the penguins dataset
penguins = sns.load_dataset("penguins")

# Calculate average body mass by species
avg_mass = penguins.groupby("species")["body_mass_g"].mean()

# Create a bar plot showing the average body mass of penguins by species
fig = go.Figure(
    data=[
        go.Bar(
            x=avg_mass.index.tolist(),
            y=avg_mass.values.tolist(),
            marker_color=["#4c72b0", "#55a868", "#c44e52"],
        )
    ],
    layout=go.Layout(
        title="Average Body Mass of Penguins by Species",
        xaxis=dict(title="Species"),
        yaxis=dict(title="Body Mass (g)"),
    ),
)

maidr.show(fig)
