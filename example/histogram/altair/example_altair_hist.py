import altair as alt
import seaborn as sns

import maidr

# Load the Iris dataset
iris = sns.load_dataset("iris")

# Create a histogram of petal lengths
hist_plot = (
    alt.Chart(iris)
    .mark_bar(color="steelblue")
    .encode(
        x=alt.X("petal_length:Q", bin=alt.Bin(maxbins=20), title="Petal Length (cm)"),
        y=alt.Y("count():Q", title="Frequency"),
    )
    .properties(
        title="Histogram of Petal Lengths in Iris Dataset", width=400, height=300
    )
)

maidr.show(hist_plot)
