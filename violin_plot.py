import matplotlib.pyplot as plt
import seaborn as sns
import maidr

# Load sample dataset
tips = sns.load_dataset("tips")

print("Creating violin plot...")
# Create a single violin plot with box plot elements
v = sns.violinplot(y=tips["total_bill"], inner='box')

# Customize the plot
plt.title("Distribution of Total Bill")
plt.ylabel("Total Bill ($)")
plt.xlabel("")

print("Showing with MAIDR...")
# Show with MAIDR accessibility
maidr.show(v)
