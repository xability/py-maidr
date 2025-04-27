import matplotlib.pyplot as plt
import numpy as np

# import maidr


def test() -> None:
    """Generate and display a multiline plot with specified data points.

    Parameters
    ----------
    num_points : int
        Number of data points per series.

    Returns
    -------
    None

    Examples
    --------
    >>> plot_multiline(100000)
    """
    num_points = 100000
    # Generate data series
    x = np.linspace(0, 10, num_points)
    y1 = np.sin(x)
    y2 = np.cos(x)
    y3 = np.sin(2 * x) * np.cos(x)

    # Create the plot
    plt.figure(figsize=(10, 6))
    lineplot = plt.plot(x, y1, "bo-", linewidth=1, markersize=2)  # Series 1
    lineplot = plt.plot(x, y2, "rs--", linewidth=1, markersize=2)  # Series 2
    lineplot = plt.plot(x, y3, "g^:", linewidth=1, markersize=2)  # Series 3

    # Customize the plot
    plt.title(f"Basic Multiline Plot with {num_points} Points")
    plt.xlabel("X values")
    plt.ylabel("Y values")
    plt.legend(["Series 1", "Series 2", "Series 3"])

    # Display the plot
    # maidr.show(lineplot)
