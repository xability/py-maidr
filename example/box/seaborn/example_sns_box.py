import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")


def boxplot(orientation: str, fig_num: int):
    # Start a new figure
    plt.figure(num=fig_num)

    # Create box plot
    if orientation == "v":
        box_plot = sns.boxplot(
            x="species", y="petal_length", data=iris, orient=orientation
        )
        plt.xlabel("Species")
        plt.ylabel("Petal Length (cm)")
    else:
        box_plot = sns.boxplot(
            x="petal_length", y="species", data=iris, orient=orientation
        )
        plt.ylabel("Species")
        plt.xlabel("Petal Length (cm)")

    # Adding labels and title
    plt.title("Box Plot of Petal Length by Iris Species")

    return box_plot


# Create the vertical boxplot
vert = boxplot(orientation="v", fig_num=1)
# plt.show()
maidr.show(vert)

# Create the vertical boxplot
horz = boxplot(orientation="h", fig_num=2)
# plt.show()
maidr.show(horz)
