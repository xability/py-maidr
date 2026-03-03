import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import maidr

np.random.seed(0)
x = np.linspace(0, 10, 100)
y = np.sin(x) + 0.3 * np.random.randn(100)

fig, ax = plt.subplots(figsize=(6, 4))
plot = sns.regplot(
    x=x,
    y=y,
    lowess=True,
    scatter_kws={"s": 30, "alpha": 0.6},
    line_kws={"color": "red", "lw": 2},
    ax=ax,
)

ax.set_xlabel("x")
ax.set_ylabel("y")
ax.set_title("Scatterplot with LOESS (Seaborn)")

# Add number formatters for better screen reader output
ax.xaxis.set_major_formatter("{x:.1f}")
ax.yaxis.set_major_formatter("{x:.2f}")

plt.tight_layout()

# Show the plot using maidr instead of plt.show()
maidr.show(plot)
