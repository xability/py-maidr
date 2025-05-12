import matplotlib.pyplot as plt
import numpy as np

import maidr

# Generating random data for three different groups
data_group1 = np.random.normal(100, 10, 200)
# Add high outliers to data_group1
data_group1 = np.append(data_group1, [150, 160, 155])

data_group2 = np.random.normal(90, 20, 200)
# Add low outliers to data_group2
data_group2 = np.append(data_group2, [10, 5, 15])

data_group3 = np.random.normal(80, 30, 200)
# Add both high and low outliers to data_group3
data_group3 = np.append(data_group3, [180, 190, 0, -10])

# Combine these different datasets into a list
data_to_plot = [data_group1, data_group2, data_group3]


# Create the boxplot
def boxplot(is_vert: bool):
    plt.figure()
    bp = plt.boxplot(data_to_plot, patch_artist=True, vert=is_vert)

    colors = ["lightblue", "lightgreen", "tan"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)

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
