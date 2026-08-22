"""A hue-grouped box plot announces every box it draws (#593).

`sns.boxplot(hue=...)` draws one box per category *per level* and announced
only the first level's. Not a wrong reading of six boxes -- three of them
absent from the schema entirely, with nothing raising, on a chart that reads
as a complete single-grouped box plot.

The cause is one `zip`. `_extract_bxp_maidr` paired the per-box lists against
`levels`, which is the axis's **tick labels** -- one per category, three where
there are six boxes -- and `zip` ends at the shortest of what it is given.
Measured on three categories and two levels::

    medians drawn   grp=p: [-0.54,   0.068, 0.2687]
                    grp=q: [-0.1045, 0.2446, 0.3534]
    emitted         n=3  z=['a','b','c']  q2=[0.2687, -0.54, 0.068]

The three that survived are exactly group p's. The plumbing above was never
at fault: the container accumulates both `bxp` calls and hands the layer six
boxes, twelve whiskers and six medians.

The siblings all read the same chart correctly -- `boxenplot` and
`violinplot` both emit six -- which is what made this legible rather than
plausible.
"""

from __future__ import annotations

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402

CATEGORIES = ["a", "b", "c"]
LEVELS = ["p", "q"]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "cat": CATEGORIES * 20,
            "grp": LEVELS * 30,
            "val": rng.normal(size=60),
        }
    )


def schema(figure) -> dict:
    return FigureManager.get_maidr(figure).plots[0].schema


def drawn_medians(data: pd.DataFrame) -> set[float]:
    """Every median the chart draws, computed without touching maidr."""
    return {
        round(float(np.median(data.val[(data.cat == cat) & (data.grp == grp)])), 9)
        for cat in CATEGORIES
        for grp in LEVELS
    }


class TestEveryBoxIsAnnounced:
    def test_a_hue_split_emits_one_row_per_box(self):
        figure, ax = plt.subplots()
        sns.boxplot(frame(), x="cat", y="val", hue="grp", ax=ax)

        assert len(schema(figure)["data"]) == len(CATEGORIES) * len(LEVELS)

    def test_no_drawn_median_is_missing(self):
        # Stronger than the count: a reading that emitted six rows by
        # repeating one level's three would satisfy the case above.
        data = frame()
        figure, ax = plt.subplots()
        sns.boxplot(data, x="cat", y="val", hue="grp", ax=ax)
        announced = {
            round(float(point["q2"]), 9) for point in schema(figure)["data"]
        }

        assert announced == drawn_medians(data)

    def test_each_row_names_its_category_and_its_level(self):
        figure, ax = plt.subplots()
        sns.boxplot(frame(), x="cat", y="val", hue="grp", ax=ax)
        names = [point["z"] for point in schema(figure)["data"]]

        assert sorted(names) == [
            f"{cat}, {grp}" for cat in CATEGORIES for grp in LEVELS
        ]

    def test_the_name_matches_the_box_it_is_on(self):
        # The category comes from the box's position and the level from its
        # colour, so a chart that got either wrong would still pass the case
        # above. This pins the pairing.
        data = frame()
        figure, ax = plt.subplots()
        sns.boxplot(data, x="cat", y="val", hue="grp", ax=ax)

        for point in schema(figure)["data"]:
            cat, grp = str(point["z"]).split(", ")
            rows = data.val[(data.cat == cat) & (data.grp == grp)]
            assert round(float(point["q2"]), 9) == round(float(np.median(rows)), 9)

    def test_there_is_one_selector_per_announced_box(self):
        # The selectors are built from the artists and the data was not, so
        # the same chart emitted six selectors against three rows -- every
        # highlight past the third addressing a box nothing announces.
        figure, ax = plt.subplots()
        sns.boxplot(frame(), x="cat", y="val", hue="grp", ax=ax)
        emitted = schema(figure)

        assert len(emitted["selectors"]) == len(emitted["data"])

    def test_an_undodged_split_is_read_too(self):
        # `dodge=False` overlays the levels in one slot instead of splitting
        # it. Same six boxes, same loss before this.
        figure, ax = plt.subplots()
        sns.boxplot(frame(), x="cat", y="val", hue="grp", dodge=False, ax=ax)

        assert len(schema(figure)["data"]) == 6

    def test_a_chart_on_its_side_is_read_too(self):
        # The categories move to y, so the box's position has to be read
        # there. Reading x would name every box after whichever tick the
        # *values* happened to fall nearest.
        data = frame()
        figure, ax = plt.subplots()
        sns.boxplot(data, y="cat", x="val", hue="grp", ax=ax)
        emitted = schema(figure)["data"]
        announced = {round(float(point["q2"]), 9) for point in emitted}

        assert announced == drawn_medians(data)
        # And each row still names the box it is on. Reading the position off
        # x here finds the *values*, which all fall near one category tick --
        # so every box comes out named after that one category, with the
        # medians above still all present and all mislabelled.
        for point in emitted:
            cat, grp = str(point["z"]).split(", ")
            rows = data.val[(data.cat == cat) & (data.grp == grp)]
            assert round(float(point["q2"]), 9) == round(float(np.median(rows)), 9)


class TestWhatIsUnchanged:
    def test_a_chart_with_no_hue_keeps_its_category_names(self):
        figure, ax = plt.subplots()
        sns.boxplot(frame(), x="cat", y="val", ax=ax)
        data = schema(figure)["data"]

        assert [point["z"] for point in data] == CATEGORIES

    def test_a_matplotlib_boxplot_is_unchanged(self):
        rng = np.random.default_rng(0)
        figure, ax = plt.subplots()
        ax.boxplot([rng.normal(size=20) for _ in range(3)])
        data = schema(figure)["data"]

        assert len(data) == 3

    def test_a_split_drawn_without_a_legend_still_keeps_every_box(self):
        # Nothing names the levels, so the boxes are named by category alone
        # -- twice each. Half a reading, and better than half the boxes.
        figure, ax = plt.subplots()
        sns.boxplot(frame(), x="cat", y="val", hue="grp", legend=False, ax=ax)
        data = schema(figure)["data"]

        assert len(data) == 6
        assert sorted(point["z"] for point in data) == sorted(CATEGORIES * 2)
