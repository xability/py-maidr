import matplotlib.pyplot as plt
import seaborn as sns

import maidr  # noqa: F401

# Load the dataset
iris = sns.load_dataset("iris")

# Choose a column for the histogram, for example, the 'petal_length'
data = iris["petal_length"]

# Create the histogram plot
fig, ax = plt.subplots()
_, _, hist_plot = ax.hist(data, bins=20, edgecolor="black")
ax.set_title("Histogram of Petal Lengths in Iris Dataset")
ax.set_xlabel("Petal Length (cm)")
ax.set_ylabel("Frequency")

# Add number formatters for better screen reader output
# X-axis: the 20 bins are 0.295 cm wide, so three decimals print every bin
# edge as drawn (1.295, 1.590, ...); one would read 1.295 as 1.3
ax.xaxis.set_major_formatter("{x:.3f}")
# Y-axis: frequency counts as integers
ax.yaxis.set_major_formatter("{x:.0f}")

plt.show()
