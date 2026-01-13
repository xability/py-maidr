import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load dataset (same as seaborn example to keep behavior comparable)
diamonds = sns.load_dataset("diamonds")

print("Creating Matplotlib violin plot with 5 violins...")

# Prepare data grouped by cut (5 categories)
groups = []
values = []
for cut, gdf in diamonds.groupby("cut", observed=False):
    groups.append(cut)
    values.append(gdf["price"].dropna().values)

fig, ax = plt.subplots(figsize=(10, 6))

# Matplotlib violin plot: KDE + min/max by default; we also request mean & median
violins = ax.violinplot(
    values,
    showmeans=True,     # explicitly show mean
    showmedians=True,   # explicitly show median
    showextrema=True,   # min/max
)

# Set x-ticks to match group labels
ax.set_xticks(range(1, len(groups) + 1))
ax.set_xticklabels(groups)

ax.set_title("Diamond Price Distribution by Cut Quality (Matplotlib Violin)")
ax.set_xlabel("Cut Quality")
ax.set_ylabel("Price (USD)")

print("Showing with MAIDR...")
maidr.show(ax)

