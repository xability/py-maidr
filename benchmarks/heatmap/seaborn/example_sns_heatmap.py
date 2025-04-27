import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# import maidr


def test(num_models: int = 1000, num_tasks: int = 100) -> None:
    """
    Generate and plot a large-scale heatmap with random data.

    Parameters
    ----------
    num_models : int
        Number of model rows in the heatmap.
    num_tasks : int
        Number of task columns in the heatmap.

    Examples
    --------
    >>> plot_large_heatmap(1000, 100)
    """
    # Generate synthetic data with specified dimensions (total entries = num_models * num_tasks)
    data: np.ndarray = np.random.rand(num_models, num_tasks)
    model_labels = [f"Model_{i}" for i in range(num_models)]
    task_labels = [f"Task_{j}" for j in range(num_tasks)]
    df: pd.DataFrame = pd.DataFrame(data, index=model_labels, columns=task_labels)

    # Plot the heatmap
    plt.figure(figsize=(12, 10))
    sns.heatmap(df, cmap="viridis", cbar_kws={"label": "Random Score"})
    plt.title(f"Large-scale Heatmap ({num_models}×{num_tasks})")
