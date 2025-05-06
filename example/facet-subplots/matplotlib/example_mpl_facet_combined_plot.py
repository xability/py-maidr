#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example of creating a facet plot with matplotlib that has shared axes.
One column contains line plots and another contains bar plots.
"""

from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np

import maidr


def generate_simple_data(
    num_rows: int = 3, num_points: int = 5
) -> Tuple[np.ndarray, List[np.ndarray], List[np.ndarray]]:
    """
    Generate simple data for line and bar plots.

    Parameters
    ----------
    num_rows : int, optional
        Number of rows (facets) to generate data for, by default 3
    num_points : int, optional
        Number of data points per plot, by default 5

    Returns
    -------
    Tuple[np.ndarray, List[np.ndarray], List[np.ndarray]]
        A tuple containing:
        - x values common for all plots
        - list of y values for line plots
        - list of y values for bar plots

    Examples
    --------
    >>> x, line_data, bar_data = generate_simple_data(2, 5)
    >>> len(line_data)
    2
    """
    # Generate x values common to both plot types
    x = np.arange(num_points)

    # Generate line plot data with different linear trends
    line_data = []
    for i in range(num_rows):
        # Create a simple linear trend with different slopes
        y = np.random.rand(5) * 10
        line_data.append(y)

    # Generate bar plot data with different patterns
    bar_data = []
    for i in range(num_rows):
        # Create simple bar heights
        y = np.abs(np.sin(x + i) * 5) + i
        bar_data.append(y)

    return x, line_data, bar_data


def create_facet_plot(
    x: np.ndarray, line_data: List[np.ndarray], bar_data: List[np.ndarray]
) -> Tuple[plt.Figure, np.ndarray]:  # type: ignore
    """
    Create a facet plot with one column of line plots and one column of bar plots.

    Parameters
    ----------
    x : np.ndarray
        The x-values for all plots
    line_data : List[np.ndarray]
        List of y-values for the line plots, one array per row
    bar_data : List[np.ndarray]
        List of y-values for the bar plots, one array per row

    Returns
    -------
    Tuple[plt.Figure, np.ndarray]
        The figure and axes objects
    """
    num_rows = len(line_data)

    # Create a figure with a 2-column grid of subplots
    fig, axs = plt.subplots(num_rows, 2, figsize=(10, 3 * num_rows), sharey="row")

    # Loop through each row to create the facet plots
    for row in range(num_rows):
        # Left column: line plot
        axs[row, 0].plot(x, line_data[row], "o-", linewidth=2, color=f"C{row}")
        axs[row, 0].set_title(f"Line Plot {row+1}")

        # Right column: bar plot
        axs[row, 1].bar(x, bar_data[row], color=f"C{row}", alpha=0.7)
        axs[row, 1].set_title(f"Bar Plot {row+1}")

        # Add a y-axis label only on the left column
        axs[row, 0].set_ylabel(f"Values (Row {row+1})")

    # Add x-labels to the bottom row only
    for col in range(2):
        axs[-1, col].set_xlabel("X Values")

    # Add a global title
    fig.suptitle("Facet Plot Example with Shared Y-Axes", fontsize=16, y=0.98)

    # Adjust spacing between subplots
    plt.tight_layout()

    return fig, axs


x, line_data, bar_data = generate_simple_data(num_rows=3)

# Create and display the facet plot
fig, axs = create_facet_plot(x, line_data, bar_data)

maidr.show(fig)
