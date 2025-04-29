from typing import Any, Dict, List

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

import maidr


def create_sample_data() -> pd.DataFrame:
    """
    Create a simple sample DataFrame for facet bar plotting.

    Returns
    -------
    pd.DataFrame
        A DataFrame with product categories, regions, and sales data.

    Examples
    --------
    >>> df = create_sample_data()
    >>> df.head()
       category region  sales
    0   Product1  North     25
    1   Product1  South     18
    2   Product1   East     30
    3   Product1   West     22
    4   Product2  North     15
    """
    # Define data for our example
    data: Dict[str, List[Any]] = {
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


def create_facet_bar_plot(data: pd.DataFrame) -> None:
    """
    Create a facet grid of bar plots with shared axis.

    Parameters
    ----------
    data : pd.DataFrame
        The DataFrame containing the data to plot.

    Examples
    --------
    >>> df = create_sample_data()
    >>> create_facet_bar_plot(df)
    """
    # Set the aesthetic style of the plots
    sns.set_theme(style="whitegrid")

    # Initialize the FacetGrid object with category as rows
    # This will create a separate subplot for each product category
    g = sns.FacetGrid(data, row="category", height=3, aspect=1.5, sharey=True)

    # Map a barplot using region as x and sales as y
    # This creates a bar plot for each category showing sales by region
    g.map_dataframe(sns.barplot, x="region", y="sales", palette="viridis")

    # Add titles and labels
    g.set_axis_labels("Region", "Sales")
    g.set_titles(row_template="{row_name}")

    # Adjust the layout and add a title
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    g.figure.suptitle("Sales by Region for Different Products", fontsize=16)

    # Show the plot
    maidr.show(g.figure)


# Create sample data
df = create_sample_data()

# Create and display the facet bar plot
create_facet_bar_plot(df)
