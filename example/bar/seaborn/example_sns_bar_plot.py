import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the penguins dataset
penguins = sns.load_dataset("penguins")

# Create a bar plot showing the average body mass of penguins by species
fig, ax = plt.subplots(figsize=(10, 6))
b_plot = sns.barplot(
    x="species", y="body_mass_g", data=penguins, errorbar="sd", palette="Blues_d", ax=ax
)
ax.set_title("Average Body Mass of Penguins by Species")
ax.set_xlabel("Species")
ax.set_ylabel("Body Mass (g)")

# Add number formatter to y-axis for better screen reader output
# Body mass values with thousands separator (e.g., "4,500")
ax.yaxis.set_major_formatter("{x:,.0f}")

maidr.show(b_plot)
