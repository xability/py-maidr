"""
Example of creating a facet plot with Altair that combines bar plots and line plots.

This script demonstrates how to create a figure with multiple panels arranged
in a grid, where one row contains bar plots and another row contains line plots.
"""

import altair as alt
import numpy as np
import pandas as pd

import maidr


def create_sample_data() -> pd.DataFrame:
    """
    Creates a sample dataframe for demonstrating facet plots.

    Returns
    -------
    pd.DataFrame
        A dataframe with product categories, regions, time periods, and metrics.
    """
    categories = ["Electronics", "Clothing", "Home"]
    regions = ["North", "Central", "South"]
    years = [2020, 2021, 2022]
    quarters = [1, 2, 3, 4]

    rows = []
    np.random.seed(42)
    for cat in categories:
        base_sales = np.random.randint(100, 200)
        base_profit = np.random.randint(20, 40)

        for region in regions:
            region_factor = 1.0 + regions.index(region) * 0.1

            for year in years:
                year_factor = (year - 2019) * 0.1

                for quarter in quarters:
                    quarter_factor = 1.0 + (quarter - 2.5) * 0.05

                    sales = int(
                        base_sales
                        * region_factor
                        * (1 + year_factor)
                        * quarter_factor
                        * np.random.uniform(0.9, 1.1)
                    )
                    profit = int(
                        base_profit
                        * region_factor
                        * (1 + year_factor)
                        * quarter_factor
                        * np.random.uniform(0.9, 1.1)
                    )

                    rows.append(
                        {
                            "Category": cat,
                            "Region": region,
                            "Year": year,
                            "Quarter": quarter,
                            "Sales": sales,
                            "Profit": profit,
                        }
                    )

    return pd.DataFrame(rows)


# Generate sample data
df = create_sample_data()

# --- BAR PLOTS: Average sales by category, faceted by region ---
bar_data = df.groupby(["Category", "Region"])["Sales"].mean().reset_index()

bar_charts = (
    alt.Chart(bar_data)
    .mark_bar()
    .encode(
        x=alt.X("Category:N", title="Category"),
        y=alt.Y("Sales:Q", title="Avg Sales"),
        color=alt.Color("Category:N", legend=None),
    )
    .properties(width=200, height=200)
    .facet(column=alt.Column("Region:N", title="Region"))
    .properties(title="Average Sales by Product Category and Region")
)

# --- LINE PLOTS: Profit trends over time, faceted by category ---
line_data = (
    df.groupby(["Category", "Year", "Quarter"])
    .agg({"Profit": "mean"})
    .reset_index()
)
line_data["TimePoint"] = line_data["Year"] + (line_data["Quarter"] - 1) / 4

line_charts = (
    alt.Chart(line_data)
    .mark_line(point=True)
    .encode(
        x=alt.X("TimePoint:Q", title="Year", axis=alt.Axis(format=".0f")),
        y=alt.Y("Profit:Q", title="Avg Profit"),
    )
    .properties(width=200, height=200)
    .facet(column=alt.Column("Category:N", title="Category"))
    .properties(title="Profit Trends by Product Category Over Time")
)

# Vertically concatenate the two faceted rows
chart = alt.vconcat(bar_charts, line_charts).properties(
    title="Combined Facet Plots: Sales Distribution and Profit Trends"
)

maidr.show(chart)
