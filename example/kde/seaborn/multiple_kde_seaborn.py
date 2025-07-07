"""
Multiple KDE overlays with Seaborn and MAIDR
--------------------------------------------
This example demonstrates how to plot multiple kernel density estimates (KDEs) for different groups using Seaborn,
with MAIDR integration for interactive accessibility and exploration.
"""

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import maidr  # MAIDR integration

# Generate sample data for three groups
np.random.seed(0)
data1 = np.random.normal(loc=0, scale=1, size=200)
data2 = np.random.normal(loc=2, scale=0.5, size=200)
data3 = np.random.normal(loc=-2, scale=1.5, size=200)

plt.figure(figsize=(8, 5))

# Plot multiple KDEs with explicit, accessible labels
sns.kdeplot(data1, label="Group 1 KDE", color="blue", linewidth=2)
sns.kdeplot(data2, label="Group 2 KDE", color="green", linewidth=2)
sns.kdeplot(data3, label="Group 3 KDE", color="red", linewidth=2)

plt.title("Multiple KDE Plots with Seaborn")
plt.xlabel("Value")
plt.ylabel("Density")
plt.legend(title="Group")
plt.tight_layout()

# Show with MAIDR for interactive accessibility
maidr.show(plt.gcf())
