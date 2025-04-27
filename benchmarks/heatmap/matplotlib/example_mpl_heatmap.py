import matplotlib.pyplot as plt
import numpy as np

# import maidr


def test(rows: int = 316, cols: int = 316) -> None:
    """
    Generate and display a large-scale heatmap with approximately
    `rows * cols` data points.

    Parameters
    ----------
    rows : int
        Number of rows in the heatmap (default is 316, so ~99 856 points).
    cols : int
        Number of columns in the heatmap (default is 316, so ~99 856 points).

    Example
    -------
    >>> plot_large_scale_heatmap(200, 500)
    """
    # create random data of specified size
    data: np.ndarray = np.random.rand(rows, cols)

    # set up the figure and axis
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(data, aspect="auto", interpolation="nearest")
    fig.colorbar(im, ax=ax, label="Value")

    # labels and title
    ax.set_title(f"Large-scale heatmap ({rows * cols} points)")
    ax.set_xlabel("Column index")
    ax.set_ylabel("Row index")

    # layout and display
    fig.tight_layout()
    # maidr.show(im)
