import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load an example dataset from seaborn
glue = sns.load_dataset("glue").pivot(index="Model", columns="Task", values="Score")

# Plot a heatmap
fig, ax = plt.subplots(figsize=(10, 8))
heatmap = sns.heatmap(glue, annot=True, fill_label="Score", ax=ax)
ax.set_title("Heatmap of Model Scores by Task")

# Add number formatter for colorbar for better screen reader output
cbar = heatmap.collections[0].colorbar
if cbar:
    cbar.ax.yaxis.set_major_formatter("{x:.1f}")  # Score values with one decimal

# Show the plot
# plt.show()
maidr.show(heatmap)
