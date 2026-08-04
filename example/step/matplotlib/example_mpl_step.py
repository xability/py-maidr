"""Hypnogram: a sleep stage held over an interval, then jumping to the next.

A hypnogram is the motivating case for a step plot. Sleep stage is *ordinal* —
Awake, REM, N1, N2, N3 — and it is piecewise constant: a stage is held for a
stretch of the night and then jumps. Drawing it as a line chart would imply the
sleeper glided continuously through the intermediate stages, which is not what
the data says.

Plot the stages as numeric codes so they keep driving sonification, braille and
the min/max bounds, then name the codes with ``set_yticks(..., labels=...)``.
maidr picks the names up and announces "REM" instead of "3".
"""

import matplotlib.pyplot as plt

import maidr  # noqa: F401

# Ordinal sleep stages, deepest first, so that "up" means lighter sleep.
STAGE_CODES = [0, 1, 2, 3, 4]
STAGE_NAMES = ["N3", "N2", "N1", "REM", "Awake"]

# One reading every half hour across a night's sleep.
hours = [i * 0.5 for i in range(17)]
stages = [4, 3, 2, 1, 0, 0, 1, 3, 2, 1, 0, 1, 3, 2, 1, 3, 4]

fig, ax = plt.subplots(figsize=(10, 5))

# where="post" is the hypnogram reading: the stage holds until the next
# reading, then jumps. maidr exports this as stepDirection "hv".
ax.step(hours, stages, where="post")

# Name the ordinal levels. This is what turns "3" into "REM" in the audio and
# text output; the underlying y values stay numeric.
ax.set_yticks(STAGE_CODES, labels=STAGE_NAMES)

ax.set_title("Hypnogram\nSleep stage across one night")
ax.set_xlabel("Time asleep (hours)")
ax.set_ylabel("Sleep stage")

# Format the x axis for better screen reader output.
ax.xaxis.set_major_formatter("{x:.1f}")

plt.show()
