"""A box layer is read in the order its boxes stand, not the order they were drawn.

seaborn draws a ``hue`` level by level, so ``sns.boxplot(x="day", hue="sex")``
was read Sun, Sat, Thur, Fri for one level and then the same four again for
the other. Right moved the outline to the next category's box of the same
level and back across the chart halfway, instead of to the box drawn beside
it, as an audit that drove every example with the keyboard found. A
matplotlib ``boxplot(positions=...)`` given out of order was read in the
order given.

Measured on the saved SVG of each layout below, seaborn 0.13: a ``hue``
dodges each category's levels across its slot in ``hue_order``, left to
right, and top to bottom on its side; ``dodge=False`` stands them all at the
category.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot.boxplot import _box_center  # noqa: E402

CATEGORIES = ["a", "b", "c"]
LEVELS = ["p", "q"]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def frame() -> pd.DataFrame:
    """Each category's levels with medians apart: a p 0, a q 10, b p 20, ..."""
    rows = []
    for c, category in enumerate(CATEGORIES):
        for g, level in enumerate(LEVELS):
            base = 20 * c + 10 * g
            rows += [(category, level, base + step) for step in range(-2, 3)]
    return pd.DataFrame(rows, columns=["cat", "grp", "val"])


def layer(figure) -> dict:
    return FigureManager.get_maidr(figure).plots[0].schema


def names(figure) -> list[str]:
    return [point["z"] for point in layer(figure)["data"]]


def centres(figure, ax, horizontal: bool) -> list[float]:
    """Where the box each row's selector names stands, row by row."""
    by_gid = {patch.get_gid(): patch for patch in ax.patches}
    gids = [
        re.search(r"g\[id='([^']+)'\]", selector["iq"]).group(1)
        for selector in layer(figure)["selectors"]
    ]
    return [_box_center(by_gid[gid], horizontal) for gid in gids]


def test_a_hue_split_is_read_left_to_right():
    figure, ax = plt.subplots()
    sns.boxplot(frame(), x="cat", y="val", hue="grp", ax=ax)

    assert names(figure) == ["a, p", "a, q", "b, p", "b, q", "c, p", "c, q"]
    drawn = centres(figure, ax, horizontal=False)
    assert drawn == sorted(drawn)
    # Each row still describes the box its selector names.
    assert [point["q2"] for point in layer(figure)["data"]] == [0, 10, 20, 30, 40, 50]


def test_order_and_hue_order_are_followed():
    figure, ax = plt.subplots()
    sns.boxplot(
        frame(),
        x="cat",
        y="val",
        hue="grp",
        order=["c", "a", "b"],
        hue_order=["q", "p"],
        ax=ax,
    )

    assert names(figure) == ["c, q", "c, p", "a, q", "a, p", "b, q", "b, p"]
    assert [point["q2"] for point in layer(figure)["data"]] == [50, 40, 10, 0, 30, 20]


def test_a_hue_split_on_its_side_is_handed_over_top_first():
    # seaborn draws the first category at the top of an inverted y axis, and
    # each category's first level above its second. maidr.js takes a
    # horizontal layer top first and walks it from the bottom up.
    figure, ax = plt.subplots()
    sns.boxplot(frame(), y="cat", x="val", hue="grp", ax=ax)

    assert ax.yaxis_inverted()
    assert names(figure) == ["a, p", "a, q", "b, p", "b, q", "c, p", "c, q"]
    drawn = centres(figure, ax, horizontal=True)
    assert drawn == sorted(drawn)


def test_an_undodged_split_keeps_each_category_together():
    figure, ax = plt.subplots()
    sns.boxplot(frame(), x="cat", y="val", hue="grp", dodge=False, ax=ax)

    assert names(figure) == ["a, p", "a, q", "b, p", "b, q", "c, p", "c, q"]


@pytest.mark.parametrize("vert", [True, False])
def test_matplotlib_positions_given_out_of_order_are_read_in_place(vert):
    figure, ax = plt.subplots()
    samples = [np.arange(30, 40), np.arange(10, 20), np.arange(20, 30)]
    ax.boxplot(samples, positions=[3, 1, 2], vert=vert)

    medians = [point["q2"] for point in layer(figure)["data"]]
    # Left to right; on its side, top first.
    assert medians == ([14.5, 24.5, 34.5] if vert else [34.5, 24.5, 14.5])


def test_a_chart_with_no_hue_is_unchanged():
    figure, ax = plt.subplots()
    sns.boxplot(frame(), x="cat", y="val", order=["b", "c", "a"], ax=ax)

    assert names(figure) == ["b", "c", "a"]
