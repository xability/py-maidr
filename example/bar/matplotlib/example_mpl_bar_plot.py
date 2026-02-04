import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load dataset
tips = sns.load_dataset("tips")

# Create a bar plot
cut_counts = tips["day"].value_counts()
fig, ax = plt.subplots(figsize=(10, 6))
b_plot = ax.bar(cut_counts.index, list(cut_counts.values), color="skyblue")
ax.set_title("The Number of Tips by Day")
ax.set_xlabel("Day")
ax.set_ylabel("Count")

# Add number formatter to y-axis for better screen reader output
# This formats values with no decimal places (integer counts)
ax.yaxis.set_major_formatter("{x:.2f}")

maidr.show(b_plot)
