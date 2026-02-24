import altair as alt
import seaborn as sns

import maidr

# Load the flights dataset from seaborn
flights = sns.load_dataset("flights")

# Calculate total passengers per year
flights_yearly = flights.groupby("year")["passengers"].sum().reset_index()
flights_yearly.columns = ["year", "total"]

# Create a line plot of total passengers per year
line_plot = (
    alt.Chart(flights_yearly)
    .mark_line(point=True)
    .encode(
        x=alt.X("year:O", title="Year"),
        y=alt.Y("total:Q", title="Total Passengers (Thousands)"),
    )
    .properties(
        title="Total Passengers per Year\nFrom the Flights Dataset",
        width=500,
        height=300,
    )
)

maidr.show(line_plot)
