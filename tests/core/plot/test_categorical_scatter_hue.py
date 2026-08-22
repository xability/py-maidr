"""A hue-grouped strip or swarm plot reads by hue level (#586).

``sns.stripplot(..., hue=...)`` emitted exactly the schema of the same call
without a ``hue=``: three layers, one per *category*, unnamed, with nothing
anywhere saying which points belonged to which group. Not a wrong grouping --
no grouping at all, on a chart whose whole subject is the comparison between
the levels.

The cause was where the reading happened rather than what it read. These
charts registered at the inner ``Axes.scatter`` calls seaborn makes, one per
category, and ``hue_groups`` needs the per-point colours and the legend, both
of which ``plot_strips`` writes *after* those calls return::

    points = ax.scatter(...)
    if "hue" in self.variables:
        points.set_facecolors(self._hue_map(sub_data["hue"]))
    ...
    self._configure_legend(...)

Measured at each of the three returns: one uniform colour, no legend.

``maidr/patch/stripplot.py`` moves the decision to the plotter method, which
``sns.catplot`` drives as well, and reads the grouping off the plotter's own
``_hue_map`` rather than off a legend that a faceted grid does not give a
panel. The layers a grouped chart gets are one per hue level, spanning the
categories -- the decomposition ``scatterplot(hue=)`` already emits (#544),
with the category on each point's ``xLabel``.

The ungrouped chart is untouched: one layer per category, which is what #426
settled and what ``test_scatter_own_collection.py`` pins.
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

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

CATEGORIES = ["a", "b", "c"]
LEVELS = ["x", "y"]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def frame() -> pd.DataFrame:
    """Three categories, two hue levels, three rows in each combination."""
    return pd.DataFrame(
        {
            "cat": [category for category in CATEGORIES for _ in range(6)],
            "val": list(range(18)),
            "hue": (["x"] * 3 + ["y"] * 3) * 3,
            # Two panels that hold different levels: "p" has every "a" row and
            # the "b" rows that are level x, "q" has the rest.
            "col": ["p"] * 9 + ["q"] * 9,
        }
    )


def layers(figure) -> list[dict]:
    return [plot.schema for plot in FigureManager.get_maidr(figure)._plots]


def names(figure) -> list:
    return [layer.get("name") for layer in layers(figure)]


def points(layer: dict) -> list[tuple[float, float]]:
    return [(float(point["x"]), float(point["y"])) for point in layer["data"]]


def drawn(ax) -> set[tuple[float, float]]:
    return {
        (round(float(x), 9), round(float(y), 9))
        for collection in ax.collections
        for x, y in collection.get_offsets()
    }


def announced(figure) -> list[tuple[float, float]]:
    return [
        (round(x, 9), round(y, 9))
        for layer in layers(figure)
        for x, y in points(layer)
    ]


def z_label(layer: dict):
    axis = (layer.get("axes") or {}).get("z")
    return None if axis is None else axis.get("label")


@pytest.mark.parametrize("plot", ["stripplot", "swarmplot"])
class TestAHueGroupedCategoricalScatter:
    def test_the_layers_are_the_hue_levels_not_the_categories(self, plot):
        # The defect's signature: three layers for three categories, with the
        # two levels nowhere in the schema.
        figure, ax = plt.subplots()
        getattr(sns, plot)(data=frame(), x="cat", y="val", hue="hue", ax=ax)

        assert names(figure) == LEVELS

    def test_each_level_spans_every_category(self, plot):
        # The point of grouping by level rather than by category: a reader
        # moving through one layer compares the same level across the chart,
        # which is the comparison the hue was drawn for.
        figure, ax = plt.subplots()
        getattr(sns, plot)(data=frame(), x="cat", y="val", hue="hue", ax=ax)

        for layer in layers(figure):
            assert len(layer["data"]) == 9
            assert {point["xLabel"] for point in layer["data"]} == set(CATEGORIES)

    def test_every_drawn_point_is_announced_exactly_once(self, plot):
        # Stronger than "the layers are named": splitting by colour could
        # drop a point no swatch claims, or double one claimed by two.
        figure, ax = plt.subplots()
        getattr(sns, plot)(data=frame(), x="cat", y="val", hue="hue", ax=ax)
        found = announced(figure)

        assert len(found) == 18
        assert len(set(found)) == 18
        assert {y for _, y in found} == {y for _, y in drawn(ax)}

    def test_the_hue_variable_is_named_on_z(self, plot):
        # `z` says what the split is by and `name` says which side of it this
        # layer is; a group called "x" with nothing saying what "x" is a kind
        # of is half a reading.
        figure, ax = plt.subplots()
        getattr(sns, plot)(data=frame(), x="cat", y="val", hue="hue", ax=ax)

        assert [z_label(layer) for layer in layers(figure)] == ["hue", "hue"]

    def test_a_chart_with_no_hue_still_reads_one_layer_per_category(self, plot):
        # #426's shape, unchanged. Registration moved to the plotter method
        # for every one of these charts, not only the grouped ones, so the
        # ungrouped path is as much a part of this as the grouped one.
        figure, ax = plt.subplots()
        getattr(sns, plot)(data=frame(), x="cat", y="val", ax=ax)

        assert names(figure) == [None, None, None]
        assert [len(layer["data"]) for layer in layers(figure)] == [6, 6, 6]
        assert len(set(announced(figure))) == 18


class TestTheShapesTheGroupingSurvives:
    def test_a_dodged_chart_groups_by_level_too(self):
        # `dodge=True` splits each category into one collection per level, so
        # every collection is uniformly coloured and the legend-based split
        # declines for a second reason. The hue map does not care.
        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", dodge=True, ax=ax)

        assert names(figure) == LEVELS
        assert [len(layer["data"]) for layer in layers(figure)] == [9, 9]

    def test_a_translucent_chart_is_still_named(self):
        # `alpha=` scales the drawn points' opacity and leaves the hue map's
        # alone -- measured, (0.12, 0.47, 0.71, 0.4) drawn against a lookup
        # entry of (..., 1.0) -- so the match is on the three colour channels.
        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", alpha=0.4, ax=ax)

        assert names(figure) == LEVELS

    def test_a_chart_drawn_without_a_legend_is_still_named(self):
        # The names come from the plotter's mapping, so suppressing the
        # legend hides the grouping from sighted readers and from nobody else.
        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", legend=False, ax=ax)

        assert names(figure) == LEVELS
        assert [z_label(layer) for layer in layers(figure)] == ["hue", "hue"]

    def test_a_chart_on_its_side_groups_the_same_way(self):
        # The categories move to `y` and the levels do not move at all.
        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), y="cat", x="val", hue="hue", ax=ax)

        assert names(figure) == LEVELS
        for layer in layers(figure):
            assert {point["yLabel"] for point in layer["data"]} == set(CATEGORIES)

    def test_a_hue_that_repeats_the_category_names_the_categories(self):
        # seaborn draws this one with a titleless legend, so the variable's
        # name has to come from the plotter as well. Nothing is lost: the
        # layers were one per category before and still are, now named.
        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="cat", ax=ax)

        assert names(figure) == CATEGORIES
        assert [z_label(layer) for layer in layers(figure)] == ["cat"] * 3


class TestWhatIsDeclined:
    def test_a_continuous_hue_is_not_a_grouping(self):
        # seaborn gives a numeric `hue=` one "level" per distinct value --
        # eighteen of them here -- which is a colour scale. One layer per
        # point is not a reading of it, so the chart keeps the reading it had.
        figure, ax = plt.subplots()
        sns.stripplot(
            data=frame().assign(num=np.linspace(0, 1, 18)),
            x="cat",
            y="val",
            hue="num",
            ax=ax,
        )

        assert names(figure) == [None, None, None]
        assert [len(layer["data"]) for layer in layers(figure)] == [6, 6, 6]


    def test_a_hue_with_one_level_is_not_a_grouping(self):
        # Nothing to tell apart. A layer named "only" over every point says
        # no more than the unnamed one it would replace.
        figure, ax = plt.subplots()
        sns.stripplot(
            data=frame().assign(one=["only"] * 18), x="cat", y="val", hue="one", ax=ax
        )

        assert names(figure) == [None, None, None]


class TestTheOrderAndTheNeighbours:
    def test_the_layers_follow_the_hue_order_not_the_drawing_order(self):
        # #502 settled that a grouped layer's layers come out in the order the
        # chart names its levels, not the order the rows happen to arrive in.
        # This frame's first row is level "x", so a reading that kept the
        # drawing order would put "x" first under either `hue_order`.
        figure, ax = plt.subplots()
        sns.stripplot(
            data=frame(), x="cat", y="val", hue="hue", hue_order=["y", "x"], ax=ax
        )

        assert names(figure) == ["y", "x"]

    def test_a_scatter_already_on_the_axes_is_left_to_its_own_layer(self):
        # The panel is read by what this call *added* to it. Reading every
        # collection instead would fold a neighbouring scatter into the strip
        # plot's groups, or -- worse -- decline the grouping because that
        # scatter's colour matches no hue level.
        figure, ax = plt.subplots()
        ax.scatter([0.5], [30])
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", ax=ax)

        assert names(figure) == [None, "x", "y"]
        assert [len(layer["data"]) for layer in layers(figure)] == [1, 9, 9]


class TestTheFacetedAndFigureLevelInterfaces:
    @pytest.mark.parametrize("kind", ["strip", "swarm"])
    def test_catplot_reads_the_same_as_the_function(self, kind):
        # `catplot` drives the plotter directly and imports neither public
        # function, so a patch on `seaborn.stripplot` would have reached two
        # of the three ways in and left this one behind.
        grid = sns.catplot(data=frame(), x="cat", y="val", hue="hue", kind=kind)

        assert names(grid.figure) == LEVELS
        assert [len(layer["data"]) for layer in layers(grid.figure)] == [9, 9]

    def test_each_panel_names_only_the_levels_it_holds(self):
        # A faceted grid has no per-panel legend at all -- it builds one at
        # the figure, after the panels are drawn -- and a panel that holds
        # one level would not be nameable from a legend anyway.
        grid = sns.catplot(
            data=frame(), x="cat", y="val", hue="hue", col="col", kind="strip"
        )
        found = [(layer.get("name"), len(layer["data"])) for layer in layers(grid.figure)]

        # Panel "p": six x rows (a and b), three y rows (a).
        # Panel "q": three x rows (c), six y rows (b and c).
        assert found == [("x", 6), ("y", 3), ("x", 3), ("y", 6)]
        assert {z_label(layer) for layer in layers(grid.figure)} == {"hue"}


class TestTheAssumptionTheGroupingRestsOn:
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(
                lambda data: sns.stripplot(data=data, x="cat", y="val", hue="hue"),
                id="strip",
            ),
            pytest.param(
                lambda data: sns.swarmplot(data=data, x="cat", y="val", hue="hue"),
                id="swarm",
            ),
            pytest.param(
                lambda data: sns.stripplot(
                    data=data, x="cat", y="val", hue="hue", dodge=True
                ),
                id="dodged",
            ),
            pytest.param(
                lambda data: sns.stripplot(
                    data=data, x="cat", y="val", hue="hue", alpha=0.4
                ),
                id="translucent",
            ),
            pytest.param(
                lambda data: sns.stripplot(
                    data=data, x="cat", y="val", hue="hue", marker="x"
                ),
                id="unfilled-marker",
            ),
            pytest.param(
                lambda data: sns.catplot(
                    data=data, x="cat", y="val", hue="hue", col="col", kind="strip"
                ),
                id="faceted",
            ),
        ],
    )
    def test_seaborn_gives_every_point_its_own_colour(self, call):
        # The whole grouping rests on this: a point's colour is what says
        # which level it belongs to, so `get_facecolor` has to answer a row
        # per point rather than the one row a uniformly styled collection
        # would give. Seaborn assigns them in a single `set_facecolors` call
        # over each panel's rows, which is why it holds -- including for the
        # empty collections a faceted grid leaves, which have neither rows
        # nor points.
        #
        # `_point_colours` declines a collection where the counts disagree,
        # and that branch is unreachable while this passes. It is pinned here
        # rather than left implicit so the release that ends it fails loudly.
        call(frame())

        for axes in plt.gcf().axes:
            for collection in axes.collections:
                rows = len(np.asarray(collection.get_facecolor()))
                assert rows == len(np.asarray(collection.get_offsets()))


class TestHighlighting:
    def test_each_point_is_addressed_by_an_element_of_its_own(self):
        # A group spans several collections, so its selectors have to name
        # each through that collection's own id. One selector resolving to
        # two elements, or two resolving to one, is a highlight on a point
        # whose value is not being announced -- the failure nothing said
        # aloud can catch.
        pytest.importorskip("lxml")
        from lxml import etree
        from lxml.cssselect import CSSSelector

        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", ax=ax)
        html = maidr.render(figure)._repr_html_()

        svg = re.search(r"<svg.*?</svg>", html, re.S)
        assert svg is not None
        root = etree.fromstring(svg.group(0).encode(), etree.XMLParser(recover=True))
        for element in root.iter():
            if isinstance(element.tag, str) and "}" in element.tag:
                element.tag = element.tag.split("}", 1)[1]

        matched = []
        for layer in layers(figure):
            selectors = layer["selectors"]
            assert len(selectors) == len(layer["data"])
            for selector in selectors:
                found = CSSSelector(selector)(root)
                assert len(found) == 1
                matched.append(found[0])

        assert len({id(element) for element in matched}) == 18
