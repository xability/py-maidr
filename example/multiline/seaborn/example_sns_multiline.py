import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import maidr

"""
Creates a multiline plot using seaborn showing basic data trends.

The plot displays three different data series with discrete points
connected by lines of different styles and colors using seaborn's
lineplot function.

"""


# Create sample data points
x = np.array([1, 2, 3, 4, 5, 6, 7, 8])
y1 = np.array([2, 4, 1, 5, 3, 7, 6, 8])
y2 = np.array([1, 3, 5, 2, 4, 6, 8, 7])
y3 = np.array([3, 1, 4, 6, 5, 2, 4, 5])

# Convert to pandas DataFrame for seaborn
data = pd.DataFrame(
    {
        "x": np.tile(x, 3),
        "y": np.concatenate([y1, y2, y3]),
        "series": np.repeat(["Series 1", "Series 2", "Series 3"], len(x)),
    }
)

# Create the plot
plt.figure(figsize=(10, 6))

# Use seaborn lineplot for multiple lines
lineplot = sns.lineplot(
    x="x", y="y", hue="series", style="series", markers=True, dashes=True, data=data
)

# Customize the plot
plt.title("Seaborn Multiline Plot")
plt.xlabel("X values")
plt.ylabel("Y values")

# Display the plot using maidr
maidr.show(lineplot)
