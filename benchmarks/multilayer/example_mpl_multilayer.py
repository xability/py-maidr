from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np

# import maidr

"""
Create a simple multilayer plot with a bar chart and a line chart.

Returns
-------
Tuple[plt.Figure, plt.Axes]
    The figure and axes objects of the created plot.

Examples
--------
>>> fig, ax = create_multilayer_plot()
>>> isinstance(fig, plt.Figure)
True
"""


def create_multilayer_plot() -> Tuple[plt.Figure, plt.Axes]:
    """
    Create a multilayer plot with a bar chart (5 categories, 100k points)
    and a line chart (5 categories random points).

    Returns
    -------
    Tuple[plt.Figure, plt.Axes]
        The Matplotlib Figure and primary Axes.

    Examples
    --------
    >>> fig, ax = create_multilayer_plot()
    >>> isinstance(fig, plt.Figure)
    True
    """
    num_categories: int = 5
    num_points: int = 100000

    # generate random categories and aggregate counts for bar
    cats = np.random.randint(0, num_categories, size=num_points)
    bar_data = np.bincount(cats, minlength=num_categories)
    x_bar = np.arange(num_categories)

    # generate random line data over the same 5 categories
    x_line = x_bar
    line_data = np.random.randn(num_categories)

    # create figure and first axis
    fig, ax1 = plt.subplots(figsize=(8, 5))

    # plot bar chart
    ax1.bar(x_bar, bar_data, color="skyblue", label="Bar Data")
    ax1.set_xlabel("Category")
    ax1.set_ylabel("Count", color="blue")
    ax1.tick_params(axis="y", labelcolor="blue")
    ax1.set_xticks(x_bar)
    ax1.set_xticklabels([f"Cat {i+1}" for i in x_bar])

    # create second axis and plot line chart
    ax2 = ax1.twinx()
    ax2.plot(
        x_line,
        line_data,
        color="red",
        marker="o",
        linestyle="-",
        alpha=0.7,
        label="Line Data",
    )
    ax2.set_xlabel("Index")
    ax2.set_ylabel("Cumulative Sum", color="red")
    ax2.tick_params(axis="y", labelcolor="red")

    # title and combined legend
    fig.suptitle("Multilayer Plot with Large Datasets")
    l1, lab1 = ax1.get_legend_handles_labels()
    l2, lab2 = ax2.get_legend_handles_labels()
    ax1.legend(l1 + l2, lab1 + lab2, loc="upper left")

    fig.tight_layout()
    return fig, ax1


def test():
    fig, ax = create_multilayer_plot()
    # maidr.show(fig)
