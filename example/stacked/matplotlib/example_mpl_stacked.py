import matplotlib.pyplot as plt
import numpy as np

import maidr

species = (
    "Adelie\nMean = 3700.66g",
    "Chinstrap\nMean = 3733.09g",
    "Gentoo\nMean = 5076.02g",
)
weight_counts = {
    "Below": np.array([70, 31, 58]),
    "Above": np.array([82, 37, 66]),
}
width = 0.5

fig, ax = plt.subplots()

bottom = np.zeros(3)

for boolean, weight_count in weight_counts.items():
    p = ax.bar(species, weight_count, width, label=boolean, bottom=bottom)
    bottom += weight_count

ax.set_xlabel("Species of Penguins")
ax.set_ylabel("Average Body Mass")

ax.set_title("Penguins with above or below average body mass")
ax.legend(loc="upper right")

maidr.show(p)
