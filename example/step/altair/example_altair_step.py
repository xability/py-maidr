"""Hypnogram in Altair: a sleep stage held over an interval, then jumping.

Altair expresses a staircase through the mark's ``interpolate`` property, which
Vega-Lite hands to the matching d3 curve. maidr renders Altair charts through
the upstream Vega-Lite adapter, so the step handling lives there and this file
needs nothing maidr-specific beyond the import.

``interpolate`` maps onto MAIDR's step conventions as:

    "step-after"  -> hold the value, then jump at the next reading  (used here)
    "step-before" -> jump at the reading, then hold
    "step"        -> jump midway between readings
"""

import altair as alt
import pandas as pd

import maidr

# Ordinal sleep stages, deepest first, so that "up" means lighter sleep.
STAGE_NAMES = ["N3", "N2", "N1", "REM", "Awake"]

# One reading every half hour across a night's sleep.
hours = [i * 0.5 for i in range(17)]
stages = [4, 3, 2, 1, 0, 0, 1, 3, 2, 1, 0, 1, 3, 2, 1, 3, 4]

df = pd.DataFrame(
    {
        "hours": hours,
        "stage": stages,
        "stage_name": [STAGE_NAMES[s] for s in stages],
    }
)

chart = (
    alt.Chart(df)
    # "step-after" is the hypnogram reading: the stage holds until the next
    # reading, then jumps.
    .mark_line(interpolate="step-after")
    .encode(
        x=alt.X("hours:Q", title="Time asleep (hours)"),
        # The y values stay numeric — they drive sonification, braille and the
        # min/max range — while the axis labels name the ordinal levels.
        y=alt.Y(
            "stage:Q",
            title="Sleep stage",
            axis=alt.Axis(
                values=list(range(len(STAGE_NAMES))),
                labelExpr=(
                    "datum.value == 0 ? 'N3' : datum.value == 1 ? 'N2' : "
                    "datum.value == 2 ? 'N1' : datum.value == 3 ? 'REM' : 'Awake'"
                ),
            ),
        ),
    )
    .properties(title="Hypnogram: sleep stage across one night")
)

maidr.show(chart)
