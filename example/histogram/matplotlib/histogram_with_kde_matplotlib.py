"""
Histogram with KDE overlay using Matplotlib and Scipy
-----------------------------------------------------
This example demonstrates how to overlay a kernel density estimate (KDE) on a histogram using raw Matplotlib and Scipy.
It uses MAIDR integration for interactive accessibility.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
import maidr  # MAIDR integration

# Generate sample data (e.g., normally distributed data)
np.random.seed(0)
data = np.random.normal(loc=0, scale=1, size=200)

# Create a figure and axis
fig, ax = plt.subplots(figsize=(8, 5))

# Plot histogram (using density=True so that the histogram integrates to 1)
ax.hist(data, bins=20, density=True, alpha=0.6, color="blue", label="Histogram")

# Compute KDE using scipy.stats.gaussian_kde
kde = gaussian_kde(data)
x_range = np.linspace(data.min() - 1, data.max() + 1, 200)
ax.plot(x_range, kde(x_range), color="red", linewidth=2, label="KDE")

ax.set_title("Histogram with KDE Overlay (Matplotlib)")
ax.set_xlabel("Value")
ax.set_ylabel("Density")
ax.legend(title="Legend")
plt.tight_layout()

# Show with MAIDR for interactive accessibility
maidr.show(fig)
