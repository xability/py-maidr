"""`sns.catplot(kind="boxen")` announced the scaffolding, again (#448).

#253 replaced that reading for `sns.boxenplot`: a letter-value plot is not
drawn by a renderer of its own, so left to the matplotlib-level patches it
arrived as a line layer of medians plus a scatter layer of outliers, with every
rung of every ladder absent. `catplot` never got the fix, because it drives
`_CategoricalPlotter` directly and imports nothing -- so the same chart, drawn
through the figure-level interface, still read as the thing #253 was filed
about:

    sns.catplot(df, x="g", y="v", kind="boxen")    line(2), point(16), point(16)
    sns.boxenplot(df, x="g", y="v", ax=ax)         boxen(2)

The line series are the median segments, each announced as a two-sample
series, so the chart calls itself a line chart and says each median twice. The
point layers hold the outliers alone, positioned at numeric slots rather than
at the category names -- fourteen values out of four hundred, announced as
though they were the data.

The fix registers at `_CategoricalPlotter.plot_boxens`, the method both
interfaces drive, which is the idiom `maidr/patch/boxplot.py` uses for
`plot_boxes` and #446 used for `_DistributionPlotter`.

The ladder's own contents are covered by `tests/core/plot/test_boxenplot.py`
against `np.percentile`; this file is about which interfaces reach that
reading, and about the per-panel handover a grid needs.
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
    """Two categories in each of two panels, with distinct distributions.

    Large enough to give a boxen something to be: the depth is the point, and
    a handful of observations produces a ladder no deeper than a box plot's.
    """
    rng = np.random.default_rng(20260816)
    return pd.DataFrame(
        {
            "v": np.concatenate(
                [
                    rng.normal(0, 1, 100),
                    rng.normal(2, 1.5, 100),
                    rng.normal(5, 1, 100),
                    rng.normal(9, 1.5, 100),
                ]
            ),
            "g": ["a"] * 100 + ["b"] * 100 + ["a"] * 100 + ["b"] * 100,
            "panel": ["x"] * 200 + ["y"] * 200,
        }
    )


def layers(fig=None) -> list[str]:
    """The types registered for a figure, or [] when nothing was."""
    try:
        registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    except UnsupportedPlotError:
        return []
    return [plot.type.value for plot in registered._plots]


def ladders(fig=None) -> list[list[dict]]:
    """The data of every ``boxen`` layer, keyed by plain strings."""
    registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    return [
        [
            {str(key): value for key, value in sample.items()}
            for sample in plot.schema["data"]
        ]
        for plot in registered._plots
        if plot.type.value == "boxen"
    ]


class TestTheGridThatReachedNoPatch:
    def test_a_catplot_boxen_is_a_boxen(self):
        grid = sns.catplot(frame(), x="g", y="v", kind="boxen")

        assert layers(grid.figure) == ["boxen"]

    def test_it_agrees_with_the_axes_level_function(self):
        # The two interfaces draw the same chart from the same data, so they
        # should describe it the same way -- rungs, median, outliers and all.
        grid = sns.catplot(frame(), x="g", y="v", kind="boxen")
        figure_level = ladders(grid.figure)

        plt.close("all")
        _, ax = plt.subplots()
        sns.boxenplot(frame(), x="g", y="v", ax=ax)

        assert figure_level == ladders(ax.get_figure())

    def test_the_rungs_are_the_quantiles_seaborn_computed(self):
        # What the old reading had none of. A ladder assembled from the
        # scaffolding would still look like a ladder; checking it against
        # `np.percentile` is how a read one is told from an invented one.
        data = frame()
        grid = sns.catplot(data, x="g", y="v", kind="boxen")

        for ladder in ladders(grid.figure)[0]:
            values = data.loc[data["g"] == ladder["z"], "v"].to_numpy()
            # The innermost rung is the quartile pair; every letter-value
            # ladder starts from the middle half, whatever its depth.
            quartiles = ladder["levels"][-1]

            assert quartiles["p"] == 0.25
            assert quartiles["lo"] == pytest.approx(float(np.percentile(values, 25)))
            assert quartiles["hi"] == pytest.approx(float(np.percentile(values, 75)))
            assert ladder["median"] == pytest.approx(float(np.median(values)), abs=1e-6)


class TestEveryPanelIsRead:
    """One call to the plotter method covers the whole grid."""

    def test_each_faceted_panel_registers_a_ladder(self):
        # `plot_boxens` is reached *once* for a faceted call and draws both
        # panels, and `plotter.ax` is None in exactly this case -- so a
        # wrapper that read only `ax` would register nothing at all here.
        grid = sns.catplot(frame(), x="g", y="v", col="panel", kind="boxen")

        assert layers(grid.figure) == ["boxen", "boxen"]

    def test_a_panel_is_built_from_its_own_collections(self):
        # The half a layer count cannot catch. Both panels hold both
        # categories, so a wrapper that handed every panel the collections of
        # the whole figure would still produce two layers -- with the second
        # panel announcing four ladders, or the first panel's.
        data = frame()
        grid = sns.catplot(data, x="g", y="v", col="panel", kind="boxen")
        first, second = ladders(grid.figure)

        assert [ladder["z"] for ladder in first] == ["a", "b"]
        assert [ladder["z"] for ladder in second] == ["a", "b"]

        for panel, read in zip(("x", "y"), (first, second)):
            for ladder in read:
                rows = data[(data["panel"] == panel) & (data["g"] == ladder["z"])]
                assert ladder["median"] == pytest.approx(
                    np.median(rows["v"].to_numpy()), abs=1e-6
                )

    def test_a_faceted_grid_still_renders(self):
        grid = sns.catplot(frame(), x="g", y="v", col="panel", kind="boxen")

        assert "maidr" in str(maidr.render(grid.figure))


class TestWhatMustNotChange:
    def test_a_boxenplot_registers_exactly_once(self):
        # The recursion guard, from the other side. `seaborn.boxenplot` and
        # the plotter method it drives are both wrapped, and only one of them
        # registers.
        _, ax = plt.subplots()
        sns.boxenplot(frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["boxen"]

    def test_the_medians_and_fliers_stay_suppressed(self):
        # The scaffolding #253 removed. Registration moved one level down, and
        # the internal context moved with it -- if it had not, the `line` and
        # `point` layers this replaced would be back alongside the `boxen`.
        _, ax = plt.subplots()
        sns.boxenplot(frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["boxen"]

    def test_a_horizontal_boxen_is_unchanged(self):
        _, ax = plt.subplots()
        sns.boxenplot(frame(), y="g", x="v", ax=ax)

        assert layers(ax.get_figure()) == ["boxen"]
        assert [ladder["z"] for ladder in ladders(ax.get_figure())[0]] == ["a", "b"]

    def test_a_hue_split_still_names_both_dimensions(self):
        _, ax = plt.subplots()
        sns.boxenplot(frame(), x="g", y="v", hue="panel", ax=ax)

        assert [ladder["z"] for ladder in ladders(ax.get_figure())[0]] == [
            "a, x",
            "a, y",
            "b, x",
            "b, y",
        ]

    def test_a_boxplot_on_the_same_axes_is_untouched(self):
        # The neighbouring categorical patch, which reaches `plot_boxes` the
        # same way and must not start declining because this one now sets the
        # internal context one level down.
        _, ax = plt.subplots()
        sns.boxplot(frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["box"]
