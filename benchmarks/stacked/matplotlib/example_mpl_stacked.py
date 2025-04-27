import matplotlib.pyplot as plt
import numpy as np


def test() -> None:
    """
    Generate and display a stacked bar plot for 5 categories, each with 100,000 datapoints,
    divided into 'Below' and 'Above' mean groups.

    This example creates synthetic normal data for each category, computes how many points
    fall below and above the sample mean, and then plots those counts as a stacked bar chart.

    Example:
        >>> generate_stacked_bar_plot()
    """
    # Define 5 categories and their underlying means
    categories = ["Category A", "Category B", "Category C", "Category D", "Category E"]
    means = [50, 60, 70, 80, 90]

    # Generate synthetic data: 100k samples per category
    data = {
        cat: np.random.normal(loc=mean, scale=10, size=100_000)
        for cat, mean in zip(categories, means)
    }

    # Compute counts below and above each category's sample mean
    below_counts = np.array([np.sum(vals < vals.mean()) for vals in data.values()])
    above_counts = np.array([np.sum(vals >= vals.mean()) for vals in data.values()])

    # Create the plot
    fig, ax = plt.subplots()
    width = 0.5
    bottom = np.zeros(len(categories))

    # Plot stacked bars for 'Below' and 'Above' groups
    for label, counts in (("Below", below_counts), ("Above", above_counts)):
        ax.bar(categories, counts, width, label=label, bottom=bottom)
        bottom += counts

    # Labeling
    ax.set_xlabel("Category")
    ax.set_ylabel("Count of Samples")
    ax.set_title("Stacked Bar Plot: Below vs. Above Mean for 5 Categories")
    ax.legend(loc="upper right")
