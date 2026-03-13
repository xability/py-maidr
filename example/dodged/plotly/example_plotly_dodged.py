import plotly.graph_objects as go

import maidr

fig = go.Figure(
    data=[
        go.Bar(name="Male", x=["Adelie", "Chinstrap", "Gentoo"], y=[4043, 3939, 5485]),
        go.Bar(
            name="Female", x=["Adelie", "Chinstrap", "Gentoo"], y=[3369, 3527, 4680]
        ),
    ],
    layout=go.Layout(
        title="Average Body Mass by Species and Sex",
        xaxis=dict(title="Species"),
        yaxis=dict(title="Body Mass (g)", tickformat=",.0f"),
        barmode="group",
    ),
)

maidr.show(fig)
