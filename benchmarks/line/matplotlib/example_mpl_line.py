import matplotlib.pyplot as plt
import numpy as np

import maidr


def generate_large_dataset(n_points: int = 100_000) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate a large dataset with a sine wave pattern and random noise.

    Parameters
    ----------
    n_points : int, optional
        Number of data points to generate, by default 100,000

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        x and y arrays containing the data points

    Examples
    --------
    >>> x, y = generate_large_dataset(1000)
    >>> len(x)
    1000
    """
    # Generate x values (evenly spaced)
    x = np.linspace(0, 100, n_points)

    # Generate y values with sine pattern and noise
    y = 10 * np.sin(0.1 * x) + np.random.normal(0, 2, n_points)

    return x, y


def test():
    # Set the figure size for better visualization
    plt.figure(figsize=(14, 7))

    # Generate large dataset
    x_data, y_data = generate_large_dataset()

    # Create line plot with optimized settings for large datasets
    # Using 'None' for marker improves performance with many points
    line_plot = plt.plot(
        x_data,
        y_data,
        linewidth=0.8,
        alpha=0.8,
        color="blue",
        label=f"Dataset ({len(x_data):,} points)",
    )

    # Add a smoothed trendline for better visualization
    window_size = 1000
    if len(x_data) > window_size:
        # Use moving average for smoother visualization
        smoothed_y = np.convolve(
            y_data, np.ones(window_size) / window_size, mode="valid"
        )
        smoothed_x = x_data[window_size - 1 :]
        plt.plot(
            smoothed_x, smoothed_y, color="red", linewidth=2, label="Smoothed trend"
        )

    # Adding title and labels with performance information
    plt.title(
        f"Large-Scale Line Plot Test\n({len(x_data):,} data points",
        fontsize=16,
    )
    plt.xlabel("X Values", fontsize=12)
    plt.ylabel("Y Values", fontsize=12)
    plt.legend()
    # maidr.show(line_plot)


# test()
