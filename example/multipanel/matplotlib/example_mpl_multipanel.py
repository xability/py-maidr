#!/usr/bin/env python3
"""
Example of creating a multipanel plot with matplotlib.

This script demonstrates how to create a figure with multiple panels
containing different types of plots: line plot, bar plot, and scatter plot.
"""

import matplotlib.pyplot as plt
import numpy as np

import maidr

x_line = np.array([1, 2, 3, 4, 5, 6, 7, 8])
y_line = np.array([2, 4, 1, 5, 3, 7, 6, 8])

# Data for bar plot
categories = ["A", "B", "C", "D", "E"]
values = np.random.rand(5) * 10

# Data for bar plot
categories_2 = ["A", "B", "C", "D", "E"]
values_2 = np.random.randn(5) * 100

# Data for scatter plot
x_scatter = np.random.randn(50)
y_scatter = np.random.randn(50)

# Create a figure with 3 subplots arranged vertically
fig, axs = plt.subplots(3, 1, figsize=(10, 12))

# First panel: Line plot
axs[0].plot(x_line, y_line, color="blue", linewidth=2)
axs[0].set_title("Line Plot: Random Data")
axs[0].set_xlabel("X-axis")
axs[0].set_ylabel("Values")
axs[0].grid(True, linestyle="--", alpha=0.7)

# Second panel: Bar plot
axs[1].bar(categories, values, color="green", alpha=0.7)
axs[1].set_title("Bar Plot: Random Values")
axs[1].set_xlabel("Categories")
axs[1].set_ylabel("Values")

# Third panel: Bar plot
axs[2].bar(categories_2, values_2, color="blue", alpha=0.7)
axs[2].set_title("Bar Plot 2: Random Values")
axs[2].set_xlabel("Categories")
axs[2].set_ylabel("Values")

# Adjust layout to prevent overlap
plt.tight_layout()

# Display the figure
maidr.show(fig)
