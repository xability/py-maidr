import os

import matplotlib.pyplot as plt
import numpy as np  # added for synthetic data generation
import pandas as pd  # added for DataFrame handling
import seaborn as sns


def get_filepath(filename: str) -> str:
    """Get absolute path for a given filename in the current directory.

    Parameters
    ----------
    filename : str
        Filename to locate.

    Returns
    -------
    str
        Absolute path to the file.
    """
    current_file_path = os.path.abspath(__file__)
    directory = os.path.dirname(current_file_path)
    return os.path.join(directory, filename)


def plot() -> plt.Axes:
    """Generate and plot a stacked bar chart for synthetic data.

    Creates a dataset with 5 categories and 100000 data points per category,
    assigns a random binary outcome for stacking, and plots the counts.

    Returns
    -------
    matplotlib.axes.Axes
        Axes object of the stacked bar chart.

    Examples
    --------
    >>> ax = plot()
    >>> ax.legend()
    """
    # Generate synthetic dataset
    num_per_cat = 100_000
    categories = [f"Category_{i}" for i in range(1, 6)]
    outcomes = np.random.choice([0, 1], size=num_per_cat * len(categories))
    cat_array = np.repeat(categories, num_per_cat)
    df = pd.DataFrame({"category": cat_array, "outcome": outcomes})

    # Group by category and outcome, then count occurrences
    grouped = df.groupby(["category", "outcome"]).size().unstack(fill_value=0)

    # Plot stacked bar chart
    ax = grouped.plot(kind="bar", stacked=True)
    ax.set_title("Count by Category with Binary Outcome (Stacked)")
    ax.set_xlabel("Category")
    ax.set_ylabel("Count")
    ax.set_xticklabels(categories, rotation=0)

    return ax


def test() -> None:
    """Execute the stacked bar plot example and display with maidr."""
    stacked = plot()
