import matplotlib.pyplot as plt
import seaborn as sns
import maidr

# Load sample dataset
penguins = sns.load_dataset("penguins")

print("Creating multiple violin plots...")
# Create multiple violins comparing flipper length across species
v = sns.violinplot(
    x="species", 
    y="flipper_length_mm", 
    data=penguins,
    inner='box',       # show box elements
    palette="Set2"     # nice distinct colors
)

# Customize the plot
plt.title("Flipper Length Distribution by Penguin Species")
plt.xlabel("Species")
plt.ylabel("Flipper Length (mm)")

print("Showing with MAIDR...")
# Show with MAIDR accessibility
maidr.show(v)

