import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")


def boxplot(orientation: str):
    # Create figure and axes
    fig, ax = plt.subplots()

    # Create box plot
    if orientation == "v":
        box_plot = sns.boxplot(
            x="species", y="petal_length", data=iris, orient=orientation, ax=ax
        )
        ax.set_xlabel("Species")
        ax.set_ylabel("Petal Length (cm)")
        # Add number formatter to value axis for better screen reader output
        ax.yaxis.set_major_formatter("{x:.1f}")
    else:
        box_plot = sns.boxplot(
            x="petal_length", y="species", data=iris, orient=orientation, ax=ax
        )
        ax.set_ylabel("Species")
        ax.set_xlabel("Petal Length (cm)")
        # Add number formatter to value axis for better screen reader output
        ax.xaxis.set_major_formatter("{x:.1f}")

    # Adding labels and title
    ax.set_title("Box Plot of Petal Length by Iris Species")

    return box_plot


# Create the vertical boxplot
vert = boxplot(orientation="v")
maidr.show(vert)

# Create the horizontal boxplot
horz = boxplot(orientation="h")
maidr.show(horz)
