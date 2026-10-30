import matplotlib.pyplot as plt
import seaborn as sns

import maidr  # noqa: F401

# Load the Iris dataset
iris = sns.load_dataset("iris")

# Select the petal lengths
petal_lengths = iris["petal_length"]

# Plot a histogram of the petal lengths
fig, ax = plt.subplots(figsize=(10, 6))
hist_plot = sns.histplot(petal_lengths, kde=True, color="blue", binwidth=0.5, ax=ax)

ax.set_title("Histogram of Petal Lengths in Iris Dataset")
ax.set_xlabel("Petal Length (cm)")
ax.set_ylabel("Frequency")

# Add number formatters for better screen reader output
# X-axis: two decimals, so each bin edge (1.49, 1.98, ...) reads within
# 0.005 cm of where it is drawn; one would read 1.49 as 1.5
ax.xaxis.set_major_formatter("{x:.2f}")
# Y-axis: frequency counts as integers
ax.yaxis.set_major_formatter("{x:.0f}")

plt.show()
