"""
Multiple KDE overlays with Matplotlib/Scipy and MAIDR
-----------------------------------------------------
This example demonstrates how to plot multiple kernel density estimates (KDEs) for different groups using
raw Matplotlib and Scipy, with MAIDR integration for interactive accessibility and exploration.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
import maidr  # MAIDR integration

# Generate sample data for three groups
np.random.seed(0)
data1 = np.random.normal(loc=0, scale=1, size=200)
data2 = np.random.normal(loc=2, scale=0.5, size=200)
data3 = np.random.normal(loc=-2, scale=1.5, size=200)

fig, ax = plt.subplots(figsize=(8, 5))

# Define x ranges for each group
x1 = np.linspace(data1.min() - 1, data1.max() + 1, 200)
x2 = np.linspace(data2.min() - 1, data2.max() + 1, 200)
x3 = np.linspace(data3.min() - 1, data3.max() + 1, 200)

# Compute KDEs
kde1 = gaussian_kde(data1)
kde2 = gaussian_kde(data2)
kde3 = gaussian_kde(data3)

# Plot KDEs with explicit, accessible labels
ax.plot(x1, kde1(x1), label="Group 1 KDE", color="blue", linewidth=2)
ax.plot(x2, kde2(x2), label="Group 2 KDE", color="green", linewidth=2)
ax.plot(x3, kde3(x3), label="Group 3 KDE", color="red", linewidth=2)

ax.set_title("Multiple KDE Plots with Matplotlib/Scipy")
ax.set_xlabel("Value")
ax.set_ylabel("Density")
ax.legend(title="Group")

# Add number formatters for better screen reader output
# X-axis: values with one decimal
ax.xaxis.set_major_formatter("{x:.1f}")
# Y-axis: density values with three decimals
ax.yaxis.set_major_formatter("{x:.3f}")

plt.tight_layout()

# Show with MAIDR for interactive accessibility
maidr.show(fig)
