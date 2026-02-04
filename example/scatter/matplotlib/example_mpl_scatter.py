import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")

# Plot sepal_length vs sepal_width
fig, ax = plt.subplots(figsize=(10, 6))
scatter_plot = ax.scatter(
    iris["sepal_length"], iris["sepal_width"], c="blue", label="Iris Data Points"
)
ax.set_title("Iris Dataset: Sepal Length vs Sepal Width")
ax.set_xlabel("Sepal Length (cm)")
ax.set_ylabel("Sepal Width (cm)")
ax.legend()

# Add number formatters for better screen reader output
# Measurements in cm with one decimal
ax.xaxis.set_major_formatter("{x:.1f}")
ax.yaxis.set_major_formatter("{x:.1f}")

maidr.show(scatter_plot)
