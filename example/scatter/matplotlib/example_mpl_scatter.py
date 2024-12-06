import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")

# Plot sepal_length vs sepal_width
plt.figure(figsize=(10, 6))  # Optional: Sets the figure size
scatter_plot = plt.scatter(
    iris["sepal_length"], iris["sepal_width"], c="blue", label="Iris Data Points"
)
plt.title("Iris Dataset: Sepal Length vs Sepal Width")  # Title of the plot
plt.xlabel("Sepal Length (cm)")  # X-axis label
plt.ylabel("Sepal Width (cm)")  # Y-axis label
plt.legend()  # Shows the legend

# plt.show()
maidr.show(scatter_plot)
