"""A binned regplot announced each interval as its own fitted curve (#451).

`sns.regplot(x_estimator=...)` collapses each x to an estimate and draws a
confidence interval around it. Those intervals are ordinary lines, and the
patch asked the *axes* which of its lines were fits rather than knowing which
lines its own call drew — so every one registered as a `smooth` layer:

    sns.regplot(df, x="dose", y="resp", x_estimator=np.mean)
      point(4), smooth(2), smooth(2), smooth(2), smooth(2), smooth(30)

Six layers for four estimates and one line. Three losses, and they compound:

* the **type** is wrong — `smooth` means a computed fit, and a vertical
  confidence bar is not one, so a reader who navigates into layer 1 is told
  they are on a curve and hears two points at the same x;
* the **count scales with the data** — `x_estimator` bins by unique x when
  `x_bins` is absent, so sixty distinct values gave sixty-one layers;
* the **link is severed** — the estimates sat in layer 0 and each interval in
  a layer of its own, so the uncertainty was unreachable from the value it
  bounds.

The same sweep had a second symptom needing no `x_estimator` at all. It matched
any label starting with `_child`, which is what matplotlib names *any*
unlabelled artist rather than something a regression line is distinguished by:

    ax.plot(...); sns.regplot(...)   ->  line, point, smooth, smooth

The caller's own series announced twice, once correctly and once as a model of
itself. Order decided it — a line added *after* the regplot was safe — and
"plot the series, overlay a fit" is the ordinary way round.

Both are answered by a before/after snapshot plus a geometric split: an
interval bar stands at one x, and the fitted curve spans the axis.
"""

from __future__ import annotations

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import maidr  # noqa: F401,E402  # activates the patches
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.exception import UnsupportedPlotError  # noqa: E402
from maidr.patch.regplot import _paired_estimates  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def frame() -> pd.DataFrame:
    """Four dose levels with clearly separated means."""
    rng = np.random.default_rng(451)
    return pd.DataFrame(
        {
            "dose": np.repeat([1.0, 2.0, 3.0, 4.0], 15),
            "resp": rng.normal(size=60) + np.repeat([1, 3, 5, 8], 15),
        }
    )


def layers(fig=None) -> list[str]:
    """The types registered for a figure, or [] when nothing was."""
    try:
        registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    except UnsupportedPlotError:
        return []
    return [plot.type.value for plot in registered._plots]


def estimates(fig=None) -> list[dict]:
    """The samples of the first ``error_bar`` layer, keyed by plain strings.

    ``MaidrKey`` subclasses ``str``, so a lookup by ``"y"`` finds a sample
    keyed by the member — but ``str(MaidrKey.Y)`` is ``"MaidrKey.Y"``, so the
    value is what makes a readable dict.
    """
    registered = FigureManager.get_maidr(fig if fig is not None else plt.gcf())
    for plot in registered._plots:
        if plot.type.value == "error_bar":
            return [
                {getattr(key, "value", key): value for key, value in sample.items()}
                for sample in plot.schema["data"]
            ]
    return []


class TestTheIntervalsAreNotCurves:
    def test_a_binned_regplot_is_two_layers(self):
        # Was six: the estimates, four interval bars each typed `smooth`, and
        # the fitted curve.
        _, ax = plt.subplots()
        sns.regplot(data=frame(), x="dose", y="resp", x_estimator=np.mean, ax=ax)

        assert layers(ax.get_figure()) == ["error_bar", "smooth"]

    def test_the_layer_count_does_not_scale_with_the_bins(self):
        # The half that made this unusable rather than merely mistyped.
        # `x_estimator` bins by unique x when `x_bins` is absent, so a
        # continuous x gave one layer per distinct value -- sixty-one here.
        rng = np.random.default_rng(20260814)
        wide = pd.DataFrame({"a": np.arange(60.0), "b": rng.normal(size=60)})

        _, ax = plt.subplots()
        sns.regplot(data=wide, x="a", y="b", x_estimator=np.mean, ax=ax)

        assert layers(ax.get_figure()) == ["error_bar", "smooth"]

    def test_each_estimate_carries_its_own_bounds(self):
        # The link that was severed. The estimates were in one layer and each
        # interval in another, so the uncertainty could not be reached from
        # the value it bounds.
        _, ax = plt.subplots()
        sns.regplot(data=frame(), x="dose", y="resp", x_estimator=np.mean, ax=ax)

        samples = estimates(ax.get_figure())

        assert [sample["x"] for sample in samples] == [1.0, 2.0, 3.0, 4.0]
        for sample in samples:
            assert {"yMin", "yMax"} <= set(sample)
            assert sample["yMin"] < sample["y"] < sample["yMax"]

    def test_the_estimates_are_the_binned_means(self):
        # A bracketed reading assembled from the wrong artists would still look
        # bracketed. Checked against the estimator the caller passed.
        data = frame()
        _, ax = plt.subplots()
        sns.regplot(data=data, x="dose", y="resp", x_estimator=np.mean, ax=ax)

        for sample in estimates(ax.get_figure()):
            rows = data.loc[data["dose"] == sample["x"], "resp"]
            assert sample["y"] == pytest.approx(rows.mean(), abs=1e-6)

    def test_x_bins_takes_the_same_path(self):
        _, ax = plt.subplots()
        sns.regplot(data=frame(), x="dose", y="resp", x_bins=4, ax=ax)

        assert layers(ax.get_figure()) == ["error_bar", "smooth"]

    def test_it_agrees_with_the_point_plot_of_the_same_estimates(self):
        # `sns.pointplot` draws the same quantity -- an estimate per level with
        # a confidence interval -- and has read as one `error_bar` layer since
        # #246. That the two now agree in shape is the property being fixed.
        data = frame()
        _, ax = plt.subplots()
        sns.regplot(data=data, x="dose", y="resp", x_estimator=np.mean, ax=ax)
        binned = estimates(ax.get_figure())

        plt.close("all")
        _, ax = plt.subplots()
        sns.pointplot(data=data, x="dose", y="resp", ax=ax)
        categorical = estimates(ax.get_figure())

        assert len(binned) == len(categorical)
        for one, other in zip(binned, categorical):
            # The bounds are bootstrapped, so they differ between calls; the
            # estimate is not.
            assert one["y"] == pytest.approx(other["y"], abs=1e-6)
            assert {"yMin", "yMax"} <= set(one)


class TestTheCurveIsStillACurve:
    def test_the_fit_survives_alongside_the_intervals(self):
        # A binned regplot legitimately has *both* an uncertainty layer and a
        # fit, so the split must not swallow the curve with the bars.
        _, ax = plt.subplots()
        sns.regplot(data=frame(), x="dose", y="resp", x_estimator=np.mean, ax=ax)
        registered = FigureManager.get_maidr(ax.get_figure())

        curves = [plot for plot in registered._plots if plot.type.value == "smooth"]

        assert len(curves) == 1
        # A smooth layer's `data` holds one entry per series, so the samples
        # are a level down -- and the point of the assertion is that the curve
        # is a curve rather than one of the two-point bars.
        series = curves[0].schema["data"]
        assert len(series) == 1
        assert len(series[0]) > 4

    def test_a_plain_regplot_is_unchanged(self):
        _, ax = plt.subplots()
        sns.regplot(data=frame(), x="dose", y="resp", ax=ax)

        assert layers(ax.get_figure()) == ["point", "smooth"]

    def test_no_intervals_means_no_error_bar_layer(self):
        # `ci=None` draws none, so there is nothing for the layer to carry and
        # a plain scatter is the honest reading.
        _, ax = plt.subplots()
        sns.regplot(
            data=frame(), x="dose", y="resp", x_estimator=np.mean, ci=None, ax=ax
        )

        assert layers(ax.get_figure()) == ["point", "smooth"]

    def test_a_curve_only_regplot_is_unchanged(self):
        _, ax = plt.subplots()
        sns.regplot(data=frame(), x="dose", y="resp", scatter=False, ax=ax)

        assert layers(ax.get_figure()) == ["smooth"]

    @pytest.mark.parametrize(
        "kwargs",
        [{"order": 2}, {"lowess": True}, {"robust": False, "ci": 99}],
        ids=["polynomial", "lowess", "wide-ci"],
    )
    def test_the_other_fits_are_unchanged(self, kwargs):
        _, ax = plt.subplots()
        sns.regplot(data=frame(), x="dose", y="resp", ax=ax, **kwargs)

        assert layers(ax.get_figure()) == ["point", "smooth"]


class TestALineTheCallDidNotDraw:
    def test_a_line_drawn_first_is_not_read_as_the_fit(self):
        # The `_child` label heuristic. `_child0` is what matplotlib names any
        # unlabelled artist, so the caller's own series was swept up and
        # announced twice -- once as `line` and once as a model of itself.
        _, ax = plt.subplots()
        ax.plot([1.0, 2.0, 3.0, 4.0], [0.5, 1.5, 2.5, 3.5])
        sns.regplot(data=frame(), x="dose", y="resp", ax=ax)

        assert layers(ax.get_figure()) == ["line", "point", "smooth"]

    def test_a_seaborn_line_drawn_first_is_not_either(self):
        _, ax = plt.subplots()
        sns.lineplot(data=frame(), x="dose", y="resp", ax=ax)
        sns.regplot(data=frame(), x="dose", y="resp", ax=ax)

        assert layers(ax.get_figure()) == ["line", "point", "smooth"]

    def test_a_line_drawn_afterwards_is_still_its_own_layer(self):
        # The order that always worked, pinned so the snapshot does not swing
        # the other way and swallow it.
        _, ax = plt.subplots()
        sns.regplot(data=frame(), x="dose", y="resp", ax=ax)
        ax.plot([1.0, 2.0, 3.0, 4.0], [0.5, 1.5, 2.5, 3.5])

        assert layers(ax.get_figure()) == ["point", "smooth", "line"]

    def test_a_scatter_drawn_first_is_not_claimed_as_the_estimates(self):
        # The collection snapshot, which the scatter layer needs for the same
        # reason: `ScatterPlot` sweeps the axes when it is handed nothing, so
        # a regplot over an existing scatter would describe that one's points.
        _, ax = plt.subplots()
        ax.scatter([9.0, 9.5], [9.0, 9.5])
        sns.regplot(data=frame(), x="dose", y="resp", ax=ax)
        registered = FigureManager.get_maidr(ax.get_figure())

        scatters = [
            plot for plot in registered._plots if plot.type.value == "point"
        ]

        assert len(scatters) == 2
        assert len(scatters[-1].schema["data"]) == 60


class TestThePairingIsVerifiedRatherThanAssumed:
    """The fallback, driven directly because seaborn never produces it.

    `PointPlot` zips its estimates against its intervals positionally, so a
    pairing that is off by one would put every bound on the wrong estimate --
    a chart that reads as complete and is wrong about every interval in it.
    Nothing seaborn draws reaches these branches, which is exactly why they
    are worth holding to the same rule as the reachable ones: an untested
    guard is one someone deletes as redundant.
    """

    @staticmethod
    def _collection(xs, ys):
        _, ax = plt.subplots()
        return ax.scatter(xs, ys)

    @staticmethod
    def _bar(x, low, high):
        return Line2D([x, x], [low, high])

    def test_a_count_mismatch_declines(self):
        # More estimates than bars. Zipping would silently describe only the
        # first few and drop the rest.
        collection = self._collection([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        bars = [self._bar(1.0, 0.5, 1.5), self._bar(2.0, 1.5, 2.5)]

        assert _paired_estimates(collection, bars) is None

    def test_a_bar_standing_at_no_estimate_declines(self):
        # Right count, wrong positions. This is the case that would produce a
        # confidently wrong reading rather than a short one.
        collection = self._collection([1.0, 2.0], [1.0, 2.0])
        bars = [self._bar(1.0, 0.5, 1.5), self._bar(9.0, 8.5, 9.5)]

        assert _paired_estimates(collection, bars) is None

    def test_matching_artists_pair_in_x_order(self):
        # The other side of the rule: the guard must not decline artists that
        # do correspond, whatever order they arrive in.
        collection = self._collection([2.0, 1.0], [20.0, 10.0])
        bars = [self._bar(2.0, 19.0, 21.0), self._bar(1.0, 9.0, 11.0)]

        paired = _paired_estimates(collection, bars)

        assert paired is not None
        estimates_line, ordered = paired
        assert list(estimates_line.get_xdata()) == [1.0, 2.0]
        assert list(estimates_line.get_ydata()) == [10.0, 20.0]
        assert [line.get_xdata()[0] for line in ordered] == [1.0, 2.0]


class TestNoBranchDropsALayer:
    """Whatever cannot be paired is still described.

    Mistyping an interval bar as a curve is the reading this change replaces,
    and it is bad. Dropping it is worse: a layer that is not there cannot be
    navigated to, and nothing says it is missing -- so the chart reads as
    complete while one of its parts is simply absent.

    The arm that used to skip them needed the pairing to fail *and* the
    scatter to be absent, which seaborn cannot produce today: the binned
    estimate and its interval are drawn together, inside the branch gated on
    `scatter`. That is exactly why it is worth pinning rather than reasoning
    about -- a guard nothing reaches is one that stops holding quietly when
    an upstream release moves.

    Driven by making the pairing fail, since seaborn will not.
    """

    def test_unpairable_intervals_are_still_described(self, monkeypatch):
        import maidr.patch.regplot as patch

        monkeypatch.setattr(patch, "_paired_estimates", lambda *_: None)

        _, ax = plt.subplots()
        sns.regplot(data=frame(), x="dose", y="resp", x_estimator=np.mean, ax=ax)

        # Four bars plus the fit, all described, with the estimates as a
        # scatter -- the reading that was there before this change, which is
        # incomplete rather than wrong.
        registered = layers(ax.get_figure())
        assert registered.count("smooth") == 5
        assert "point" in registered

    def test_nothing_is_lost_when_the_scatter_is_absent_too(self, monkeypatch):
        # The unreachable corner itself: no scatter to fall back to, so the
        # intervals are the only thing left to describe.
        import maidr.patch.regplot as patch

        monkeypatch.setattr(patch, "_paired_estimates", lambda *_: None)
        monkeypatch.setattr(
            patch, "_prospective_axes", lambda kwargs: kwargs.get("ax")
        )

        _, ax = plt.subplots()
        sns.regplot(
            data=frame(), x="dose", y="resp", x_estimator=np.mean,
            scatter=False, ax=ax,
        )

        # No estimates were drawn, so no `point` layer -- and every line the
        # call drew is still a layer rather than nothing.
        registered = layers(ax.get_figure())
        assert "point" not in registered
        assert registered.count("smooth") >= 1
