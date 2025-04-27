from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import maidr

# To use maidr's typescript build set the following command to use maidr ts
# maidr.set_engine("ts")


def generate_large_dataset(
    size: int = 10000, num_categories: int = 100
) -> pd.DataFrame:
    """
    Generate a synthetic dataset with specified number of categories.

    Parameters
    ----------
    size : int, optional
        Number of data points to generate, by default 10000
    num_categories : int, optional
        Number of unique categories to generate, by default 100

    Returns
    -------
    pd.DataFrame
        DataFrame containing random category assignments

    Examples
    --------
    >>> df = generate_large_dataset(1000, 50)
    >>> df.shape
    (1000, 1)
    >>> len(df['category'].unique())
    50
    """
    # Create category labels (Cat_1, Cat_2, ..., Cat_100)
    categories = [f"Cat_{i+1}" for i in range(num_categories)]

    # Generate varying weights for categories to create more realistic distribution
    # Using exponential distribution to make some categories more common than others
    raw_weights = np.random.exponential(0.5, size=num_categories)
    # Normalize to make the weights sum to 1
    weights = raw_weights / raw_weights.sum()

    # Generate random category values
    random_categories = np.random.choice(categories, size=size, p=weights)

    # Create random values for each category (simulating measurements)
    random_values = np.random.normal(500, 100, size=size)

    # Create DataFrame
    return pd.DataFrame({"category": random_categories, "value": random_values})


def create_category_count_plot(
    data: pd.DataFrame,
) -> Tuple[plt.Figure, sns.FacetGrid]:
    """
    Create a bar plot showing the count of each category in the dataset using Seaborn.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing 'category' and 'value' columns

    Returns
    -------
    Tuple[plt.Figure, sns.FacetGrid]
        Figure and Seaborn plot object
    """
    # Create figure
    fig = plt.figure(figsize=(15, 10))

    # Create aggregated data for plotting
    agg_data = data.groupby("category")["value"].mean().reset_index()
    agg_data = agg_data.sort_values("category")

    # Create the bar plot using Seaborn
    ax = sns.barplot(
        x="category",
        y="value",
        data=agg_data,
        errorbar=None,  # No error bars for performance with large datasets
    )

    # Add title and labels
    plt.title("Distribution Across 100 Categories (10,000 Data Points)")
    plt.xlabel("Category")
    plt.ylabel("Average Value")

    # Improve x-axis readability
    plt.xticks(rotation=90, fontsize=8)
    plt.tick_params(axis="x", which="major", pad=5)

    # Adjust layout to make room for rotated labels
    plt.tight_layout()

    return fig, ax


def test():
    # Generate dataset with 10,000 data points across 100 categories
    large_dataset = generate_large_dataset(100000, 5)

    # Create and display the bar plot
    fig, b_plot = create_category_count_plot(large_dataset)
