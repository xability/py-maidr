#!/usr/bin/env python3
"""
Example of creating a multipanel plot with seaborn.

This script demonstrates how to create a figure with multiple panels
containing different types of plots using seaborn: line plot, bar plot, and box plot.
"""

from typing import List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

# import maidr

# Set the plotting style
sns.set_theme(style="whitegrid")


def generate_line_data(n: int = 100000) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate large line-plot dataset.

    Parameters
    ----------
    n : int
        Number of data points.

    Returns
    -------
    x : np.ndarray
        Equally spaced X values.
    y : np.ndarray
        Sinusoidal Y values with noise.

    Examples
    --------
    >>> x, y = generate_line_data(1000)
    """
    x = np.linspace(0, 10, n)
    y = np.sin(x) + np.random.randn(n) * 0.1
    return x, y


def generate_bar_data(
    n: int = 100000, categories: Optional[List[str]] = None
) -> Tuple[List[str], np.ndarray]:
    """
    Generate counts per category for bar plot.

    Parameters
    ----------
    n : int
        Total number of samples.
    categories : list of str, optional
        Category labels (default A–E).

    Returns
    -------
    categories : list of str
        Category names.
    counts : np.ndarray
        Frequency counts for each category.

    Examples
    --------
    >>> cats, counts = generate_bar_data(5000, ['A','B','C'])
    """
    if categories is None:
        categories = [chr(ord("A") + i) for i in range(5)]
    data = np.random.choice(categories, size=n)
    counts = np.array([np.sum(data == cat) for cat in categories])
    return categories, counts


def generate_box_data(
    n: int = 100000, categories: Optional[List[str]] = None
) -> Tuple[List[str], List[np.ndarray]]:
    """
    Generate values for box plot per category.

    Parameters
    ----------
    n : int
        Total number of samples.
    categories : list of str, optional
        Category labels (default A–E).

    Returns
    -------
    categories : list of str
        Category names.
    values_list : list of np.ndarray
        One array of values per category.

    Examples
    --------
    >>> cats, vals = generate_box_data(5000, ['A','B'])
    """
    if categories is None:
        categories = [chr(ord("A") + i) for i in range(5)]
    size = n // len(categories)
    values_list = [np.random.randn(size) for _ in categories]
    return categories, values_list


def test():
    # Data for line plot
    x_line, y_line = generate_line_data()
    line_data = {"x": x_line, "y": y_line}

    # Data for bar plot
    categories, values = generate_bar_data()
    bar_data = {"categories": categories, "values": values}

    # Generate box plot data
    categories_box, box_values = generate_box_data()

    # Create a figure with 3 subplots arranged vertically
    fig, axs = plt.subplots(3, 1, figsize=(10, 12))

    # First panel: Line plot using seaborn
    sns.lineplot(x="x", y="y", data=line_data, color="blue", linewidth=2, ax=axs[0])
    axs[0].set_title("Line Plot: Random Data")
    axs[0].set_xlabel("X-axis")
    axs[0].set_ylabel("Values")

    # Second panel: Bar plot using seaborn
    sns.barplot(
        x="categories", y="values", data=bar_data, color="green", alpha=0.7, ax=axs[1]
    )
    axs[1].set_title("Bar Plot: Random Values")
    axs[1].set_xlabel("Categories")
    axs[1].set_ylabel("Values")

    # Third panel: Box plot
    axs[2].boxplot(box_values, labels=categories_box, vert=True)
    axs[2].set_title("Box Plot: Category Distribution")
    axs[2].set_xlabel("Categories")
    axs[2].set_ylabel("Values")

    # Adjust layout to prevent overlap
    plt.tight_layout()

    # Display the figure
    # maidr.show(fig)
