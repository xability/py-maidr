import matplotlib.pyplot as plt
import numpy as np

import maidr

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

# Generate sample data
x = np.arange(5)
bar_data = np.array([3, 5, 2, 7, 3])
line_data = np.array([10, 8, 12, 14, 9])

# Create a figure and a set of subplots
fig, ax1 = plt.subplots(figsize=(8, 5))

# Create the bar chart on the first y-axis
ax1.bar(x, bar_data, color="skyblue", label="Bar Data")
ax1.set_xlabel("X values")
ax1.set_ylabel("Bar values", color="blue")
ax1.tick_params(axis="y", labelcolor="blue")

# Create a second y-axis sharing the same x-axis
ax2 = ax1.twinx()

# Create the line chart on the second y-axis
ax2.plot(x, line_data, color="red", marker="o", linestyle="-", label="Line Data")
ax2.set_xlabel("X values")
ax2.set_ylabel("Line values", color="red")
ax2.tick_params(axis="y", labelcolor="red")

# Add title and legend
plt.title("Multilayer Plot Example")

# Add legends for both axes
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

# Adjust layout
fig.tight_layout()

maidr.show(fig)
