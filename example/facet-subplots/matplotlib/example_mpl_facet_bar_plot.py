#!/usr/bin/env python3
"""
Example of creating a facet plot with matplotlib.

This script demonstrates how to create a figure with multiple panels
containing bar plots that share the same axes, creating a facet plot.
Each panel represents data for a different category or condition.
"""

import matplotlib.pyplot as plt
import numpy as np

import maidr

categories = ["A", "B", "C", "D", "E"]

np.random.seed(42)
data_group1 = np.random.rand(5) * 10
data_group2 = np.random.rand(5) * 100
data_group3 = np.random.rand(5) * 36
data_group4 = np.random.rand(5) * 42

data_sets = [data_group1, data_group2, data_group3, data_group4]
condition_names = ["Group 1", "Group 2", "Group 3", "Group 4"]

fig, axs = plt.subplots(2, 2, figsize=(12, 10), sharey=True, sharex=True)
axs = axs.flatten()

all_data = np.concatenate(data_sets)
y_min, y_max = np.min(all_data) * 0.9, np.max(all_data) * 1.1

# Create a bar plot in each subplot
for i, (data, condition) in enumerate(zip(data_sets, condition_names)):
    axs[i].bar(categories, data, color=f"C{i}", alpha=0.7)
    axs[i].set_title(f"{condition}")
    axs[i].set_ylim(y_min, y_max)  # Set consistent y-axis limits

    # Add value labels on top of each bar
    for j, value in enumerate(data):
        axs[i].text(
            j,
            value + (y_max - y_min) * 0.02,
            f"{value:.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

# Add common labels
fig.text(0.5, 0.04, "Categories", ha="center", va="center", fontsize=14)
fig.text(
    0.06, 0.5, "Values", ha="center", va="center", rotation="vertical", fontsize=14
)

# Add a common title
fig.suptitle("Facet Plot: Bar Charts by Condition", fontsize=16)

# Adjust layout
plt.tight_layout(rect=(0.08, 0.08, 0.98, 0.95))

maidr.show(fig)
