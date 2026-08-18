"""`sns.catplot(kind="point")` dropped the intervals and kept the means (#448).

The quietest of the `catplot` kinds, and the one most likely to be believed.
`catplot` drives `_CategoricalPlotter` directly and imports nothing, so its
panels reached neither name `wrap_seaborn` patches and were left to the
`Axes.plot` wrapper:

    sns.catplot(df, x="g", y="v", kind="point")   line(3)
    sns.pointplot(df, x="g", y="v", ax=ax)        error_bar(3)

Both readings carry three estimates and both are correct about them. What the
`line` reading has no room for is `yMin`/`yMax` -- the confidence intervals
#246 added, and the thing a point plot exists to show. A reader was handed
three means with nothing saying the chart draws intervals around them, so the
loss is not audible: an interval-free reading of a chart that has intervals
sounds exactly like a correct reading of a chart that does not.

The fix registers at `_CategoricalPlotter.plot_points`, the method both
interfaces drive, through the same `_register_point_layer` the axes-level
patch uses -- so the estimate/interval split, its verification, and every
fallback it takes are shared rather than reimplemented. Those are covered by
`tests/core/plot/test_pointplot.py`; this file is about which interfaces reach
them, and about the per-panel handover a grid needs.
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
    """Three categories in each of two panels, with different means."""
    rng = np.random.default_rng(20260816)
    return pd.DataFrame(
        {
            "v": np.concatenate(
                [rng.normal(shift, 1, 30) for shift in (0, 2, 5, 1, 4, 8)]
            ),
            "g": list(np.repeat(list("abc"), 30)) * 2,
            "panel": ["x"] * 90 + ["y"] * 90,
        }
    )


def layers(fig=None) -> list[str]:
    """The types registered for a figure, or [] when nothing was."""
    try:
        registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    except UnsupportedPlotError:
        return []
    return [plot.type.value for plot in registered._plots]


def estimates(fig=None) -> list[list[dict]]:
    """The data of every ``error_bar`` layer, keyed by plain strings.

    The samples are keyed by ``MaidrKey`` members rather than by strings.
    ``MaidrKey`` subclasses ``str``, so a lookup by ``"y"`` finds them anyway,
    but ``str(MaidrKey.Y)`` is ``"MaidrKey.Y"`` -- so the value is what makes
    a readable dict, not the member.
    """
    registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    return [
        [
            {getattr(key, "value", key): value for key, value in sample.items()}
            for sample in plot.schema["data"]
        ]
        for plot in registered._plots
        if plot.type.value == "error_bar"
    ]


class TestTheGridThatReachedNoPatch:
    def test_a_catplot_point_carries_its_intervals(self):
        grid = sns.catplot(frame(), x="g", y="v", kind="point")

        assert layers(grid.figure) == ["error_bar"]

    def test_it_agrees_with_the_axes_level_function(self):
        # The two interfaces draw the same chart from the same data, so they
        # should describe it the same way. This is what makes the defect
        # legible: three means and no intervals sounds complete on its own.
        #
        # `seed=0` because seaborn's default interval is a *bootstrapped* 95%
        # CI, so two calls on one frame draw slightly different bounds -- a
        # property of the chart rather than of the reading, and one that would
        # otherwise make this compare resampling noise.
        grid = sns.catplot(frame(), x="g", y="v", kind="point", seed=0)
        figure_level = estimates(grid.figure)

        plt.close("all")
        _, ax = plt.subplots()
        sns.pointplot(frame(), x="g", y="v", seed=0, ax=ax)

        assert figure_level == estimates(ax.get_figure())

    def test_every_estimate_is_bracketed(self):
        # The half a type name does not prove. `error_bar` with no bounds on
        # it would be the same loss under a better label.
        grid = sns.catplot(frame(), x="g", y="v", kind="point")

        for sample in estimates(grid.figure)[0]:
            assert {"yMin", "yMax"} <= set(sample)
            assert sample["yMin"] < sample["y"] < sample["yMax"]

    def test_the_estimates_are_the_group_means(self):
        # A bracketed reading assembled from the wrong artists would still
        # look bracketed. Checked against the data seaborn was given.
        data = frame()
        grid = sns.catplot(data, x="g", y="v", kind="point")

        for sample in estimates(grid.figure)[0]:
            rows = data.loc[data["g"] == sample["x"], "v"]
            assert sample["y"] == pytest.approx(rows.mean(), abs=1e-6)


class TestEveryPanelIsRead:
    """One call to the plotter method covers the whole grid."""

    def test_each_faceted_panel_registers_a_layer(self):
        # `plot_points` is reached *once* for a faceted call and draws both
        # panels, and `plotter.ax` is None in exactly this case -- so a
        # wrapper that read only `ax` would register nothing at all here.
        grid = sns.catplot(frame(), x="g", y="v", col="panel", kind="point")

        assert layers(grid.figure) == ["error_bar", "error_bar"]

    def test_a_panel_estimates_only_its_own_rows(self):
        # Both panels hold all three categories, so a wrapper that handed
        # every panel the same lines would still produce two layers -- with
        # the second announcing the first panel's means.
        data = frame()
        grid = sns.catplot(data, x="g", y="v", col="panel", kind="point")
        first, second = estimates(grid.figure)

        for panel, read in zip(("x", "y"), (first, second)):
            for sample in read:
                rows = data[(data["panel"] == panel) & (data["g"] == sample["x"])]
                assert sample["y"] == pytest.approx(rows["v"].mean(), abs=1e-6)

        assert first != second

    def test_a_faceted_grid_still_renders(self):
        grid = sns.catplot(frame(), x="g", y="v", col="panel", kind="point")

        assert "maidr" in str(maidr.render(grid.figure))


class TestWhatMustNotChange:
    def test_a_pointplot_registers_exactly_once(self):
        # The recursion guard, from the other side. `seaborn.pointplot` and
        # the plotter method it drives are both wrapped, and only one of them
        # registers.
        _, ax = plt.subplots()
        sns.pointplot(frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["error_bar"]

    def test_the_interval_polylines_stay_suppressed(self):
        # What #246 removed: seaborn draws the intervals as ordinary lines,
        # so the generic wrapper described them as series of their own, cap
        # geometry and NaN coordinates included. Registration moved one level
        # down and the internal context moved with it -- if it had not, those
        # would be back alongside the `error_bar`.
        _, ax = plt.subplots()
        sns.pointplot(frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["error_bar"]

    def test_a_chart_with_no_intervals_is_still_a_line(self):
        # `errorbar=None` draws none, so there is nothing for an `error_bar`
        # layer to carry and `line` is the honest type.
        _, ax = plt.subplots()
        sns.pointplot(frame(), x="g", y="v", errorbar=None, ax=ax)

        assert layers(ax.get_figure()) == ["line"]

    def test_a_hue_split_keeps_its_intervals(self):
        # This used to pin the opposite -- `["line"]` -- because the error bar
        # layer carried a single flat series with no field naming the group,
        # so a hued chart's intervals were dropped rather than mis-assigned.
        # maidr 4.4.0 gave the grammar a grouped shape and the fallback went
        # with it (#462). Pinned here so that the registration `catplot`
        # shares does not quietly diverge from the axes-level function's.
        _, ax = plt.subplots()
        sns.pointplot(frame(), x="g", y="v", hue="panel", ax=ax)

        assert layers(ax.get_figure()) == ["error_bar"]

    def test_a_point_plot_does_not_claim_lines_it_did_not_draw(self):
        # The per-panel snapshot. An estimate taken from another chart is
        # worse than no layer at all, and `_split` would take a plain line
        # with a marker on it for one.
        _, ax = plt.subplots()
        ax.plot([0, 1, 2], [9.0, 9.0, 9.0], marker="o")
        sns.pointplot(frame(), x="g", y="v", ax=ax)

        for sample in estimates(ax.get_figure())[0]:
            assert sample["y"] != pytest.approx(9.0)
