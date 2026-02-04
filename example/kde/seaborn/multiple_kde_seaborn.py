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

fig, ax = plt.subplots(figsize=(8, 5))

# Plot multiple KDEs with explicit, accessible labels
sns.kdeplot(data1, label="Group 1 KDE", color="blue", linewidth=2, ax=ax)
sns.kdeplot(data2, label="Group 2 KDE", color="green", linewidth=2, ax=ax)
sns.kdeplot(data3, label="Group 3 KDE", color="red", linewidth=2, ax=ax)

ax.set_title("Multiple KDE Plots with Seaborn")
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
