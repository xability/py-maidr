"""Pie chart in Plotly: parts of one whole, read out as slices.

Plotly draws a pie's wedges largest first — ``sort`` defaults to true — so the
order of the ``values`` array is not the order of the slices. maidr reproduces
that ordering, because the slice a user hears has to be the slice that
highlights. Pass ``sort=False`` to keep the authored order in both.

Plotly names neither axis of a pie, so ``xaxis``/``yaxis`` titles in the layout
are what tell maidr how to announce a slice; without them it falls back to the
generic "Label" and "Value". A donut is the same chart with ``hole`` set.
"""

import plotly.graph_objects as go
import seaborn as sns

import maidr

# Load dataset
tips = sns.load_dataset("tips")

# Count the tips recorded on each day of the week.
day_counts = tips["day"].value_counts()

fig = go.Figure(
    go.Pie(
        labels=day_counts.index.tolist(),
        values=day_counts.values.tolist(),
        # Keep the authored order, so the slices read in the order
        # `value_counts()` produced rather than being re-sorted by plotly.
        sort=False,
    )
)

fig.update_layout(
    title="Share of Tips by Day",
    # Name the two dimensions of a slice, so it is read out as
    # "Day: Sat, Number of tips: 87" rather than "Label: Sat, Value: 87".
    xaxis=dict(title="Day"),
    yaxis=dict(title="Number of tips"),
)

maidr.show(fig)
