import matplotlib.pyplot as plt
import numpy as np

# import maidr

# Define labels and their true means (in grams)
species_labels: tuple[str, str, str] = (
    "Adelie\n $\\mu=3700.66g$",
    "Chinstrap\n $\\mu=3733.09g$",
    "Gentoo\n $\\mu=5076.02g$",
)
species_means: tuple[float, float, float] = (3700.66, 3733.09, 5076.02)


def generate_penguin_weight_counts(
    num_samples: int, means: tuple[float, float, float], seed: int | None = None
) -> dict[str, np.ndarray]:
    """
    Generate counts of penguin weights below and above their species mean.

    Parameters
    ----------
    num_samples : int
        Total number of samples to generate across all species.
    means : tuple of float
        Mean weight for each species.
    seed : int or None, optional
        Seed for random number generator.

    Returns
    -------
    counts : dict of str to np.ndarray
        Dictionary with keys "Below" and "Above", each an array of counts per species.

    Example
    -------
    >>> counts = generate_penguin_weight_counts(100000, (3700, 3733, 5076), seed=0)
    """
    rng = np.random.default_rng(seed)
    per_species = num_samples // len(means)
    below_counts = []
    above_counts = []

    for mu in means:
        # simulate weights with a fixed sigma
        weights = rng.normal(loc=mu, scale=500, size=per_species)
        below_counts.append(np.sum(weights < mu))
        above_counts.append(np.sum(weights >= mu))

    return {
        "Below": np.array(below_counts, dtype=int),
        "Above": np.array(above_counts, dtype=int),
    }


def plot_dodged_bar(
    weight_counts: dict[str, np.ndarray], species: tuple[str, ...], width: float = 0.35
) -> None:
    """
    Plot a dodged bar chart of weight counts for each category and species.

    Parameters
    ----------
    weight_counts : dict of str to np.ndarray
        Counts per species for "Below" and "Above" categories.
    species : tuple of str
        Labels for each species.
    width : float, optional
        Width of each bar.

    """
    x = np.arange(len(species))
    total_groups = len(weight_counts)
    offsets = [(-width / 2) + i * width for i in range(total_groups)]

    fig, ax = plt.subplots()
    # draw each category at its offset
    for offset, (category, counts) in zip(offsets, weight_counts.items()):
        ax.bar(x + offset, counts, width, label=category)

    ax.set_xticks(x)
    ax.set_xticklabels(species)
    ax.set_xlabel("Species")
    ax.set_title("Dodged Bar Plot: Penguin Weight Counts (100 000 samples)")
    ax.legend(loc="upper right")

    # render via maidr
    # maidr.show(ax)


def test() -> None:
    """
    Entry point: generate data for 100 000 samples and plot.
    """
    counts = generate_penguin_weight_counts(100_000, species_means, seed=42)
    plot_dodged_bar(counts, species_labels)
