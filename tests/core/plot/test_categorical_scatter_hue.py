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

        # The layers now carry the category each holds (#662). That is not a
        # hue grouping and does not pretend to be one: no `z` axis, which is
        # what a hue-read layer declares and what the declines below assert.
        assert names(figure) == CATEGORIES
        assert [z_label(layer) for layer in layers(figure)] == [None, None, None]
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


class TestTheCategoryEachLayerHolds:
    """
    A layer names the category it is (#662).

    The split into one layer per category is #426's, unchanged. What was
    missing is the name on each: a reader arrowing between layers heard
    "point plot" three times, on a chart whose layers *are* the categories --
    while the same call with a ``hue=`` that changes nothing about the split
    named all three. The name is read off the layer's own points, against the
    same tick lookup ``ScatterPlot`` uses for a point's ``xLabel``, so it is
    the word the chart prints under the strip.
    """

    @pytest.mark.parametrize("plot", ["stripplot", "swarmplot"])
    def test_a_strip_names_the_category_it_draws(self, plot):
        figure, ax = plt.subplots()
        getattr(sns, plot)(data=frame(), x="cat", y="val", ax=ax)

        assert names(figure) == CATEGORIES

    def test_a_horizontal_strip_is_named_too(self):
        # The names are on y here, and asking about x alone was itself the
        # #353 defect -- so both axes are asked.
        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), y="cat", x="val", ax=ax)

        assert names(figure) == CATEGORIES

    def test_a_numerically_grouped_strip_is_named_as_the_chart_labels_it(self):
        # Written the other way round first, expecting no names at all, and
        # the measurement said otherwise. `stripplot` categorises its
        # grouping axis whatever the column's dtype -- `plotter.var_types`
        # reports `'categorical'` for a float column exactly as for a string
        # one -- so seaborn draws one strip per distinct value and labels
        # each tick with the value.
        #
        # The name is that tick, float artefacts and all, because every
        # *point* of these layers already carries the same string on its
        # `xLabel` and the axis already prints it. Declining at the layer
        # while announcing at the point would be an inconsistency, not a
        # safeguard. It is an unlovely chart, and it is unlovely on the page
        # too: the ticks read "0.0", "0.2", "0.6000000000000001".
        figure, ax = plt.subplots()
        sns.stripplot(data=frame().assign(num=[0.0, 0.5, 1.0] * 6), x="num", y="val",
                      ax=ax)

        drawn_ticks = [tick.get_text() for tick in ax.get_xticklabels()]
        assert names(figure) == drawn_ticks
        assert [point["xLabel"] for layer in layers(figure)
                for point in layer["data"][:1]] == drawn_ticks

    def test_a_faceted_panel_names_what_it_holds(self):
        # A `catplot` panel gets its layers the same way, and the panels here
        # hold different categories: "p" has every "a" row and the "b" rows
        # that are level x, "q" has the rest.
        #
        # seaborn gives every panel a collection for every category, so a
        # panel holding none of one gets an empty collection -- which is
        # registered, and which this deliberately does not name. There is no
        # category in it to name it after, and a name read off the axis
        # rather than off the points would announce a strip that was not
        # drawn.
        grid = sns.catplot(data=frame(), x="cat", y="val", col="col", kind="strip")

        emitted = names(grid.figure)
        assert [name for name in emitted if name is not None] == ["a", "b", "b", "c"]
        assert emitted.count(None) == 2
        assert [len(layer["data"]) for layer in layers(grid.figure)
                if layer.get("name") is None] == [0, 0]

    def test_a_collection_spanning_categories_is_not_named_after_one(self):
        # Asked of the reader directly, because no chart reaching this branch
        # produces such a collection: seaborn draws a strip per category
        # whether the hue was read, declined or absent, so every collection
        # the ungrouped path sees holds exactly one. The guard is what keeps
        # that a fact about seaborn rather than an assumption -- a producer
        # that ever handed over a mixed collection would be named after
        # whichever category it drew first.
        from maidr.patch.stripplot import _collection_category

        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", ax=ax)
        # One y, deliberately. x names two categories and is declined for
        # that; y then names exactly one thing -- the number 1.0 -- and is
        # declined because a coordinate is not a name. Two points at
        # different heights would fall out on the count alone and never
        # reach the second refusal.
        spanning = ax.scatter([0.0, 1.0], [1.0, 1.0])

        assert _collection_category(ax, spanning) is None
        assert _collection_category(ax, ax.collections[0]) == "a"

    def test_a_dodged_chart_is_still_named_by_its_levels(self):
        # A hue that reads takes the other branch, and there the name is the
        # level -- the category travels on each point's `xLabel` instead.
        # Two namings, and only one of them can be the layer's.
        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", dodge=True, ax=ax)

        assert names(figure) == LEVELS
        assert [z_label(layer) for layer in layers(figure)] == ["hue", "hue"]


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

        # Asserted on the `z` axis rather than on the names, because the
        # names are the *categories* now (#662) and always were the reading
        # this chart keeps. A hue that was read declares the variable it
        # grouped by; a hue that was declined declares nothing.
        assert [z_label(layer) for layer in layers(figure)] == [None, None, None]
        assert names(figure) == CATEGORIES
        assert [len(layer["data"]) for layer in layers(figure)] == [6, 6, 6]


    @pytest.mark.parametrize(
        "palette",
        [
            pytest.param({"x": (0.0, 0.0, 1.0, 0.3), "y": (0.0, 0.0, 1.0, 0.9)},
                         id="same-hue-different-opacity"),
            pytest.param({"x": "blue", "y": "blue"}, id="the-same-colour-twice"),
        ],
    )
    def test_two_levels_drawn_the_same_colour_are_not_told_apart(self, palette):
        # The levels are matched on their three colour channels, so opacity
        # alone does not separate them -- and a palette that draws two levels
        # the same colour does not separate them at all. Measured: both come
        # out as the ungrouped reading -- three layers, one per category and
        # named for it -- rather than every point of both levels handed to
        # whichever name matched first.
        figure, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", palette=palette, ax=ax)

        assert [z_label(layer) for layer in layers(figure)] == [None, None, None]
        assert names(figure) == CATEGORIES
        assert len(set(announced(figure))) == 18

    def test_a_hue_with_one_level_is_not_a_grouping(self):
        # Nothing to tell apart. A layer named "only" over every point says
        # no more than the category name it would replace -- and the category
        # is the thing these three layers actually differ by (#662).
        figure, ax = plt.subplots()
        sns.stripplot(
            data=frame().assign(one=["only"] * 18), x="cat", y="val", hue="one", ax=ax
        )

        assert [z_label(layer) for layer in layers(figure)] == [None, None, None]
        assert names(figure) == CATEGORIES


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


class TestHowThePointColoursAreRead:
    """
    One conversion per distinct colour, one answer per point (#718).

    ``_point_colours`` used to run ``to_rgba`` on every row, and a collection
    of 50,000 points coloured by a two-level hue is 50,000 calls that return
    two values between them: measured, over a second on top of a 370 ms draw.
    Converting each distinct row once and fanning the result back out is the
    same list, point for point.
    """

    def test_every_point_is_named_as_if_converted_on_its_own(self):
        # Equality against the per-row spelling, on a translucent chart so
        # the rows carry an alpha `to_rgba` has to keep, and on every one of
        # the collections rather than a chosen one.
        from maidr.core.plot.scatterplot import _rgba
        from maidr.patch.stripplot import _point_colours

        _, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", alpha=0.4, ax=ax)

        for collection in ax.collections:
            expected = [_rgba(row) for row in collection.get_facecolor()]
            assert _point_colours(collection) == expected
            assert len(expected) == len(collection.get_offsets())
            # Two levels drawn, so two colours -- the reason the per-distinct
            # conversion is worth having at all.
            assert len(set(expected)) == 2

    def test_a_row_count_that_does_not_match_the_points_still_declines(self):
        # The guard the docstring describes: rows that do not correspond to
        # the points answer `None` per point rather than a colour each,
        # before any conversion happens. Monkeypatched, because seaborn never
        # produces the mismatch (the test above pins that).
        from maidr.patch.stripplot import _point_colours

        _, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", ax=ax)
        collection = ax.collections[0]
        count = len(collection.get_offsets())
        assert count > 1

        # Read once, then patched in: matplotlib's `get_facecolors` alias
        # dispatches back to the instance's `get_facecolor`, so a lambda that
        # called either would be calling itself.
        one_row = collection.get_facecolor()[:1]
        collection.get_facecolor = lambda: one_row

        assert _point_colours(collection) == [None] * count

    def test_each_distinct_colour_is_converted_once(self, monkeypatch):
        # The change itself, pinned by count rather than by clock: a
        # collection of six points in two colours is two conversions, not
        # six. A conversion per point would pass every equality test above
        # and cost the second #718 measured back.
        import maidr.patch.stripplot as stripplot

        _, ax = plt.subplots()
        sns.stripplot(data=frame(), x="cat", y="val", hue="hue", ax=ax)
        collection = ax.collections[0]
        rows = np.asarray(collection.get_facecolor())
        assert len(rows) == 6

        converted = []
        monkeypatch.setattr(
            stripplot, "_rgba", lambda row: converted.append(row) or tuple(row)
        )
        stripplot._point_colours(collection)

        assert len(converted) == len(np.unique(rows, axis=0)) == 2


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
