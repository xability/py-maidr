import altair as alt
import seaborn as sns

import maidr

# Load the Titanic dataset
titanic = sns.load_dataset("titanic")

# Create a count plot
count_plot = (
    alt.Chart(titanic)
    .mark_bar()
    .encode(
        x=alt.X("class:N", title="Class"),
        y=alt.Y("count():Q", title="Count"),
    )
    .properties(
        title="Passenger Class Distribution on the Titanic", width=400, height=300
    )
)

maidr.show(count_plot)
