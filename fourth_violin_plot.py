# Python program to illustrate
# violinplot using inbuilt data-set
# given in seaborn
 
# importing the required modules
import matplotlib.pyplot as plt
import seaborn as sns
import maidr

# use to set style of background of plot
sns.set(style="whitegrid")

# loading data-set
tips = sns.load_dataset("tips")

print("Creating violin plot...")
# Create violin plot
v = sns.violinplot(x='day', y='tip', data=tips, linewidth=4)

# Customize the plot
plt.title("Tip Distribution by Day")

print("Showing with MAIDR...")
# Show with MAIDR accessibility
maidr.show(v)

