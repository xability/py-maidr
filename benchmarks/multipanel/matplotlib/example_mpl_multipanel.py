#!/usr/bin/env python3
"""
Example of creating a multipanel plot with matplotlib.

This script demonstrates how to create a figure with multiple panels
containing different types of plots: line plot, bar plot, and box plot.
"""

from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np

# import maidr


def generate_line_data(n: int = 100000) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate line plot data.

    Parameters
    ----------
    n : int
        Number of data points.

    Returns
    -------
    x : np.ndarray
        Equally spaced X values.
    y : np.ndarray
        Sinusoidal Y values with added noise.

    Examples
    --------
    >>> x, y = generate_line_data(1000)
    """
    x = np.linspace(0, 10, n)
    y = np.sin(x) + np.random.randn(n) * 0.1
    return x, y


def generate_bar_data(
    n: int = 100000, categories: List[str] = None
) -> Tuple[List[str], np.ndarray]:
    """
    Generate bar plot counts for categories.

    Parameters
    ----------
    n : int
        Total number of data points.
    categories : list of str, optional
        Category labels (default A–E).

    Returns
    -------
    categories : list of str
        Category names.
    values : np.ndarray
        Counts per category.

    Examples
    --------
    >>> cats, vals = generate_bar_data(1000, ['A','B'])
    """
    if categories is None:
        categories = [chr(ord("A") + i) for i in range(5)]
    data = np.random.choice(categories, size=n)
    values = np.array([np.sum(data == cat) for cat in categories])
    return categories, values


def generate_box_data(
    n: int = 100000, categories: List[str] = None
) -> List[np.ndarray]:
    """
    Generate box plot data for categories.

    Parameters
    ----------
    n : int
        Total number of data points.
    categories : list of str, optional
        Category labels (default A–E).

    Returns
    -------
    box_values : list of np.ndarray
        Values per category.

    Examples
    --------
    >>> box_vals = generate_box_data(1000, ['A','B'])
    """
    if categories is None:
        categories = [chr(ord("A") + i) for i in range(5)]
    size_per_cat = n // len(categories)
    return [np.random.randn(size_per_cat) for _ in categories]


def test() -> None:
    """
    Generate datasets and create a multipanel plot.
    """
    # Generate synthetic datasets
    x_line, y_line = generate_line_data()
    categories, bar_values = generate_bar_data()
    box_values = generate_box_data()

    # Create figure with 3 vertical subplots
    fig, axs = plt.subplots(3, 1, figsize=(10, 12))

    # Line plot
    axs[0].plot(x_line, y_line, color="blue", linewidth=2)
    axs[0].set_title("Line Plot: Large Dataset")
    axs[0].set_xlabel("X-axis")
    axs[0].set_ylabel("Values")
    axs[0].grid(True, linestyle="--", alpha=0.7)

    # Bar plot
    axs[1].bar(categories, bar_values, color="green", alpha=0.7)
    axs[1].set_title("Bar Plot: Category Counts")
    axs[1].set_xlabel("Categories")
    axs[1].set_ylabel("Counts")

    # Box plot
    axs[2].boxplot(box_values, labels=categories, vert=True)
    axs[2].set_title("Box Plot: Category Distribution")
    axs[2].set_xlabel("Categories")
    axs[2].set_ylabel("Values")

    plt.tight_layout()
    # maidr.show(fig)
