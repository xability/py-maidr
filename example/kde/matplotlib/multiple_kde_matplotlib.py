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

plt.figure(figsize=(8, 5))

# Define x ranges for each group
x1 = np.linspace(data1.min() - 1, data1.max() + 1, 200)
x2 = np.linspace(data2.min() - 1, data2.max() + 1, 200)
x3 = np.linspace(data3.min() - 1, data3.max() + 1, 200)

# Compute KDEs
kde1 = gaussian_kde(data1)
kde2 = gaussian_kde(data2)
kde3 = gaussian_kde(data3)

# Plot KDEs with explicit, accessible labels
plt.plot(x1, kde1(x1), label="Group 1 KDE", color="blue", linewidth=2)
plt.plot(x2, kde2(x2), label="Group 2 KDE", color="green", linewidth=2)
plt.plot(x3, kde3(x3), label="Group 3 KDE", color="red", linewidth=2)

plt.title("Multiple KDE Plots with Matplotlib/Scipy")
plt.xlabel("Value")
plt.ylabel("Density")
plt.legend(title="Group")
plt.tight_layout()

# Show with MAIDR for interactive accessibility
maidr.show(plt.gcf())
