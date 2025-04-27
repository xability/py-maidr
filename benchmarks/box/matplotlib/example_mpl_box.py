import matplotlib.pyplot as plt
import numpy as np

import maidr


def boxplot(is_vert: bool) -> dict:
    """
    Create a box plot with large datasets to test matplotlib's performance.

    Parameters
    ----------
    is_vert : bool
        Whether to create a vertical (True) or horizontal (False) box plot.

    Returns
    -------
    dict
        The box plot artists dictionary returned by plt.boxplot

    Examples
    --------
    >>> bp = boxplot(is_vert=True)  # Create a vertical box plot
    """
    # Set the size of the dataset for stress testing
    DATA_SIZE = 100_000  # 100,000 data points per group

    # Generating very large random datasets for performance testing

    data_group1 = np.random.normal(100, 10, DATA_SIZE)
    data_group2 = np.random.normal(90, 20, DATA_SIZE)
    data_group3 = np.random.normal(80, 30, DATA_SIZE)
    data_group4 = np.random.normal(70, 25, DATA_SIZE)
    data_group5 = np.random.normal(110, 15, DATA_SIZE)

    # Combine these different datasets into a list
    data_to_plot = [data_group1, data_group2, data_group3, data_group4, data_group5]
    plt.figure(figsize=(12, 8))  # Larger figure for better visibility with large data

    bp = plt.boxplot(data_to_plot, patch_artist=True, vert=is_vert)

    colors = ["lightblue", "lightgreen", "tan", "salmon", "plum"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)

    groups = [f"Group {i+1}" for i in range(len(data_to_plot))]

    if is_vert:
        plt.xticks(ticks=range(1, len(data_to_plot) + 1), labels=groups)
        plt.xlabel("Group")
        plt.ylabel("Values")
    else:
        plt.yticks(ticks=range(1, len(data_to_plot) + 1), labels=groups)
        plt.ylabel("Group")
        plt.xlabel("Values")

    return bp


def test():
    # Create the vertical boxplot
    vert = boxplot(is_vert=True)
    # plt.show()
    # maidr.show(vert)

    # # Create the horizontal boxplot
    # horz = boxplot(is_vert=False)
    # # plt.show()
    # maidr.show(horz)
