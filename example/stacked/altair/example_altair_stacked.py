import altair as alt
import seaborn as sns

import maidr

# Load the Titanic dataset
titanic = sns.load_dataset("titanic")

# Group by class and survived
grouped = (
    titanic.groupby(["class", "survived"])
    .size()
    .reset_index(name="count")
)
grouped["survived"] = grouped["survived"].map({0: "Did not survive", 1: "Survived"})

# Create a stacked bar chart
stacked_plot = (
    alt.Chart(grouped)
    .mark_bar()
    .encode(
        x=alt.X("class:N", title="Class"),
        y=alt.Y("count:Q", title="Number of Passengers", stack="zero"),
        color=alt.Color("survived:N", title="Survival Status"),
    )
    .properties(
        title="Passenger Count by Class and Survival Status on the Titanic",
        width=400,
        height=300,
    )
)

maidr.show(stacked_plot)
