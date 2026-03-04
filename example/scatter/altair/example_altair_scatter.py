import altair as alt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")

# Create a scatter plot of sepal length vs sepal width, colored by species
scatter_plot = (
    alt.Chart(iris)
    .mark_point()
    .encode(
        x=alt.X("sepal_length:Q", title="Sepal Length (cm)"),
        y=alt.Y("sepal_width:Q", title="Sepal Width (cm)"),
        color=alt.Color("species:N", title="Species"),
    )
    .properties(
        title="Iris Sepal Length vs Sepal Width", width=400, height=300
    )
)

maidr.show(scatter_plot)
