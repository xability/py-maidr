"""Hypnogram drawn with seaborn: a sleep stage held over an interval, then jumping.

seaborn has no dedicated step function, but ``lineplot`` forwards ``drawstyle``
through to matplotlib, and maidr classifies a layer by the drawstyle of the
artists that come back — so ``drawstyle="steps-post"`` produces a step layer
here exactly as ``ax.step(..., where="post")`` does in the matplotlib example.

As there, the stages are plotted as numeric codes so they keep driving
sonification, braille and the min/max range, and are named afterwards with
``set_yticks(..., labels=...)``. maidr picks the names up and announces "REM"
instead of "3".
"""

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

import maidr  # noqa: F401

# Ordinal sleep stages, deepest first, so that "up" means lighter sleep.
STAGE_CODES = [0, 1, 2, 3, 4]
STAGE_NAMES = ["N3", "N2", "N1", "REM", "Awake"]

# One reading every half hour across a night's sleep.
night = pd.DataFrame(
    {
        "hours": [i * 0.5 for i in range(17)],
        "stage": [4, 3, 2, 1, 0, 0, 1, 3, 2, 1, 0, 1, 3, 2, 1, 3, 4],
    }
)

fig, ax = plt.subplots(figsize=(10, 5))

# drawstyle="steps-post" is the hypnogram reading: the stage holds until the
# next reading, then jumps. maidr exports this as stepDirection "hv".
sns.lineplot(data=night, x="hours", y="stage", drawstyle="steps-post", ax=ax)

# Name the ordinal levels. This is what turns "3" into "REM" in the audio and
# text output; the underlying y values stay numeric.
ax.set_yticks(STAGE_CODES, labels=STAGE_NAMES)

ax.set_title("Hypnogram\nSleep stage across one night")
ax.set_xlabel("Time asleep (hours)")
ax.set_ylabel("Sleep stage")

plt.show()
