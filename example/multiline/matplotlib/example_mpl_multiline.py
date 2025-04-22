import matplotlib.pyplot as plt
import numpy as np

import maidr

"""
Creates a multiline plot showing basic data trends.

The plot displays three different data series with discrete points
connected by lines of different styles and colors.

Returns
-------
None
"""

# Create sample data points
x = np.array([1, 2, 3, 4, 5, 6, 7, 8])
y1 = np.array([2, 4, 1, 5, 3, 7, 6, 8])
y2 = np.array([1, 3, 5, 2, 4, 6, 8, 7])
y3 = np.array([3, 1, 4, 6, 5, 2, 4, 5])

# Create the plot
plt.figure(figsize=(10, 6))

# Plot multiple lines with different styles and markers
lineplot = plt.plot(x, y1, "bo-", linewidth=2, markersize=8)
lineplot = plt.plot(x, y2, "rs--", linewidth=2, markersize=8)
lineplot = plt.plot(x, y3, "g^:", linewidth=2, markersize=8)

# lineplot = plt.plot(x, y1, "bo-", label="Series 1", linewidth=2, markersize=8)

# Customize the plot
plt.title("Basic Multiline Plot")
plt.xlabel("X values")
plt.ylabel("Y values")
plt.legend()

# Display the plot
# plt.show()
maidr.show(lineplot)
