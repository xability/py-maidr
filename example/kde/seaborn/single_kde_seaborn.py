import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import maidr

# 1) Sample data
data = np.random.randn(500)

# 2) Plot the KDE curve
fig, ax = plt.subplots()
sns.kdeplot(data, ax=ax)
ax.set_xlabel("Value")
ax.set_ylabel("Density")
ax.set_title("Seaborn KDE Plot")

# Add number formatters for better screen reader output
# X-axis: values with one decimal
ax.xaxis.set_major_formatter("{x:.1f}")
# Y-axis: density values with three decimals
ax.yaxis.set_major_formatter("{x:.3f}")

plt.tight_layout()
maidr.show(ax)
