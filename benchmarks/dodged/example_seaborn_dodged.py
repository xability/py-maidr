import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# import maidr


def generate_category_data(
    num_samples: int,
    means: tuple[float, float, float, float, float],
    scale: float = 50.0,
    seed: int | None = None,
) -> pd.DataFrame:
    """
    Generate synthetic data for multiple categories with values drawn from normal distributions.

    Parameters
    ----------
    num_samples : int
        Number of samples per category.
    means : tuple of float
        Mean for each of the 5 categories.
    scale : float, optional
        Standard deviation for all categories.
    seed : int or None, optional
        Random seed.

    Returns
    -------
    DataFrame
        DataFrame with columns 'Category' and 'Value'.

    Example
    -------
    >>> df = generate_category_data(100000, (10,20,30,40,50), scale=5, seed=0)
    """
    rng = np.random.default_rng(seed)
    categories = [f"Category {i+1}" for i in range(len(means))]
    data: list[dict[str, float]] = []
    for cat, mu in zip(categories, means):
        values = rng.normal(loc=mu, scale=scale, size=num_samples)
        # accumulate observations
        for val in values:
            data.append({"Category": cat, "Value": val})
    return pd.DataFrame(data)


def plot_dodged_bar_seaborn(
    df: pd.DataFrame, means: tuple[float, float, float, float, float]
) -> None:
    """
    Plot a dodged bar chart showing counts of values below and above the category means.

    Parameters
    ----------
    df : DataFrame
        DataFrame containing 'Category' and 'Value' columns.
    means : tuple of float
        Mean for each category, in the same order as in df.
    """
    # map each category to its mean
    mean_map = {f"Category {i+1}": m for i, m in enumerate(means)}
    # flag observations above or below mean
    df["AboveMean"] = df["Value"] >= df["Category"].map(mean_map)

    # count per category & flag
    count_df = df.groupby(["Category", "AboveMean"]).size().reset_index(name="Count")

    sns.set(style="whitegrid")
    plt.figure(figsize=(8, 6))
    ax = sns.barplot(
        data=count_df, x="Category", y="Count", hue="AboveMean", dodge=True
    )
    ax.set_title("Dodged Bar Plot (Seaborn): Counts Above/Below Mean")
    ax.set_xlabel("Category")
    ax.set_ylabel("Count")
    ax.legend(title="Above Mean")
    # maidr.show(ax)


def test() -> None:
    """
    Entry point: generate data for 5 categories and plot.
    """
    means = (10, 20, 30, 40, 50)
    df = generate_category_data(100_000, means, scale=5.0, seed=42)
    plot_dodged_bar_seaborn(df, means)
