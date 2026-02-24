import altair as alt
import pandas as pd
import numpy as np

import maidr

# Define data
vegetables = [
    "cucumber",
    "tomato",
    "lettuce",
    "asparagus",
    "potato",
    "wheat",
    "barley",
]
farmers = [
    "Farmer Joe",
    "Upland Bros.",
    "Smith Gardening",
    "Agrifun",
    "Organiculture",
    "BioGoods Ltd.",
    "Cornylee Corp.",
]

harvest = np.array(
    [
        [0.8, 2.4, 2.5, 3.9, 0.0, 4.0, 0.0],
        [2.4, 0.0, 4.0, 1.0, 2.7, 0.0, 0.0],
        [1.1, 2.4, 0.8, 4.3, 1.9, 4.4, 0.0],
        [0.6, 0.0, 0.3, 0.0, 3.1, 0.0, 0.0],
        [0.7, 1.7, 0.6, 2.6, 2.2, 6.2, 0.0],
        [1.3, 1.2, 0.0, 0.0, 0.0, 3.2, 5.1],
        [0.1, 2.0, 0.0, 1.4, 0.0, 1.9, 6.3],
    ]
)

# Build a long-form DataFrame
rows = []
for i, veg in enumerate(vegetables):
    for j, farmer in enumerate(farmers):
        rows.append(
            {"Vegetable": veg, "Farmer": farmer, "Harvest": float(harvest[i, j])}
        )
df = pd.DataFrame(rows)

# Create a heatmap
heatmap = (
    alt.Chart(df)
    .mark_rect()
    .encode(
        x=alt.X("Farmer:N", title="Farmers"),
        y=alt.Y("Vegetable:N", title="Vegetables"),
        color=alt.Color("Harvest:Q", title="Harvest (tons)"),
    )
    .properties(
        title="Harvest of local farmers (in tons/year)", width=400, height=300
    )
)

# Add text annotations
text = (
    alt.Chart(df)
    .mark_text(color="white")
    .encode(
        x="Farmer:N",
        y="Vegetable:N",
        text=alt.Text("Harvest:Q", format=".1f"),
    )
)

chart = heatmap + text

maidr.show(chart)
