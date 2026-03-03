import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the Titanic dataset
titanic = sns.load_dataset("titanic")

# Create a countplot
fig, ax = plt.subplots()
count_plot = sns.countplot(x="class", data=titanic, ax=ax)

# Set the title
ax.set_title("Passenger Class Distribution on the Titanic")

# Add number formatter to y-axis for better screen reader output
# Count values as integers (no decimals)
ax.yaxis.set_major_formatter("{x:.0f}")

maidr.show(count_plot)
