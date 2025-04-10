import matplotlib.pyplot as plt
import seaborn as sns

import maidr

maidr.set_engine("ts")

# Load the Titanic dataset
titanic = sns.load_dataset("titanic")

# Create a countplot
count_plot = sns.countplot(x="class", data=titanic)

# Set the title and show the plot
plt.title("Passenger Class Distribution on the Titanic")

# plt.show()
maidr.show(count_plot)
