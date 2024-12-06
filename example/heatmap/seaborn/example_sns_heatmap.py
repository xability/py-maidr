import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load an example dataset from seaborn
glue = sns.load_dataset("glue").pivot(index="Model", columns="Task", values="Score")

# Plot a heatmap
plt.figure(figsize=(10, 8))
heatmap = sns.heatmap(glue, annot=True, fill_label="Score")
plt.title("Heatmap of Model Scores by Task")

# Show the plot
# plt.show()
maidr.show(heatmap)
