from typing import List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# import maidr


def generate_multiline_data(num_lines: int, num_points: int) -> pd.DataFrame:
    """
    Generate synthetic data for multiple lines.

    Parameters
    ----------
    num_lines : int
        Number of distinct lines to generate.
    num_points : int
        Number of data points per line.

    Returns
    -------
    pd.DataFrame
        DataFrame containing 'x', 'y', and 'line' columns.

    Examples
    --------
    >>> df = generate_multiline_data(num_lines=3, num_points=100000)
    >>> df.head()
           x         y   line
    0  0.00  0.012345  line_0
    1  0.01 -0.023456  line_0
    2  0.02  0.045678  line_0
    3  0.03  1.012345  line_1
    4  0.04  0.987654  line_1
    """
    # Create x values equally spaced between 0 and 10
    x = np.linspace(0, 10, num_points)
    data: List[pd.DataFrame] = []
    for line_id in range(num_lines):
        # Add a sinusoidal trend with noise, offset by line_id
        y = np.sin(x + line_id * np.pi / 4) + np.random.normal(
            loc=0, scale=0.1, size=num_points
        )
        df_line = pd.DataFrame({"x": x, "y": y, "line": f"line_{line_id}"})
        data.append(df_line)
    # Combine all lines into one DataFrame
    return pd.concat(data, ignore_index=True)


def test(num_lines: int = 3, num_points: int = 100000) -> None:
    """
    Plot multiple lines using Seaborn with a large dataset.

    Parameters
    ----------
    num_lines : int, optional
        Number of distinct lines to plot (default is 3).
    num_points : int, optional
        Number of points per line (default is 100000).

    Returns
    -------
    None

    Examples
    --------
    >>> plot_multiline_seaborn(num_lines=5, num_points=100000)
    """
    # Generate the multiline dataset
    df = generate_multiline_data(num_lines=num_lines, num_points=num_points)

    # Set Seaborn style and figure size
    sns.set(style="whitegrid")
    plt.figure(figsize=(12, 6))

    # Plot lines with hue grouping
    lineplot = sns.lineplot(
        data=df, x="x", y="y", hue="line", palette="tab10", linewidth=1, alpha=0.8
    )

    plt.title("Multiline Plot with Seaborn")
    plt.xlabel("X-axis")
    plt.ylabel("Y-axis")
    plt.legend(title="Line")
    plt.tight_layout()
    # maidr.show(lineplot)
