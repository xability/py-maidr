import plotly.graph_objects as go
import seaborn as sns

import maidr

# Load the flights dataset from seaborn
flights = sns.load_dataset("flights")

# Pivot the dataset and compute total passengers per year
flights_wide = flights.pivot(index="year", columns="month", values="passengers")
flights_wide["Total"] = flights_wide.sum(axis=1)
flights_wide.reset_index(inplace=True)

# Plot the total number of passengers per year
fig = go.Figure(
    data=[
        go.Scatter(
            x=flights_wide["year"].tolist(),
            y=flights_wide["Total"].tolist(),
            mode="lines",
            name="Total Passengers",
        )
    ],
    layout=go.Layout(
        title="Total Passengers per Year",
        xaxis=dict(title="Year"),
        yaxis=dict(title="Total Passengers (Thousands)", tickformat=",.0f"),
    ),
)

maidr.show(fig)
