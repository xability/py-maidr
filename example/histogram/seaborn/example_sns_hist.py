import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")

# Select the petal lengths
petal_lengths = iris["petal_length"]

# Plot a histogram of the petal lengths
plt.figure(figsize=(10, 6))
hist_plot = sns.histplot(petal_lengths, kde=True, color="blue", binwidth=0.5)

plt.title("Histogram of Petal Lengths in Iris Dataset")
plt.xlabel("Petal Length (cm)")
plt.ylabel("Frequency")

# plt.show()
maidr.show(hist_plot)
