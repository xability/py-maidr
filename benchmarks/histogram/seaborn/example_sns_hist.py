import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

# import maidr


def generate_large_dataset(
    size: int = 1000000, mu: float = 0.0, sigma: float = 1.0
) -> np.ndarray:
    """
    Generate a large dataset of random values following a normal distribution.

    Parameters
    ----------
    size : int, optional
        Number of data points to generate, by default 1,000,000
    mu : float, optional
        Mean of the normal distribution, by default 0.0
    sigma : float, optional
        Standard deviation of the normal distribution, by default 1.0

    Returns
    -------
    np.ndarray
        Array of randomly generated data points

    Examples
    --------
    >>> data = generate_large_dataset(10000, 5.0, 2.0)
    >>> len(data)
    10000
    """
    # Generate random data following normal distribution
    return np.random.normal(mu, sigma, size)


# Set audio rendering engine
# maidr.set_engine("ts")
def test():
    # Generate large dataset (1 million points)
    data = generate_large_dataset(size=100000, mu=50.0, sigma=15.0)

    # Create a figure with appropriate size
    plt.figure(figsize=(10, 6))

    # Plot histogram using seaborn with KDE
    # For large datasets, we need to adjust the binwidth or number of bins
    n_bins = int(np.sqrt(len(data)))  # Square root rule for bin selection
    hist_plot = sns.histplot(
        data=data,
        kde=True,  # Include kernel density estimate
        color="blue",
        bins=n_bins,  # Use calculated number of bins
        alpha=0.7,  # Add transparency to make KDE visible
        stat="density",  # Use density to better compare with KDE
    )

    # Add informative title and labels
    plt.title(f"Histogram of {len(data):,} Random Data Points (Normal Distribution)")
    plt.xlabel("Value")
    plt.ylabel("Density")

    # Add distribution parameters as text annotation
    plt.annotate(
        f"μ = 50.0, σ = 15.0\nn = {len(data):,}",
        xy=(0.95, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        bbox=dict(boxstyle="round", fc="white", alpha=0.8),
    )

    # Display the histogram through maidr
    # maidr.show(hist_plot)
