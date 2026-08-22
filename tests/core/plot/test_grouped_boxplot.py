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


class TestTheFigureLevelSpelling:
    """`catplot` announces every box across two layers nothing tells apart.

    It registers one layer per `bxp` call, so no box is lost the way the
    axes-level spelling lost three -- but both layers carried the same three
    categories on `z` and no name, so a reader moving between them heard
    a, b, c twice with nothing saying which group either was (#595).

    The name cannot be resolved when the layer registers: `catplot` builds one
    legend at the **figure**, after every panel is drawn, so at registration
    there is none on the axes and none on the figure either. It is deferred
    the way `GROUP_NAME` already is for a `pairplot` (#561).

    `z` keeps the category and `name` says which side of the split the layer
    is -- the division `ScatterPlot.render` documents.
    """

    @staticmethod
    def _medians(data: pd.DataFrame, grp: str) -> list[float]:
        return [
            round(float(np.median(data.val[(data.cat == cat) & (data.grp == grp)])), 9)
            for cat in CATEGORIES
        ]

    def test_each_layer_is_named_for_its_level(self):
        data = frame()
        grid = sns.catplot(data, x="cat", y="val", hue="grp", kind="box")
        layers = [
            (
                plot.schema.get("name"),
                [round(float(point["q2"]), 9) for point in plot.schema["data"]],
            )
            for plot in FigureManager.get_maidr(grid.figure).plots
        ]

        # Checked against the medians rather than registration order, so a
        # name attached to the wrong layer fails rather than passes.
        assert layers == [
            ("p", self._medians(data, "p")),
            ("q", self._medians(data, "q")),
        ]

    def test_a_faceted_grid_names_its_layers_too(self):
        # The legend is figure-level here as well, and the panels are more
        # numerous, so a resolver that read the wrong one would show.
        grid = sns.catplot(frame(), x="cat", y="val", hue="grp", col="grp", kind="box")
        names = [
            plot.schema.get("name")
            for plot in FigureManager.get_maidr(grid.figure).plots
        ]

        assert sorted(name for name in names if name) == LEVELS

    def test_a_grid_with_no_hue_stays_unnamed(self):
        grid = sns.catplot(frame(), x="cat", y="val", kind="box")
        names = [
            plot.schema.get("name")
            for plot in FigureManager.get_maidr(grid.figure).plots
        ]

        assert names == [None]

    def test_a_matplotlib_boxplot_stays_unnamed(self):
        rng = np.random.default_rng(0)
        figure, ax = plt.subplots()
        ax.boxplot([rng.normal(size=20) for _ in range(3)])

        assert schema(figure).get("name") is None

    def test_the_axes_level_spelling_keeps_its_levels_on_z(self):
        # Its boxes reach one layer together, so the level belongs per box
        # rather than to the layer. Naming the layer as well would say the
        # whole of it was one level, which is the opposite of true.
        figure, ax = plt.subplots()
        sns.boxplot(frame(), x="cat", y="val", hue="grp", ax=ax)
        emitted = schema(figure)

        assert emitted.get("name") is None
        assert {str(point["z"]).split(", ")[1] for point in emitted["data"]} == set(
            LEVELS
        )

    def test_a_call_whose_boxes_differ_in_colour_is_not_named(self):
        """A layer holding two levels is neither of them.

        Nothing measured draws one -- `bxp` colours a call's boxes together,
        and the two callers that reach `_level_of` each draw one colour per
        call -- so this is the guard rather than a live path, asserted
        directly because no chart can assert it.
        """
        from matplotlib.patches import PathPatch
        from matplotlib.path import Path as MplPath

        from maidr.patch.boxplot import _level_of

        figure, ax = plt.subplots()
        sns.boxplot(frame(), x="cat", y="val", hue="grp", ax=ax)
        square = MplPath([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        mixed = [
            PathPatch(square, facecolor="red"),
            PathPatch(square, facecolor="blue"),
        ]

        assert _level_of(ax, mixed) is None
        # And one colour, on the same axes and legend, does resolve -- so the
        # decline above is the mixture and not the setup.
        alone = [PathPatch(square, facecolor=mixed[0].get_facecolor())]
        assert callable(_level_of(ax, alone))
