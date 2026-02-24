import altair as alt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")


def boxplot(orientation: str):
    """Create a box plot with Altair."""
    if orientation == "v":
        box_plot = (
            alt.Chart(iris)
            .mark_boxplot()
            .encode(
                x=alt.X("species:N", title="Species"),
                y=alt.Y("petal_length:Q", title="Petal Length (cm)"),
            )
            .properties(
                title="Box Plot of Petal Length by Iris Species", width=400, height=300
            )
        )
    else:
        box_plot = (
            alt.Chart(iris)
            .mark_boxplot()
            .encode(
                x=alt.X("petal_length:Q", title="Petal Length (cm)"),
                y=alt.Y("species:N", title="Species"),
            )
            .properties(
                title="Box Plot of Petal Length by Iris Species", width=400, height=300
            )
        )
    return box_plot


# Create the vertical boxplot
vert = boxplot(orientation="v")
maidr.show(vert)

# Create the horizontal boxplot
horz = boxplot(orientation="h")
maidr.show(horz)
