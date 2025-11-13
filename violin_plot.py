import os
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

# Prepare to save output HTML
script_dir = os.path.dirname(os.path.abspath(__file__))
examples_dir = os.path.join(script_dir, "..", "maidr", "examples")
os.makedirs(examples_dir, exist_ok=True)

# Save as HTML file
html_path = os.path.join(examples_dir, "first_violin_plot.html")
html_path = maidr.save_html(v, file=html_path)

print(f"HTML saved to: {html_path}")