import plotly.graph_objects as go

import maidr

fig = go.Figure(
    data=[
        go.Scatter(
            x=[2019, 2020, 2021, 2022, 2023],
            y=[100, 120, 115, 140, 160],
            mode="lines",
            name="Product A",
        ),
        go.Scatter(
            x=[2019, 2020, 2021, 2022, 2023],
            y=[80, 95, 110, 105, 130],
            mode="lines",
            name="Product B",
        ),
        go.Scatter(
            x=[2019, 2020, 2021, 2022, 2023],
            y=[60, 70, 85, 90, 100],
            mode="lines",
            name="Product C",
        ),
    ],
    layout=go.Layout(
        title="Sales Trends by Product",
        xaxis=dict(title="Year"),
        yaxis=dict(title="Sales (units)", tickformat=",.0f"),
    ),
)

maidr.show(fig)
