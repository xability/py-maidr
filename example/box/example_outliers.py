from typing import Any, Dict, List

import matplotlib.pyplot as plt
import numpy as np

import maidr


def boxplot_with_outliers(is_vert: bool = True) -> Dict[str, Any]:
    """
    Generate and display a box plot with explicit upper and lower outliers.

    Parameters
    ----------
    is_vert : bool, optional
        If True, draw a vertical box plot; otherwise draw horizontal.
        Default is True.

    Returns
    -------
    dict of str to list or Line2D
        The dictionary of matplotlib artists making up the box plot.

    Example
    -------
    >>> bp = boxplot_with_outliers(is_vert=False)
    >>> maidr.show(bp)
    """
    # Generate three groups of data with 200 normal points each
    rng = np.random.default_rng()
    groups: List[np.ndarray] = []
    for mean, std in [(100, 10), (90, 20), (80, 30)]:
        data = rng.normal(loc=mean, scale=std, size=200)
        # Create 5 lower and 5 upper outliers
        lower_out = rng.uniform(low=mean - 5 * std, high=mean - 3 * std, size=5)
        upper_out = rng.uniform(low=mean + 3 * std, high=mean + 5 * std, size=5)
        data_with_out = np.concatenate((data, lower_out, upper_out))
        groups.append(data_with_out)

    # Plot configuration
    plt.figure()
    bp = plt.boxplot(groups, patch_artist=True, vert=is_vert)

    # Set distinctive face colors for each box
    colors = ["lightcoral", "lightseagreen", "lightsteelblue"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)

    # Labeling and orientation
    labels = ["Group 1", "Group 2", "Group 3"]
    if is_vert:
        plt.xticks(ticks=[1, 2, 3], labels=labels)
        plt.title("Box Plot with Outliers (Vertical)")
        plt.xlabel("Group")
        plt.ylabel("Values")
    else:
        plt.yticks(ticks=[1, 2, 3], labels=labels)
        plt.title("Box Plot with Outliers (Horizontal)")
        plt.ylabel("Group")
        plt.xlabel("Values")

    return bp


if __name__ == "__main__":
    # # Example usage: draw horizontal and vertical plots
    # vert_bp = boxplot_with_outliers(is_vert=True)
    # # plt.show()
    # maidr.show(vert_bp)

    horz_bp = boxplot_with_outliers(is_vert=False)
    # plt.show()
    maidr.show(horz_bp)
