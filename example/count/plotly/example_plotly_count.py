import plotly.graph_objects as go

import maidr

# Count plot is a histogram with categorical data
species = [
    "Adelie", "Adelie", "Adelie", "Adelie", "Adelie",
    "Chinstrap", "Chinstrap", "Chinstrap",
    "Gentoo", "Gentoo", "Gentoo", "Gentoo",
]

fig = go.Figure(
    data=[go.Histogram(x=species)],
    layout=go.Layout(
        title="Penguin Species Count",
        xaxis=dict(title="Species"),
        yaxis=dict(title="Count"),
    ),
)

maidr.show(fig)
