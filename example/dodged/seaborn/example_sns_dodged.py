import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import maidr


def plot_dodged_bar() -> None:
    """Create and display a dodged bar plot using Seaborn.

    This function constructs a grouped bar plot of penguin weight counts
    for three species, categorized as 'Below' or 'Above' average mass,
    and renders it via maidr.

    Returns
    -------
    None
        Displays the plot in a pop‑up window.

    Example
    -------
    >>> plot_dodged_bar()
    """
    # Define species names and corresponding weight count arrays
    species: tuple[str, str, str] = (
        "Adelie",
        "Chinstrap",
        "Gentoo",
    )
    weight_counts: dict[str, np.ndarray] = {
        "Below": np.array([70, 31, 58]),
        "Above": np.array([82, 37, 66]),
    }

    # Build a long-form DataFrame for Seaborn
    rows: list[tuple[str, int, str]] = []
    for idx, sp in enumerate(species):
        for category, counts in weight_counts.items():
            rows.append((sp, int(counts[idx]), category))
    df: pd.DataFrame = pd.DataFrame(rows, columns=["species", "count", "category"])

    # Set theme and create the plot
    sns.set_theme(style="whitegrid")
    fig, ax = plt.subplots()
    p = sns.barplot(
        data=df,
        x="species",
        y="count",
        hue="category",
        ax=ax,
        dodge=True,
    )

    hue_levels = df["category"].unique().tolist()

    for container, level in zip(ax.containers, hue_levels):
        container.set_label(level)

    for container in ax.containers:
        print(container.get_label())

    # Label axes and title
    ax.set_xlabel("Penguin Species")
    ax.set_ylabel("Weight Count")
    ax.set_title("Seaborn Dodged Bar Plot: Penguin Weight Counts")
    ax.legend(title="Category", loc="upper right")

    # Render the plot
    maidr.show(p)


if __name__ == "__main__":
    plot_dodged_bar()
