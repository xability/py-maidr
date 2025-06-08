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

# --- Seaborn regplot example with regression line ---
# Create a regplot with a regression line (and optionally lowess smoothing)
regplot = sns.regplot(
    data=iris,
    x="sepal_length",
    y="sepal_width",
    lowess=True,
    scatter_kws={"color": "gray"},
    line_kws={"color": "red"},
)
plt.title("Iris Sepal Length vs Sepal Width with Regression Line (LOWESS)")
plt.xlabel("Sepal Length")
plt.ylabel("Sepal Width")

# Show the plot
# plt.show()
maidr.show(regplot)

# --- Seaborn regplot example WITHOUT regression line ---
# Create a regplot with only scatter points (no regression line)
regplot_no_line = sns.regplot(
    data=iris,
    x="sepal_length",
    y="sepal_width",
    fit_reg=False,
    scatter_kws={"color": "green"},
)
plt.title("Iris Sepal Length vs Sepal Width (No Regression Line)")
plt.xlabel("Sepal Length")
plt.ylabel("Sepal Width")

# Show the plot
# plt.show()
maidr.show(regplot_no_line)
