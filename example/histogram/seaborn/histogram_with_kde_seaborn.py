"""
Histogram with KDE overlay using Seaborn
-----------------------------------------
This example demonstrates how to overlay a kernel density estimate (KDE) on a histogram using Seaborn.
It uses MAIDR integration for interactive accessibility.
"""

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import maidr  # MAIDR integration

# Generate sample data (e.g., normally distributed data)
np.random.seed(0)
data = np.random.normal(loc=0, scale=1, size=200)

# Create a figure and axis
fig, ax = plt.subplots(figsize=(8, 5))

# Plot histogram with KDE overlay using Seaborn (using stat='density' so that the histogram integrates to 1)
sns.histplot(
    data,
    bins=20,
    stat="density",
    alpha=0.6,
    color="blue",
    label="Histogram",
    kde=True,
    ax=ax,
)

ax.set_title("Histogram with KDE Overlay (Seaborn)")
ax.set_xlabel("Value")
ax.set_ylabel("Density")
ax.legend(title="Legend")
plt.tight_layout()

# Show with MAIDR for interactive accessibility
maidr.show(fig)
