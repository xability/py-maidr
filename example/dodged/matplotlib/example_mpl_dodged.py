"""
Dodged Bar Plot Example.

This example demonstrates how to create a dodged (grouped) bar plot with Matplotlib,
displaying data for different penguin species for two categories: 'Below' and 'Above'
average body masses.

Example:
    $ python example_mpl_dodged.py
"""

import matplotlib.pyplot as plt
import numpy as np

import maidr

species: tuple[str, str, str] = (
    "Adelie",
    "Chinstrap",
    "Gentoo",
)
weight_counts: dict[str, np.ndarray] = {
    "Below": np.array([70, 31, 58]),
    "Above": np.array([82, 37, 66]),
}

x: np.ndarray = np.arange(len(species))
total_groups: int = len(weight_counts)
width: float = 0.35

fig, ax = plt.subplots()

offsets: list[float] = [(-width / 2) + i * width for i in range(total_groups)]

for offset, (category, counts) in zip(offsets, weight_counts.items()):
    positions = x + offset
    p = ax.bar(positions, counts, width, label=category)

# Set x-axis labels and title
ax.set_xticks(x)
ax.set_xticklabels(species)
ax.set_xlabel("Species")
ax.set_title("Dodged Bar Plot: Penguin Weight Counts")
ax.legend(loc="upper right")

# Show plot using maidr.show
maidr.show(p)
