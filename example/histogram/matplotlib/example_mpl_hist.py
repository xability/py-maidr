import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the dataset
iris = sns.load_dataset("iris")

# Choose a column for the histogram, for example, the 'petal_length'
data = iris["petal_length"]

# Create the histogram plot
_, _, hist_plot = plt.hist(data, bins=20, edgecolor="black")
plt.title("Histogram of Petal Lengths in Iris Dataset")
plt.xlabel("Petal Length (cm)")
plt.ylabel("Frequency")

# plt.show()
maidr.show(hist_plot)
