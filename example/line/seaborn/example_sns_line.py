import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the 'tips' dataset from seaborn
tips = sns.load_dataset("tips")

# Choose a specific subset of the dataset (e.g., data for 'Thursday')
subset_data = tips[tips["day"] == "Thur"]

# Create a line plot
fig, ax = plt.subplots(figsize=(10, 6))
line_plot = sns.lineplot(
    data=subset_data,
    x="total_bill",
    y="tip",
    markers=True,
    style="day",
    legend=False,
    ax=ax,
)
ax.set_title("Line Plot of Tips vs Total Bill (Thursday)")
ax.set_xlabel("Total Bill")
ax.set_ylabel("Tip")

# Add currency formatters for better screen reader output
# Both axes show dollar amounts
ax.xaxis.set_major_formatter("${x:.2f}")
ax.yaxis.set_major_formatter("${x:.2f}")

maidr.show(line_plot)
