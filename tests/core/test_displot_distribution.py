"""`sns.displot` read as a dodged bar chart and lost its bin edges (#446).

`displot` is seaborn's figure-level interface for distributions, and its
default `kind="hist"` draws a histogram. It does not import `histplot` -- it
drives `_DistributionPlotter` directly -- so neither name `wrap_seaborn`
patches was ever bound, and the panel was seen only by `Axes.bar`, which
cannot know it is drawing a histogram.

Measured on the same data through the two interfaces:

    sns.displot(df, x="v", bins=3)
      dodged_bar   {'x': '-1.61082', 'z': '_container0', 'y': 9.0}
    sns.histplot(df, x="v", bins=3)
      hist         {'y': 9.0, 'x': -1.6108, 'xMin': -2.3250, 'xMax': -0.8966, ...}

Three losses at once, each worse than the last:

* the **type** names a chart that compares groups side by side, which a
  distribution is not, so the reader is oriented to a chart that is not there;
* the **bin edges** are gone, so the bin *centre* is announced where a bar
  chart puts its category name -- a precise-looking number that is neither an
  observation nor a boundary, and nothing marks it as a midpoint;
* **`z` carried `_container0`**, maidr's own internal identifier for a
  `BarContainer`, announced as the name a reader hears to tell series apart.

`kind="kde"` had the smaller version of the same problem: `line` where the
axes-level `kdeplot` gives `smooth`. A fitted curve is not a series of
observations, and only one of the two types says so.

The fix patches the plotter method both interfaces drive, which is the idiom
`maidr/patch/boxplot.py` already uses for `_CategoricalPlotter.plot_boxes`.
`histplot` and `kdeplot` set the internal context before calling through, so
the inner patch declines for them and nothing registers twice.
"""

from __future__ import annotations

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import maidr  # noqa: F401,E402  # activates the patches
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.exception import UnsupportedPlotError  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "v": rng.normal(size=60),
            "w": rng.normal(size=60),
            "g": list("ab") * 30,
        }
    )


def layers(fig=None) -> list[str]:
    """The types registered for a figure, or [] when nothing was."""
    try:
        registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    except UnsupportedPlotError:
        return []
    return [plot.type.value for plot in registered._plots]


def samples(fig=None) -> list[dict]:
    registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    data = registered._plots[0].schema["data"]
    return data[0] if data and isinstance(data[0], list) else data


class TestADistributionReadsAsOne:
    def test_displot_is_a_histogram(self):
        sns.displot(frame(), x="v", bins=3)

        assert layers() == ["hist"]

    def test_it_carries_the_bin_interval(self):
        # The half that matters most to a reader. A histogram bar means "9
        # observations fell between -2.325 and -0.897"; without the bounds the
        # centre is all that is left, and a centre is not a value anything was
        # measured at.
        sns.displot(frame(), x="v", bins=3)
        first = {str(key): value for key, value in samples()[0].items()}

        assert {"xMin", "xMax"} <= set(first)
        assert first["xMin"] < first["x"] < first["xMax"]

    def test_it_agrees_with_the_axes_level_function(self):
        # The two interfaces draw the same chart from the same data, so they
        # should describe it the same way. This is what makes the defect
        # legible: nothing about `displot`'s reading looked wrong on its own.
        sns.displot(frame(), x="v", bins=3)
        figure_level = [
            {str(key): value for key, value in sample.items()}
            for sample in samples()
        ]

        plt.close("all")
        _, ax = plt.subplots()
        sns.histplot(frame(), x="v", bins=3, ax=ax)
        axes_level = [
            {str(key): value for key, value in sample.items()}
            for sample in samples(ax.get_figure())
        ]

        assert figure_level == axes_level

    def test_no_internal_container_name_is_announced(self):
        # `_container0` is maidr's own identifier for a `BarContainer`. A
        # reader was being handed it as a group name.
        sns.displot(frame(), x="v", bins=3)

        assert not any(
            "_container" in str(value)
            for sample in samples()
            for value in sample.values()
        )

    def test_a_kde_is_a_fitted_curve(self):
        sns.displot(frame(), x="v", kind="kde")

        assert layers() == ["smooth"]

    def test_an_ecdf_is_unchanged(self):
        # The one `kind` that was already right, pinned so the change does not
        # move it on the way past.
        sns.displot(frame(), x="v", kind="ecdf")

        assert layers() == ["step"]


class TestEveryPanelIsRead:
    """One call to the plotter method covers the whole grid."""

    def test_each_faceted_histogram_panel_registers(self):
        # `plot_univariate_histogram` is reached *once* and draws both panels,
        # and `plotter.ax` is None in exactly this case -- so a wrapper that
        # read only `ax` would register nothing at all here.
        sns.displot(frame(), x="v", col="g", bins=3)

        assert layers() == ["hist", "hist"]

    def test_each_faceted_kde_panel_registers(self):
        sns.displot(frame(), x="v", kind="kde", col="g")

        assert layers() == ["smooth", "smooth"]


class TestWhatMustNotChange:
    def test_histplot_still_registers_exactly_once(self):
        # The recursion guard. `histplot` drives the same plotter method, so
        # without the internal-context check every panel would register twice.
        _, ax = plt.subplots()
        sns.histplot(frame(), x="v", bins=3, ax=ax)

        assert layers(ax.get_figure()) == ["hist"]

    def test_kdeplot_still_registers_exactly_once(self):
        _, ax = plt.subplots()
        sns.kdeplot(frame(), x="v", ax=ax)

        assert layers(ax.get_figure()) == ["smooth"]

    def test_histplot_with_a_kde_overlay_is_unchanged(self):
        _, ax = plt.subplots()
        sns.histplot(frame(), x="v", bins=3, kde=True, ax=ax)

        assert layers(ax.get_figure()) == ["hist", "smooth"]

    def test_a_bivariate_histogram_still_declines_to_be_a_histogram(self):
        # `sns.histplot(x=..., y=...)` is a 2D histogram drawn as a QuadMesh,
        # not as bars. `hist` promises one bin per bar with a count, which
        # such a layer has neither of, so registering it would promise a
        # reading nothing can produce (#388). That decline stands.
        #
        # What it no longer costs is the chart: a mesh of joint counts is a
        # heatmap, and is now read as one rather than being lost with the
        # `hist` it is not (#522).
        _, ax = plt.subplots()
        sns.histplot(frame(), x="v", y="w", ax=ax)

        assert layers(ax.get_figure()) == ["heat"]

    def test_a_histogram_does_not_claim_someone_elses_bars(self):
        # The per-axes snapshot. An axes that already holds bars must not have
        # them read as this histogram's, which is the difference between
        # declining and lying.
        _, ax = plt.subplots()
        sns.barplot(frame(), x="g", y="v", ax=ax)
        sns.histplot(frame(), x="v", y="w", ax=ax)

        # No `hist`, which is what this case is about. The `heat` beside it is
        # the mesh that call drew, asked the same ownership question (#522).
        assert layers(ax.get_figure()) == ["bar", "heat"]

    def test_a_jointplot_is_unchanged(self):
        # It reaches the defining-module binding rather than the plotter
        # class, so it takes a different path and must not shift.
        grid = sns.jointplot(data=frame(), x="v", y="w")

        assert layers(grid.figure) == ["point", "hist", "hist"]


class TestAFacetedHistogramNamesEachPanelFromItself:
    """Every panel's names used to resolve from the last panel's (#591).

    ``deferred_names`` stores its resolver and runs it at *render*, which is
    what makes a ``pairplot``'s legend readable (#561). Built inside the
    per-panel loop it closed over the loop variables, so by the time it ran
    they held the final panel's axes and containers and every panel was named
    from that one.

    Measured on a grid whose panels hold different groups: three layers, all
    ``None``, because the last panel held a single container and a lone
    artist is exactly what ``names_for`` declines. Asked panel by panel the
    same figure gives ``['b', 'a']`` and ``[None]``.
    """

    @staticmethod
    def _split_frame() -> pd.DataFrame:
        # Panel "p" holds groups a and b; panel "q" holds only c. The panels
        # must differ in *shape*, or the last one's answer happens to fit.
        return pd.DataFrame(
            {
                "v": list(np.linspace(0, 1, 30)),
                "g": ["a"] * 10 + ["b"] * 10 + ["c"] * 10,
                "c": ["p"] * 20 + ["q"] * 10,
            }
        )

    def test_each_panel_is_named_from_its_own_groups(self):
        grid = sns.displot(self._split_frame(), x="v", hue="g", col="c", bins=3)
        named = [
            (plot.schema.get("name"), [point["y"] for point in plot.schema["data"]])
            for plot in FigureManager.get_maidr(grid.figure)._plots
        ]

        # The counts say which group each layer holds, so the names can be
        # checked against them rather than against registration order.
        assert named == [
            ("b", [0.0, 10.0, 0.0]),
            ("a", [10.0, 0.0, 0.0]),
            (None, [0.0, 0.0, 10.0]),
        ]

