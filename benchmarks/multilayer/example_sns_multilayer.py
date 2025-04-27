from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# import maidr


def test() -> Tuple[plt.Figure, plt.Axes]:
    """
    Create a multilayer plot using seaborn: a bar chart of category counts
    with an overlaid linechart of mean values for each category.

    Returns
    -------
    Tuple[plt.Figure, plt.Axes]
        The Matplotlib Figure and primary Axes with the seaborn layers applied.

    Examples
    --------
    >>> fig, ax = create_seaborn_multilayer_plot()
    >>> isinstance(fig, plt.Figure)
    True
    """
    num_categories: int = 5
    num_points: int = 100_000

    # generate DataFrame with random categories and values
    cats = np.random.randint(0, num_categories, size=num_points)
    values = np.random.randn(num_points)  # random metric per point
    df = pd.DataFrame({"category": cats, "value": values})
    # map numeric categories to labels
    df["category"] = df["category"].map(lambda i: f"Cat {i + 1}")

    # create figure and primary axis
    fig, ax1 = plt.subplots(figsize=(8, 5))
    sns.countplot(x="category", data=df, color="skyblue", ax=ax1)
    ax1.set_xlabel("Category")
    ax1.set_ylabel("Count", color="blue")
    ax1.tick_params(axis="y", labelcolor="blue")

    # create secondary axis for mean-value line
    ax2 = ax1.twinx()
    sns.pointplot(
        x="category",
        y="value",
        data=df,
        ci=None,
        color="red",
        marker="o",
        linestyles="-",
        ax=ax2,
    )
    ax2.set_ylabel("Mean Value", color="red")
    ax2.tick_params(axis="y", labelcolor="red")

    # title and combined legend
    fig.suptitle("Seaborn Multilayer Plot with 100k Points")
    # combine legends from both layers
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper left")

    fig.tight_layout()
    return fig, ax1
