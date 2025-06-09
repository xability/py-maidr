import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import maidr

np.random.seed(0)
x = np.linspace(0, 10, 100)
y = np.sin(x) + 0.3 * np.random.randn(100)

plt.figure(figsize=(6, 4))
plot = sns.regplot(
    x=x,
    y=y,
    lowess=True,
    scatter_kws={"s": 30, "alpha": 0.6},
    line_kws={"color": "red", "lw": 2},
)

plt.xlabel("x")
plt.ylabel("y")
plt.title("Scatterplot with LOESS (Seaborn)")
plt.tight_layout()

# Show the plot using maidr instead of plt.show()
maidr.show(plot)
