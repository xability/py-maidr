import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import maidr

# Set the size of the dataset for stress testing
DATA_SIZE = 100_000  # 100,000 data points per category


def create_large_dataset(size: int = DATA_SIZE) -> pd.DataFrame:
    """
    Create a large synthetic dataset for stress testing seaborn.

    Parameters
    ----------
    size : int, optional
        Number of data points per category, by default DATA_SIZE

    Returns
    -------
    pd.DataFrame
        DataFrame containing the synthetic data
    """

    # Create 5 categories with different distributions
    categories = ["Category A", "Category B", "Category C", "Category D", "Category E"]

    data = []
    for category in categories:
        if category == "Category A":
            values = np.random.normal(100, 10, size)
        elif category == "Category B":
            values = np.random.normal(90, 20, size)
        elif category == "Category C":
            values = np.random.normal(80, 30, size)
        elif category == "Category D":
            values = np.random.normal(70, 25, size)
        else:  # Category E
            values = np.random.normal(110, 15, size)

        for value in values:
            data.append({"category": category, "value": value})

    df = pd.DataFrame(data)

    return df


def boxplot(orientation: str, fig_num: int, data: pd.DataFrame):  # type: ignore
    """
    Create a box plot with large datasets to test seaborn's performance.

    Parameters
    ----------
    orientation : str
        Orientation of the box plot, 'v' for vertical or 'h' for horizontal
    fig_num : int
        Figure number for the plot
    data : pd.DataFrame
        DataFrame containing the data to plot

    Returns
    -------
    sns.AxesSubplot
        The seaborn box plot object

    Examples
    --------
    >>> df = create_large_dataset(1000)
    >>> box_plot = boxplot('v', 1, df)
    """
    # Start a new figure
    plt.figure(num=fig_num, figsize=(12, 8))

    # Create box plot

    if orientation == "v":
        box_plot = sns.boxplot(x="category", y="value", data=data, orient=orientation)
        plt.xlabel("Category")
        plt.ylabel("Values")
    else:
        box_plot = sns.boxplot(x="value", y="category", data=data, orient=orientation)
        plt.ylabel("Category")
        plt.xlabel("Values")

    return box_plot


def test():
    # Create the large dataset
    large_df = create_large_dataset()

    # Create the vertical boxplot
    # print("Creating vertical boxplot...")
    vert = boxplot(orientation="v", fig_num=1, data=large_df)
    # plt.show()
    # maidr.show(vert)

    # # Create the horizontal boxplot
    # print("Creating horizontal boxplot...")
    # horz = boxplot(orientation="h", fig_num=2, data=large_df)
    # # plt.show()
    # maidr.show(horz)
