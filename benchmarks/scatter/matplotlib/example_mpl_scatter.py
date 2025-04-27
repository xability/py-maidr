from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np

# import maidr


def generate_dataset(n_points: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate a synthetic 2D dataset from a standard normal distribution.

    Parameters
    ----------
    n_points : int
        Number of points to generate.

    Returns
    -------
    x : np.ndarray
        X-coordinates of shape (n_points,).
    y : np.ndarray
        Y-coordinates of shape (n_points,).

    Examples
    --------
    >>> x, y = generate_dataset(5)
    >>> x.shape, y.shape
    ((5,), (5,))
    """
    x = np.random.randn(n_points)
    y = np.random.randn(n_points)
    return x, y


def plot_scatter(x: np.ndarray, y: np.ndarray, size: Tuple[int, int] = (10, 6)):
    """
    Plot a scatter plot for the given data.

    Parameters
    ----------
    x : np.ndarray
        X-coordinates of data points.
    y : np.ndarray
        Y-coordinates of data points.
    size : Tuple[int, int], optional
        Figure size in inches, by default (10, 6).

    Returns
    -------
    plt.PathCollection
        The scatter plot artist.

    Examples
    --------
    >>> sc = plot_scatter(x, y)
    """
    plt.figure(figsize=size)
    scatter = plt.scatter(x, y, c="blue", s=10, alpha=0.5)
    plt.title("Synthetic Dataset Scatter Plot")
    plt.xlabel("X values")
    plt.ylabel("Y values")
    plt.legend(["Data Points"])
    return scatter


def test():  # Generate and plot 100 000 points
    x_vals, y_vals = generate_dataset(100_000)
    sc = plot_scatter(x_vals, y_vals)
    # maidr.show(sc)
