#!/usr/bin/env python3
"""
Example of creating a multipanel plot with seaborn.

This script demonstrates how to create a figure with multiple panels
containing different types of plots using seaborn: line plot, bar plot, and bar plot.
"""

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

import maidr

# Set the plotting style
sns.set_theme(style="whitegrid")

# Data for line plot
x_line = np.array([1, 2, 3, 4, 5, 6, 7, 8])
y_line = np.array([2, 4, 1, 5, 3, 7, 6, 8])
line_data = {"x": x_line, "y": y_line}

# Data for first bar plot
categories = ["A", "B", "C", "D", "E"]
values = np.random.rand(5) * 10
bar_data = {"categories": categories, "values": values}

# Data for second bar plot
categories_2 = ["A", "B", "C", "D", "E"]
values_2 = np.random.randn(5) * 100
bar_data_2 = {"categories": categories_2, "values": values_2}

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

# Third panel: Bar plot using seaborn
sns.barplot(
    x="categories", y="values", data=bar_data_2, color="blue", alpha=0.7, ax=axs[2]
)
axs[2].set_title("Bar Plot 2: Random Values")  # Fixed the typo in the title
axs[2].set_xlabel("Categories")
axs[2].set_ylabel("Values")

# Adjust layout to prevent overlap
plt.tight_layout()

# Display the figure
maidr.show(fig)
