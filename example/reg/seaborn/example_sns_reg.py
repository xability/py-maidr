import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")

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
