"""`sns.catplot(kind="bar")` named a grouped chart and drew a phantom (#448).

`catplot` drives `_CategoricalPlotter` directly and imports nothing, so its
panels reached neither name `wrap_seaborn` patches and were read by the
matplotlib-level ones alone:

    sns.catplot(df, x="g", y="v", kind="bar")     dodged_bar(3), line(2)
    sns.barplot(df, x="g", y="v", ax=ax)          bar(3)

Two things wrong, and both follow from `Axes.bar` being asked a question it
cannot answer.

**The type.** `dodged_bar` names a chart that compares groups side by side. A
chart with no hue is not one, so the reader is oriented to a chart that is not
there -- told to expect a second dimension, and given a flat series. Seaborn
does not forward `hue` or `dodge` to `Axes.bar`, so the matplotlib patch has to
infer grouping from bar widths and positions, and on seaborn's output it
inferred wrong.

**The phantom layer.** The `line(2)` is the error-bar geometry travelling as a
two-sample series of its own -- the #440 shape, where a `line` layer describes
another chart's scaffolding. The axes-level patch suppresses it by drawing
inside the internal context; nothing did that here.

`kind="count"` is the same defect with only the type half, since a count plot
draws no intervals.

The fix registers at `_CategoricalPlotter.plot_bars`, the method every
interface drives, using the same `_seaborn_bar_type` classifier -- which asks
the drawn containers rather than the arguments, because whether a hue splits
the layer is seaborn's decision and `dodge` defaults to `"auto"`.
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


def bars(fig=None) -> list[list[dict]]:
    """The data of every bar layer, keyed by plain strings.

    ``MaidrKey`` subclasses ``str``, so a lookup by ``"y"`` finds a sample
    keyed by the member -- but ``str(MaidrKey.Y)`` is ``"MaidrKey.Y"``, so the
    value is what makes a readable dict.
    """
    registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    return [
        [
            {getattr(key, "value", key): value for key, value in sample.items()}
            for sample in plot.schema["data"]
        ]
        for plot in registered._plots
        if plot.type.value in ("bar", "dodged_bar")
    ]


class TestTheGridThatReachedNoPatch:
    def test_a_catplot_bar_is_a_plain_bar_chart(self):
        # Was `['dodged_bar', 'line']`.
        grid = sns.catplot(frame(), x="g", y="v", kind="bar")

        assert layers(grid.figure) == ["bar"]

    def test_a_catplot_count_is_a_plain_bar_chart(self):
        grid = sns.catplot(frame(), x="g", kind="count")

        assert layers(grid.figure) == ["bar"]

    @pytest.mark.parametrize("kind", ["bar", "count"])
    def test_it_agrees_with_the_axes_level_function(self, kind):
        # The two interfaces draw the same chart from the same data, so they
        # should describe it the same way.
        variables = {"x": "g"} if kind == "count" else {"x": "g", "y": "v"}
        grid = sns.catplot(frame(), kind=kind, **variables)
        figure_level = bars(grid.figure)

        plt.close("all")
        _, ax = plt.subplots()
        axes_level = "countplot" if kind == "count" else "barplot"
        getattr(sns, axes_level)(frame(), ax=ax, **variables)

        assert figure_level == bars(ax.get_figure())

    def test_the_error_bar_geometry_is_not_a_series(self):
        # The phantom. Seaborn draws the intervals as ordinary lines, so
        # without the internal context they arrived as a two-sample `line`
        # layer of their own -- cap geometry announced as data.
        grid = sns.catplot(frame(), x="g", y="v", kind="bar")

        assert "line" not in layers(grid.figure)

    def test_the_heights_are_the_group_means(self):
        data = frame()
        grid = sns.catplot(data, x="g", y="v", kind="bar")

        for sample in bars(grid.figure)[0]:
            rows = data.loc[data["g"] == sample["x"], "v"]
            assert sample["y"] == pytest.approx(rows.mean(), abs=1e-6)


class TestEveryPanelIsRead:
    """One call to the plotter method covers the whole grid."""

    def test_each_faceted_panel_registers_a_layer(self):
        # `plot_bars` is reached *once* for a faceted call and draws both
        # panels, and `plotter.ax` is None in exactly this case -- so a
        # wrapper that read only `ax` would register nothing at all here.
        grid = sns.catplot(frame(), x="g", y="v", col="panel", kind="bar")

        assert layers(grid.figure) == ["bar", "bar"]

    def test_a_panel_reports_only_its_own_bars(self):
        data = frame()
        grid = sns.catplot(data, x="g", y="v", col="panel", kind="bar")
        first, second = bars(grid.figure)

        for panel, read in zip(("x", "y"), (first, second)):
            for sample in read:
                rows = data[(data["panel"] == panel) & (data["g"] == sample["x"])]
                assert sample["y"] == pytest.approx(rows["v"].mean(), abs=1e-6)

        assert first != second

    def test_a_panel_missing_a_category_is_still_read(self):
        # Facets are rarely balanced. A panel that holds two of the three
        # categories draws two bars, and must be described as the chart it is
        # rather than measured against the figure's category list.
        data = frame()
        sparse = data[~((data["panel"] == "y") & (data["g"] == "c"))]
        grid = sns.catplot(sparse, x="g", y="v", col="panel", kind="bar")

        assert layers(grid.figure) == ["bar", "bar"]
        assert [len(read) for read in bars(grid.figure)] == [3, 2]

    def test_a_faceted_grid_still_renders(self):
        grid = sns.catplot(frame(), x="g", y="v", col="panel", kind="bar")

        assert "maidr" in str(maidr.render(grid.figure))


class TestWhenItIsGroupedItSaysSo:
    def test_a_hue_split_is_a_grouped_bar_chart(self):
        # The type correction has to cut both ways: naming every chart `bar`
        # would trade one wrong answer for another.
        grid = sns.catplot(frame(), x="g", y="v", hue="panel", kind="bar")

        assert layers(grid.figure) == ["dodged_bar"]

    def test_a_hue_that_repeats_the_category_is_not_grouped(self):
        # Seaborn's own idiom for colouring a plain bar chart: it draws one
        # container per level, each holding a single bar, and wears a legend.
        # Nothing about that is a second dimension for a reader to navigate.
        grid = sns.catplot(frame(), x="g", y="v", hue="g", kind="bar")

        assert layers(grid.figure) == ["bar"]


class TestWhatMustNotChange:
    def test_a_barplot_registers_exactly_once(self):
        _, ax = plt.subplots()
        sns.barplot(frame(), x="g", y="v", ax=ax)

        assert layers(ax.get_figure()) == ["bar"]

    def test_a_countplot_registers_exactly_once(self):
        _, ax = plt.subplots()
        sns.countplot(frame(), x="g", ax=ax)

        assert layers(ax.get_figure()) == ["bar"]

    def test_a_horizontal_bar_is_unchanged(self):
        _, ax = plt.subplots()
        sns.barplot(frame(), y="g", x="v", ax=ax)

        assert layers(ax.get_figure()) == ["bar"]

    def test_a_matplotlib_bar_is_unchanged(self):
        # `Axes.bar` has no plotter to ask -- it is handed its heights
        # directly -- so that side still reads its own arguments, and the
        # width/position inference stays where it is.
        _, ax = plt.subplots()
        ax.bar(["a", "b", "c"], [1.0, 2.0, 3.0])

        assert layers(ax.get_figure()) == ["bar"]

    def test_a_manually_dodged_matplotlib_bar_is_still_dodged(self):
        _, ax = plt.subplots()
        ax.bar([0.1, 1.1, 2.1], [1.0, 2.0, 3.0], width=0.4, label="A")
        ax.bar([0.5, 1.5, 2.5], [4.0, 5.0, 6.0], width=0.4, label="B")

        assert layers(ax.get_figure()) == ["dodged_bar", "dodged_bar"]
