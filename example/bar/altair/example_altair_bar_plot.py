import altair as alt
import seaborn as sns

import maidr

# Load dataset
tips = sns.load_dataset("tips")

# Count tips by day
cut_counts = tips["day"].value_counts().reset_index()
cut_counts.columns = ["day", "count"]

# Create a bar plot
bar_plot = (
    alt.Chart(cut_counts)
    .mark_bar(color="skyblue")
    .encode(
        x=alt.X("day:N", title="Day"),
        y=alt.Y("count:Q", title="Count"),
    )
    .properties(title="The Number of Tips by Day", width=400, height=300)
)

maidr.show(bar_plot)
