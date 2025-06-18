import numpy as np
import matplotlib.pyplot as plt
from statsmodels.nonparametric.smoothers_lowess import lowess
import maidr

# Generate synthetic data
np.random.seed(0)
x = np.linspace(0, 10, 100)
y = np.sin(x) + 0.3 * np.random.randn(100)

# LOWESS smoothing
smoothed = lowess(y, x, frac=0.3)  # frac controls the amount of smoothing

fig, ax = plt.subplots(figsize=(6, 4))
ax.scatter(x, y, color="blue", alpha=0.6, label="Data points")
# Plot the smooth (LOWESS) line
ax.plot(smoothed[:, 0], smoothed[:, 1], color="red", lw=2, label="LOWESS smooth")

ax.set_xlabel("x")
ax.set_ylabel("y")
ax.set_title("Matplotlib: Scatter with LOWESS Smooth Line")
ax.legend()
plt.tight_layout()

# Show with MAIDR (if available)
maidr.show(ax)
