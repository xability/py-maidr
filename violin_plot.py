import matplotlib.pyplot as plt
import seaborn as sns
import maidr

# Load sample dataset
tips = sns.load_dataset("tips")

# Create a single violin plot
v = sns.violinplot(y=tips["total_bill"])

# Customize the plot
plt.title("Distribution of Total Bill")
plt.ylabel("Total Bill ($)")
plt.xlabel("")

# Show with MAIDR accessibility
maidr.show(v)
