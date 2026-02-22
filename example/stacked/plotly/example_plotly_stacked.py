import plotly.graph_objects as go

import maidr

fig = go.Figure(
    data=[
        go.Bar(
            name="Adelie", x=["Torgersen", "Biscoe", "Dream"], y=[47, 44, 56]
        ),
        go.Bar(
            name="Chinstrap", x=["Torgersen", "Biscoe", "Dream"], y=[0, 0, 68]
        ),
        go.Bar(
            name="Gentoo", x=["Torgersen", "Biscoe", "Dream"], y=[0, 124, 0]
        ),
    ],
    layout=go.Layout(
        title="Penguin Count by Island (Stacked)",
        xaxis=dict(title="Island"),
        yaxis=dict(title="Count"),
        barmode="stack",
    ),
)

maidr.show(fig)
