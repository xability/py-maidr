import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")

# Create a scatter plot
fig, ax = plt.subplots()
scatter_plot = sns.scatterplot(
    data=iris, x="sepal_length", y="sepal_width", hue="species", ax=ax
)

# Adding title and labels
ax.set_title("Iris Sepal Length vs Sepal Width")
ax.set_xlabel("Sepal Length (cm)")
ax.set_ylabel("Sepal Width (cm)")

# Add number formatters for better screen reader output
# Measurements in cm with one decimal
ax.xaxis.set_major_formatter("{x:.1f}")
ax.yaxis.set_major_formatter("{x:.1f}")

maidr.show(scatter_plot)
