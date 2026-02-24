"""
Example of creating a facet bar plot with Altair.

This script demonstrates how to create a figure with multiple panels
containing bar plots that share the same axes, creating a facet plot.
Each panel represents data for a different product category.
"""

import altair as alt
import pandas as pd

import maidr


def create_sample_data() -> pd.DataFrame:
    """
    Create a simple sample DataFrame for facet bar plotting.

    Returns
    -------
    pd.DataFrame
        A DataFrame with product categories, regions, and sales data.
    """
    data = {
        "category": [
            "Product1",
            "Product1",
            "Product1",
            "Product1",
            "Product2",
            "Product2",
            "Product2",
            "Product2",
            "Product3",
            "Product3",
            "Product3",
            "Product3",
        ],
        "region": ["North", "South", "East", "West"] * 3,
        "sales": [25, 18, 30, 22, 15, 29, 10, 24, 32, 17, 22, 35],
    }
    return pd.DataFrame(data)


# Create sample data
df = create_sample_data()

# Create a facet bar plot using Altair's row faceting
facet_plot = (
    alt.Chart(df)
    .mark_bar()
    .encode(
        x=alt.X("region:N", title="Region"),
        y=alt.Y("sales:Q", title="Sales"),
        color=alt.Color("region:N", legend=None),
    )
    .properties(width=300, height=150)
    .facet(row=alt.Row("category:N", title="Product Category"))
    .properties(title="Sales by Region for Different Products")
)

maidr.show(facet_plot)
