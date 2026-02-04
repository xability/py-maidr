"""
Single KDE Plot with Matplotlib/Scipy and MAIDR
------------------------------------------------
This example demonstrates how to plot a single kernel density estimate (KDE)
using raw Matplotlib and Scipy, with MAIDR integration for interactive
accessibility and exploration.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
import maidr

# Generate sample data
np.random.seed(42)
data = np.random.normal(loc=1, scale=2, size=300)

fig, ax = plt.subplots(figsize=(8, 5))

# Define x range for the plot
x = np.linspace(data.min() - 2, data.max() + 2, 200)

# Compute KDE
kde = gaussian_kde(data)

# Plot single KDE
ax.plot(x, kde(x), label="Sample Data KDE", color="blue", linewidth=2)

ax.set_title("Single KDE Plot with Matplotlib/Scipy")
ax.set_xlabel("Value")
ax.set_ylabel("Density")
ax.legend()
ax.grid(True, alpha=0.3)

# Add number formatters for better screen reader output
# X-axis: values with one decimal
ax.xaxis.set_major_formatter("{x:.1f}")
# Y-axis: density values with three decimals
ax.yaxis.set_major_formatter("{x:.3f}")

plt.tight_layout()

# Show with MAIDR for interactive accessibility
maidr.show(fig)
