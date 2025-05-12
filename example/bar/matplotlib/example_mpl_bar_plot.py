import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load dataset
tips = sns.load_dataset("tips")

# Create a bar plot
cut_counts = tips["day"].value_counts()
plt.figure(figsize=(10, 6))
b_plot = plt.bar(cut_counts.index, list(cut_counts.values), color="skyblue")
plt.title("The Number of Tips by Day")
plt.xlabel("Day")
plt.ylabel("Count")

# plt.show()
maidr.show(b_plot)
