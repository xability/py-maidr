"""Hypnogram in Plotly: a sleep stage held over an interval, then jumping.

Plotly has no step trace type. A staircase is an ordinary ``Scatter`` trace
whose ``line_shape`` tells plotly.js to draw risers between the samples rather
than interpolating across them, so ``line_shape`` is the only thing that marks
the data as piecewise constant. maidr reads it and exports a step layer, which
announces the stage names and lets a user jump transition to transition.

``line_shape`` maps onto MAIDR's step conventions as:

    "hv"  -> hold the value, then jump at the next reading   (used here)
    "vh"  -> jump at the reading, then hold
    "hvh" -> jump midway between readings
    "vhv" -> still a step, but no MAIDR equivalent, so no direction is claimed
"""

import plotly.graph_objects as go

import maidr

# Ordinal sleep stages, deepest first, so that "up" means lighter sleep.
STAGE_NAMES = ["N3", "N2", "N1", "REM", "Awake"]

# One reading every half hour across a night's sleep.
hours = [i * 0.5 for i in range(17)]
stages = [4, 3, 2, 1, 0, 0, 1, 3, 2, 1, 0, 1, 3, 2, 1, 3, 4]

fig = go.Figure(
    go.Scatter(
        x=hours,
        y=stages,
        mode="lines",
        # "hv" is the hypnogram reading: the stage holds until the next
        # reading, then jumps. maidr exports this as stepDirection "hv".
        line_shape="hv",
        name="Night 1",
    )
)

fig.update_layout(
    title="Hypnogram<br>Sleep stage across one night",
    xaxis_title="Time asleep (hours)",
    # Name the ordinal levels. The underlying y values stay numeric, which is
    # what drives sonification, braille and the min/max range.
    yaxis=dict(
        title="Sleep stage",
        tickmode="array",
        tickvals=list(range(len(STAGE_NAMES))),
        ticktext=STAGE_NAMES,
    ),
)

maidr.show(fig)
