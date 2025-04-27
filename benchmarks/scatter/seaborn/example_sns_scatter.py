import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# import maidr


def generate_random_dataset(n: int) -> pd.DataFrame:
    """
    Generate a random dataset with two variables x and y.

    Parameters
    ----------
    n : int
        Number of data points to generate.

    Returns
    -------
    pd.DataFrame
        DataFrame containing 'x' and 'y' columns.

    Examples
    --------
    >>> df = generate_random_dataset(100)
    >>> df.shape
    (100, 2)
    """
    x = np.random.randn(n)
    y = np.random.randn(n)
    return pd.DataFrame({"x": x, "y": y})


def test():
    df = generate_random_dataset(100_000)

    # Create a scatter plot
    scatter_plot = sns.scatterplot(data=df, x="x", y="y")

    # Adding title and labels (optional)
    plt.title("Random Scatter Plot (100,000 points)")
    plt.xlabel("x")
    plt.ylabel("y")


# Show the plot
# maidr.show(scatter_plot)
