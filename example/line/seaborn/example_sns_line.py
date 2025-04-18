import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the 'tips' dataset from seaborn
tips = sns.load_dataset("tips")

# Choose a specific subset of the dataset (e.g., data for 'Thursday')
subset_data = tips[tips["day"] == "Thur"]

# Create a line plot
plt.figure(figsize=(10, 6))
line_plot = sns.lineplot(
    data=subset_data,
    x="total_bill",
    y="tip",
    markers=True,
    style="day",
    legend=False,
)
plt.title("Line Plot of Tips vs Total Bill (Thursday)")
plt.xlabel("Total Bill")
plt.ylabel("Tip")

# plt.show()
maidr.show(line_plot)
