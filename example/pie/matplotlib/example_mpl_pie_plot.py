"""Pie chart: parts of one whole, read out as slices.

A pie is one flat row of slices, so navigation runs left and right across
them and there is no second dimension to move through. Each slice is
announced by its label, its value, and the share of the whole that value
works out to — the percentage is derived from the values at render time
rather than authored, so it can never disagree with them.

``Axes.pie`` normalises what it is given: it draws ``x / sum(x)`` and each
wedge keeps only its angles, so the counts below survive as counts only
because maidr reads them off the call. Set ``xlabel`` and ``ylabel`` to name
what a slice *is* and what it *measures*; otherwise a slice is announced with
the generic "Category" and "Value".
"""

import matplotlib.pyplot as plt
import seaborn as sns

import maidr  # noqa: F401

# Load dataset
tips = sns.load_dataset("tips")

# Count the tips recorded on each day of the week.
day_counts = tips["day"].value_counts()

fig, ax = plt.subplots(figsize=(8, 8))

# autopct draws the percentages onto the chart for sighted readers; maidr
# derives its own from the values, so the two cannot drift apart.
ax.pie(
    list(day_counts.values),
    labels=list(day_counts.index),
    autopct="%1.1f%%",
    startangle=90,
)

ax.set_title("Share of Tips by Day")

# Name the two dimensions of a slice, so it is read out as
# "Day: Sat, Number of tips: 87" rather than "X: Sat, Y: 87".
ax.set_xlabel("Day")
ax.set_ylabel("Number of tips")

plt.show()
