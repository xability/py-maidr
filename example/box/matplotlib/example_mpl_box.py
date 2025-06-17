import matplotlib.pyplot as plt
import numpy as np

import maidr

# Generating random data for three different groups
data_group1 = np.random.normal(100, 10, 200)
# Add outliers to data_group1
data_group1 = np.append(data_group1, [150, 160, 50, 40])

data_group2 = np.random.normal(90, 20, 200)
# Add outliers to data_group2
data_group2 = np.append(data_group2, [180, 190, 10, 20])

data_group3 = np.random.normal(80, 30, 200)
# Add outliers to data_group3
data_group3 = np.append(data_group3, [200, 210, -10, -20])

# Combine these different datasets into a list
data_to_plot = [data_group1, data_group2, data_group3]


# Create the boxplot
def boxplot(is_vert: bool):
    plt.figure()
    bp = plt.boxplot(data_to_plot, patch_artist=True, vert=is_vert)

    colors = ["lightblue", "lightgreen", "tan"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)

    # Color outliers
    outlier_color = "red"
    for flier in bp["fliers"]:
        flier.set(
            marker="o",
            markerfacecolor=outlier_color,
            markeredgecolor=outlier_color,
            alpha=0.5,
        )

    if is_vert:
        plt.xticks(ticks=[1, 2, 3], labels=["Group 1", "Group 2", "Group 3"])
        plt.title("Vertical Box Plot Example")
        plt.xlabel("Group")
        plt.ylabel("Values")
    else:
        plt.yticks(ticks=[1, 2, 3], labels=["Group 1", "Group 2", "Group 3"])
        plt.title("Horizontal Box Plot Example")
        plt.ylabel("Group")
        plt.xlabel("Values")

    return bp


# # Create the vertical boxplot
vert = boxplot(is_vert=True)
# plt.show()
maidr.show(vert)

# Create the horizontal boxplot
horz = boxplot(is_vert=False)
# plt.show()
maidr.show(horz)
