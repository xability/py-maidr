import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the penguins dataset
penguins = sns.load_dataset("penguins")

# Create a bar plot showing the average body mass of penguins by species
plt.figure(figsize=(10, 6))
b_plot = sns.barplot(
    x="species", y="body_mass_g", data=penguins, errorbar="sd", palette="Blues_d"
)
plt.title("Average Body Mass of Penguins by Species")
plt.xlabel("Species")
plt.ylabel("Body Mass (g)")

# plt.show()
maidr.show(b_plot)
