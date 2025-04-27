import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# import maidr


def generate_large_dataset(n_points: int = 100_000) -> pd.DataFrame:
    """
    Generate a large DataFrame with a sine pattern plus noise.

    Parameters
    ----------
    n_points : int, optional
        Number of data points to generate, by default 100000

    Returns
    -------
    pd.DataFrame
        DataFrame with columns 'x' and 'y'

    Examples
    --------
    >>> df = generate_large_dataset(1000)
    >>> len(df)
    1000
    >>> set(df.columns)
    {'x', 'y'}
    """
    # Evenly spaced x values
    x = np.linspace(0, 100, n_points)
    # y as sine wave plus Gaussian noise
    y = 10 * np.sin(0.1 * x) + np.random.normal(loc=0, scale=2, size=n_points)
    return pd.DataFrame({"x": x, "y": y})


def plot_large_dataset(df: pd.DataFrame, window_size: int = 1000) -> None:
    """
    Plot a large dataset using seaborn with an optional smoothed trendline.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing 'x' and 'y' columns.
    window_size : int, optional
        Window size for moving average smoothing, by default 1000
    """
    # Initialize figure
    plt.figure(figsize=(12, 6))

    # Scatter-free line plot (markers off for performance)
    lineplot = sns.lineplot(
        data=df,
        x="x",
        y="y",
        linewidth=0.8,
        alpha=0.6,
        color="blue",
        legend=False,
    )

    # Compute and plot moving average trendline if enough points
    if len(df) > window_size:
        smoothed = df["y"].rolling(window=window_size, center=False).mean()
        plt.plot(
            df["x"].iloc[window_size - 1 :],
            smoothed.iloc[window_size - 1 :],
            color="red",
            linewidth=2,
            label="Smoothed trend",
        )
        plt.legend()

    # Labels and title
    plt.title(f"Seaborn Line Plot with {len(df):,} Points", fontsize=14)
    plt.xlabel("X Value", fontsize=12)
    plt.ylabel("Y Value", fontsize=12)
    plt.tight_layout()
    # maidr.show(lineplot)


def test() -> None:
    """
    Main execution: generate data and create plot.
    """
    df = generate_large_dataset()
    plot_large_dataset(df)
