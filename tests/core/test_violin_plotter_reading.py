"""A seaborn violin is read from seaborn's plotter, not from the call (#448, #449).

The old patch sat on ``seaborn.violinplot`` and worked out what had been drawn
by re-reading the caller's keywords. Three readings were wrong for that one
reason, and they get worse in order:

* ``sns.catplot(kind="violin")`` reached no patch at all -- it drives
  ``_CategoricalPlotter`` directly and imports nothing -- so its panel was seen
  only by the matplotlib-level patches and arrived as ``line``. A distribution
  announced as a two-point series (#448).

* ``sns.violinplot(y="g", x="v")``, the spelling seaborn documents for a
  horizontal violin, **raised**::

      TypeError: ufunc 'isnan' not supported for the input types

  out of ``maidr.render()``, and the figure produced no HTML at all. ``orient``
  is None in the keywords when seaborn inferred it, so ``is_horizontal`` was
  False, so the category names were read as the measurements (#449).

* ``sns.violinplot(df, x=..., y=...)`` -- the first-positional signature --
  silently lost its ``violin_box`` layer, because the extractor looked for
  ``data`` in the keywords only. The chart loaded, the density curve read
  correctly, and the five summary statistics a violin exists to carry were not
  there, with nothing saying so (#449).

The fix registers at ``_CategoricalPlotter.plot_violins``, the method every
interface drives, and reads ``plotter.orient``, ``plotter.plot_data`` and
``plotter.var_levels`` -- seaborn's own answers, resolved before it draws.

Most of the file is therefore agreement tests: two interfaces, or two
spellings of one call, describing the same chart the same way. That shape is
what makes these defects legible at all, since none of the wrong readings
looked wrong on its own.
"""

from __future__ import annotations

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import maidr  # noqa: E402  # activates the patches
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.exception import UnsupportedPlotError  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def frame() -> pd.DataFrame:
    """Two categories in each of two panels, so a facet cannot pass by luck."""
    rng = np.random.default_rng(20260816)
    return pd.DataFrame(
        {
            "v": rng.normal(size=60),
            "g": list("ab") * 30,
            "panel": ["x"] * 30 + ["y"] * 30,
        }
    )


def layers(fig=None) -> list[str]:
    """The types registered for a figure, or [] when nothing was."""
    try:
        registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    except UnsupportedPlotError:
        return []
    return [plot.type.value for plot in registered._plots]


def summaries(fig=None) -> list[list[dict]]:
    """The data of every ``violin_box`` layer, keyed by plain strings."""
    registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    return [
        [
            {str(key): value for key, value in sample.items()}
            for sample in plot.schema["data"]
        ]
        for plot in registered._plots
        if plot.type.value == "violin_box"
    ]


def selectors(fig=None) -> list[list[dict]]:
    """The selector sets of every ``violin_box`` layer."""
    registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    return [
        [
            {str(key): value for key, value in one.items()}
            for one in plot.schema["selectors"]
        ]
        for plot in registered._plots
        if plot.type.value == "violin_box"
    ]


def named(fig=None) -> list[str]:
    """The group names of the first ``violin_box`` layer."""
    return [sample["z"] for sample in summaries(fig)[0]]


class TestTheGridThatReachedNoPatch:
    """`catplot` drives the plotter directly, so nothing above it can help."""

    def test_a_catplot_violin_is_a_violin(self):
        # Was `['line']`: seaborn builds the body from a PolyCollection and
        # the inner box from `Axes.plot`, and with no seaborn-level patch on
        # the path those lines were all that registered.
        grid = sns.catplot(frame(), x="g", y="v", kind="violin")

        assert layers(grid.figure) == ["violin_box", "violin_kde"]

    def test_it_agrees_with_the_axes_level_function(self):
        # The two interfaces draw the same chart from the same data, so they
        # should describe it the same way. This is what makes the defect
        # legible: nothing about `catplot`'s reading looked wrong on its own.
        grid = sns.catplot(frame(), x="g", y="v", kind="violin")
        figure_level = summaries(grid.figure)

        plt.close("all")
        _, ax = plt.subplots()
        sns.violinplot(frame(), x="g", y="v", ax=ax)

        assert figure_level == summaries(ax.get_figure())


class TestEveryPanelIsRead:
    """One call to the plotter method covers the whole grid."""

    def test_each_faceted_panel_registers_its_own_pair(self):
        # `plot_violins` is reached *once* for a faceted call and draws both
        # panels, and `plotter.ax` is None in exactly this case -- so a
        # wrapper that read only `ax` would register nothing at all here.
        grid = sns.catplot(frame(), x="g", y="v", col="panel", kind="violin")

        assert layers(grid.figure) == [
            "violin_box",
            "violin_kde",
            "violin_box",
            "violin_kde",
        ]

    def test_a_panel_summarises_only_its_own_rows(self):
        # The half that a layer count cannot catch. Both panels hold both
        # categories, so a wrapper that handed each panel the whole figure's
        # data would still produce four layers -- with the second panel
        # announcing the first panel's medians.
        data = frame()
        grid = sns.catplot(data, x="g", y="v", col="panel", kind="violin")
        first, second = summaries(grid.figure)

        assert [sample["z"] for sample in first] == ["a", "b"]
        assert [sample["z"] for sample in second] == ["a", "b"]

        for panel, read in zip(("x", "y"), (first, second)):
            for sample in read:
                rows = data[(data["panel"] == panel) & (data["g"] == sample["z"])]
                assert sample["q2"] == pytest.approx(rows["v"].median())

        assert first != second


    def test_a_panel_splits_by_hue_within_itself(self):
        # Facets and a hue together, which neither the class above nor
        # `TestTheNamesGroupsAreGiven` covers on its own. `iter_data` groups
        # by facet and `_panel_groups` splits by hue inside each panel, so
        # the two passes have to compose -- and a panel that reused the
        # figure's whole hue cross would still produce the right layer count.
        # Built here rather than from `frame()`, whose `g` and a two-level
        # hue would run in lockstep -- half the cross would simply not exist,
        # and the test would pass on data that never exercised it.
        rng = np.random.default_rng(4488)
        data = pd.DataFrame(
            {
                "v": rng.normal(size=60),
                "g": ["a", "a", "b", "b"] * 15,
                "shade": ["m", "n"] * 30,
                "panel": ["x"] * 30 + ["y"] * 30,
            }
        )
        grid = sns.catplot(
            data, x="g", y="v", hue="shade", col="panel", kind="violin"
        )
        first, second = summaries(grid.figure)

        for read in (first, second):
            assert [sample["z"] for sample in read] == [
                "a_m",
                "a_n",
                "b_m",
                "b_n",
            ]

        for panel, read in zip(("x", "y"), (first, second)):
            for sample in read:
                category, shade = sample["z"].split("_")
                rows = data[
                    (data["panel"] == panel)
                    & (data["g"] == category)
                    & (data["shade"] == shade)
                ]
                assert sample["q2"] == pytest.approx(rows["v"].median())


class TestAHorizontalViolin:
    """The orientation seaborn infers is the one it drew."""

    def test_an_inferred_horizontal_violin_does_not_raise(self):
        # Assigning the categorical variable to `y` is how seaborn documents a
        # horizontal violin; no `orient=` is needed. This raised `TypeError`
        # out of `render`, and the figure emitted no HTML at all.
        _, ax = plt.subplots()
        sns.violinplot(data=frame(), y="g", x="v", ax=ax)

        assert layers(ax.get_figure()) == ["violin_box", "violin_kde"]
        assert "maidr" in str(maidr.render(ax.get_figure()))

    def test_it_is_read_as_horizontal(self):
        _, ax = plt.subplots()
        sns.violinplot(data=frame(), y="g", x="v", ax=ax)
        registered = FigureManager.get_maidr(ax.get_figure())

        assert registered._plots[0].schema["orientation"] == "horz"

    def test_inferring_and_spelling_it_out_agree(self):
        # `orient="h"` always worked, which is why this survived: anyone who
        # wrote the orientation down never saw it.
        _, ax = plt.subplots()
        sns.violinplot(data=frame(), y="g", x="v", orient="h", ax=ax)
        spelled_out = summaries(ax.get_figure())

        plt.close("all")
        _, ax = plt.subplots()
        sns.violinplot(data=frame(), y="g", x="v", ax=ax)

        assert summaries(ax.get_figure()) == spelled_out

    def test_the_measurements_are_the_numbers_not_the_names(self):
        # The mechanism, stated directly. The crash was `np.isnan` being
        # handed an array of category names, because the roles were swapped.
        data = frame()
        _, ax = plt.subplots()
        sns.violinplot(data=data, y="g", x="v", ax=ax)

        for sample in summaries(ax.get_figure())[0]:
            rows = data[data["g"] == sample["z"]]
            assert sample["q2"] == pytest.approx(rows["v"].median())


class TestAPositionalFrame:
    """`sns.violinplot(df, ...)` is seaborn's first-positional signature."""

    def test_the_box_summary_survives(self):
        # Was `['violin_kde']` alone. Nothing warned: the chart loaded and the
        # density curve read correctly, so the missing layer was invisible.
        _, ax = plt.subplots()
        sns.violinplot(frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["violin_box", "violin_kde"]

    def test_it_agrees_with_the_keyword_spelling(self):
        _, ax = plt.subplots()
        sns.violinplot(data=frame(), x="g", y="v", ax=ax)
        by_keyword = summaries(ax.get_figure())

        plt.close("all")
        _, ax = plt.subplots()
        sns.violinplot(frame(), x="g", y="v", ax=ax)

        assert summaries(ax.get_figure()) == by_keyword


class TestTheNamesGroupsAreGiven:
    def test_the_drawn_order_is_the_announced_order(self):
        # `order=` is seaborn's; asking the plotter is what keeps the two in
        # step, where sorting the values would not.
        _, ax = plt.subplots()
        sns.violinplot(data=frame(), x="g", y="v", order=["b", "a"], ax=ax)

        assert named(ax.get_figure()) == ["b", "a"]

    def test_a_hue_joins_its_name_to_the_category(self):
        data = frame()
        _, ax = plt.subplots()
        sns.violinplot(data=data, x="g", y="v", hue="panel", ax=ax)

        assert named(ax.get_figure()) == ["a_x", "a_y", "b_x", "b_y"]

    def test_a_hue_that_is_the_category_is_not_said_twice(self):
        # Colouring a plain violin by its own category is seaborn's own idiom,
        # and would otherwise announce "a_a".
        _, ax = plt.subplots()
        sns.violinplot(data=frame(), x="g", y="v", hue="g", ax=ax)

        assert named(ax.get_figure()) == ["a", "b"]

    def test_two_unnamed_variables_are_not_the_same_variable(self):
        # The other side of that rule, and the case it got wrong. "The hue is
        # the category" means the same *named* column, and `plotter.variables`
        # records None for a bare array -- so comparing the two roles directly
        # made two unnamed variables look like one:
        #
        #     groups: ['a', 'a', 'b', 'b']
        #
        # Four violins, two pairs sharing a name, with nothing telling them
        # apart. Which is the defect this whole file is about, one spelling
        # along: a reading that sounds complete and is not.
        _, ax = plt.subplots()
        sns.violinplot(
            x=["a"] * 12 + ["b"] * 12,
            y=list(range(1, 25)),
            hue=(["p"] * 6 + ["q"] * 6) * 2,
            ax=ax,
        )

        assert named(ax.get_figure()) == ["a_p", "a_q", "b_p", "b_q"]

    def test_a_single_distribution_keeps_its_placeholder_name(self):
        # `sns.violinplot(x=values)` has no categorical variable, and seaborn
        # does not leave the column out -- it invents the axis and fills it
        # with the empty string. Reading that literally names the group "".
        _, ax = plt.subplots()
        sns.violinplot(x=[1.0, 2.0, 3.0, 4.0, 5.0], ax=ax)

        assert named(ax.get_figure()) == ["Violin"]

    def test_bare_lists_of_categories_are_still_groups(self):
        # The other half of the same test: an *unnamed* variable is not an
        # absent one, so this must not collapse to the placeholder.
        _, ax = plt.subplots()
        sns.violinplot(x=list("aabb") * 3, y=[1.0, 2.0, 3.0, 4.0] * 3, ax=ax)

        assert named(ax.get_figure()) == ["a", "b"]


class TestTheInnerBox:
    def test_a_violin_does_not_claim_lines_it_did_not_draw(self):
        # The per-panel snapshot. The old one read `kwargs["ax"]`, so it was
        # empty whenever the caller omitted it -- and a line already on the
        # current axes was then classified as part of the inner box.
        #
        # Measured with one stray marker between the two violins: three
        # selector sets for two groups, and the second violin's median and
        # interquartile selectors gone, so those highlights pointed nowhere.
        #
        #     2 groups, 3 selector sets
        #       [0] z='a' filled=['min', 'iq', 'q2', 'max']
        #       [1] z='b' filled=['min', 'max']
        _, ax = plt.subplots()
        ax.plot([0.5], [0.0], marker="o")
        sns.violinplot(data=frame(), x="g", y="v")

        summary, selector = summaries(plt.gcf())[0], selectors(plt.gcf())[0]

        assert len(selector) == len(summary)
        for one in selector:
            assert all(one.get(key) for key in ("min", "iq", "q2", "max"))

    def test_no_inner_box_means_no_box_layer(self):
        # `inner=None` draws nothing inside the violin, so the box layer's
        # selectors would have nothing to point at.
        _, ax = plt.subplots()
        sns.violinplot(data=frame(), x="g", y="v", inner=None, ax=ax)

        assert layers(ax.get_figure()) == ["violin_kde"]


class TestWhatMustNotChange:
    def test_a_violin_registers_exactly_once(self):
        # The recursion guard, from the other side. `seaborn.violinplot` and
        # the plotter method it drives are both wrapped, and only one of them
        # registers.
        _, ax = plt.subplots()
        sns.violinplot(data=frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["violin_box", "violin_kde"]

    def test_the_matplotlib_violin_is_unchanged(self):
        # `Axes.violinplot` has no seaborn plotter to ask -- it is handed its
        # values positionally -- so that side still reads its own arguments,
        # and `ViolinDataExtractor` is still reached from there.
        _, ax = plt.subplots()
        ax.violinplot([[1.0, 2.0, 3.0, 4.0, 5.0], [2.0, 3.0, 4.0, 5.0, 6.0]])

        assert layers(ax.get_figure()) == ["violin_box", "violin_kde"]

    def test_a_boxplot_on_the_same_axes_is_untouched(self):
        # The neighbouring categorical patch, which reaches `plot_boxes` the
        # same way and must not start declining because this one now sets the
        # internal context one level down.
        _, ax = plt.subplots()
        sns.boxplot(data=frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["box"]

    def test_a_violin_over_a_boxplot_reads_both(self):
        _, ax = plt.subplots()
        sns.boxplot(data=frame(), x="g", y="v", ax=ax)
        sns.violinplot(data=frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["box", "violin_box", "violin_kde"]
