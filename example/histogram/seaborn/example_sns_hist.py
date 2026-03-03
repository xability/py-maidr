import matplotlib.pyplot as plt
import seaborn as sns

import maidr

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
# X-axis: measurements in cm with one decimal
ax.xaxis.set_major_formatter("{x:.1f}")
# Y-axis: frequency counts as integers
ax.yaxis.set_major_formatter("{x:.0f}")

maidr.show(hist_plot)
