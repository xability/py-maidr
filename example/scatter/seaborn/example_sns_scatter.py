import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")

# Create a scatter plot
scatter_plot = sns.scatterplot(
    data=iris, x="sepal_length", y="sepal_width", hue="species"
)

# Adding title and labels (optional)
plt.title("Iris Sepal Length vs Sepal Width")
plt.xlabel("Sepal Length")
plt.ylabel("Sepal Width")

# Show the plot
# plt.show()
maidr.show(scatter_plot)
