import plotly.graph_objects as go

import maidr

fig = go.Figure(
    data=[
        go.Candlestick(
            x=["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"],
            open=[150.0, 152.5, 148.0, 155.0, 153.0],
            high=[155.0, 156.0, 155.5, 158.0, 157.0],
            low=[148.0, 149.0, 146.5, 152.0, 150.0],
            close=[152.5, 148.0, 155.0, 153.0, 156.5],
        )
    ],
    layout=go.Layout(
        title="Stock Price (Candlestick)",
        xaxis=dict(title="Date", type="date"),
        yaxis=dict(title="Price ($)", tickprefix="$", tickformat=",.2f"),
    ),
)

maidr.show(fig)
