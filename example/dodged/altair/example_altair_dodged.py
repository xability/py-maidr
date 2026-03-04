import altair as alt
import pandas as pd

import maidr

# Define species and weight count data
species = ["Adelie", "Chinstrap", "Gentoo"]
weight_counts = {
    "Below": [70, 31, 58],
    "Above": [82, 37, 66],
}

# Build a long-form DataFrame for Altair
rows = []
for sp_idx, sp in enumerate(species):
    for category, counts in weight_counts.items():
        rows.append({"species": sp, "count": counts[sp_idx], "category": category})
df = pd.DataFrame(rows)

# Create a dodged (grouped) bar plot
dodged_plot = (
    alt.Chart(df)
    .mark_bar()
    .encode(
        x=alt.X("species:N", title="Species"),
        y=alt.Y("count:Q", title="Count"),
        color=alt.Color("category:N", title="Category"),
        xOffset="category:N",
    )
    .properties(
        title="Dodged Bar Plot: Penguin Weight Counts", width=400, height=300
    )
)

maidr.show(dodged_plot)
