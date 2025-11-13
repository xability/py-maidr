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


# Save to maidr/examples directory
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
examples_dir = os.path.join(script_dir, "..", "maidr", "examples")
os.makedirs(examples_dir, exist_ok=True)
html_path = os.path.join(examples_dir, "fourth_violin_plot.html")
html_path = maidr.save_html(v, file=html_path)
print(f"HTML saved to: {html_path}")

