"""A non-finite coordinate produced a payload the core cannot parse (#427).

``json.dumps`` writes ``NaN``, ``Infinity`` and ``-Infinity`` as bare tokens.
They are legal JavaScript literals but **not** JSON, and the core parses the
SVG's ``maidr`` attribute with ``JSON.parse`` (``src/index.tsx``), which
rejects all three:

    JSON.parse rejects -Infinity: No number after minus sign in JSON at position 7

The ``catch`` around it logs and returns, so ``initMaidrOnElement`` is never
called. That makes this worse than a wrong reading: audio, text, braille and
highlight are all absent, and the only trace is a ``console.error`` a screen
reader user has no reason to be looking at.

Two idioms reach it, and neither is exotic:

* ``sns.ecdfplot`` starts its staircase at ``-inf``, so the first step has
  somewhere to come from;
* ``NaN`` is matplotlib's own way of **breaking** a line into segments, and a
  masked array becomes one on the way through.

Dropping the point is the right answer rather than the lesser evil: none of
those coordinates names a value a reader could be told. What is lost is the
visual gap, which MAIDR's grammar has no point shape for either way -- and
the samples on both sides keep their real x, so the jump is still heard.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from maidr.core.enum import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _reject_constant(token: str):
    raise ValueError(token)


def parses_as_strict_json(ax) -> None:
    """Assert the emitted schema survives what the core actually runs on it.

    ``json.loads`` accepts the three tokens by default, exactly as
    ``json.dumps`` emits them, so the round trip passes while the browser
    fails. ``parse_constant`` is what makes this test able to fail.
    """
    ax = getattr(ax, "axes", ax)
    schema = FigureManager.get_maidr(ax.get_figure())._flatten_maidr()

    json.loads(json.dumps(schema), parse_constant=_reject_constant)


def series_of(ax) -> list[list[dict]]:
    ax = getattr(ax, "axes", ax)
    maidr = FigureManager.get_maidr(ax.get_figure())
    return [series for plot in maidr._plots for series in plot.schema["data"]]


class TestTheEcdfThatStartsAtNegativeInfinity:
    def test_its_payload_is_parseable(self):
        ax = sns.ecdfplot(x=np.random.default_rng(0).normal(size=30))

        parses_as_strict_json(ax)

    def test_the_padding_point_is_dropped_and_the_rest_kept(self):
        # One point per observation: the -inf row is seaborn's staircase
        # scaffolding, not a 31st datum.
        data = np.random.default_rng(0).normal(size=30)
        ax = sns.ecdfplot(x=data)

        assert [len(series) for series in series_of(ax)] == [len(data)]

    def test_the_proportions_still_reach_one(self):
        # Dropping from the front must not shift the curve. If the wrong row
        # went, the last proportion is no longer 1.
        ax = sns.ecdfplot(x=np.random.default_rng(0).normal(size=30))
        ys = [point["y"] for point in series_of(ax)[0]]

        assert ys[-1] == pytest.approx(1.0)
        assert ys == sorted(ys)


class TestALineBrokenByNaN:
    """`NaN` is how matplotlib itself splits a line, so this is idiomatic."""

    def test_its_payload_is_parseable(self):
        line = plt.plot([1, 2, np.nan, 4], [10, 20, np.nan, 40])[0]

        parses_as_strict_json(line)

    def test_the_real_samples_survive_intact(self):
        # The assertion that matters is not "no NaN" but that the gap costs
        # nothing else: both sides keep their own x and y.
        line = plt.plot([1, 2, np.nan, 4], [10, 20, np.nan, 40])[0]
        points = [(point["x"], point["y"]) for point in series_of(line)[0]]

        assert points == [(1.0, 10.0), (2.0, 20.0), (4.0, 40.0)]

    def test_a_step_is_covered_by_the_same_rule(self):
        # `StepPlot` extends `MultiLinePlot`, which is why one fix serves
        # both -- asserted rather than left to inheritance.
        step = plt.step([1, 2, np.nan, 4], [10, 20, np.nan, 40])[0]

        parses_as_strict_json(step)
        assert len(series_of(step)[0]) == 3

    def test_a_masked_array_is_too(self):
        # A mask becomes NaN on the way through, so it arrives by a different
        # route at the same defect.
        line = plt.plot(np.ma.masked_invalid([1.0, 2.0, np.nan, 4.0]), [1, 2, 3, 4])[0]

        parses_as_strict_json(line)


class TestASampleWithAPositionButNoValue:
    """Kept and reported as missing, rather than dropped or faked.

    ``seaborn.pointplot`` NaN-pads a hue level that never appears in some
    category, and that padding is load-bearing: it keeps both estimate lines
    at one vertex per category, which is what stops the pairing failing and
    the interval polylines travelling as data (see ``test_pointplot.py``).

    So a real x with a non-finite y is *not* the same thing as a point with no
    position, and the position rule asks about x alone. The value is emitted
    as ``None`` -> ``null``, which the core has read as a gap since maidr
    4.3.0 (xability/maidr#926): it becomes ``NaN`` inside ``LineTrace``, stays
    out of the range, sounds as the empty tone rather than a floor tone, and
    announces as "missing".

    This was a strict ``xfail`` when #430 landed, because before that release
    there was no honest representation -- a bare ``NaN`` stopped the chart
    initialising and a zero would have claimed a reading of zero.
    """

    @staticmethod
    def _unbalanced():
        import pandas as pd

        return pd.DataFrame(
            {
                "g": ["a"] * 4 + ["b"] * 4 + ["c"] * 2,
                "half": ["x", "x", "y", "y", "x", "x", "y", "y", "x", "x"],
                "v": [1.0, 2.0, 5.0, 6.0, 10.0, 11.0, 14.0, 15.0, 20.0, 21.0],
            }
        )

    def _axes(self):
        _, ax = plt.subplots()
        sns.pointplot(self._unbalanced(), x="g", y="v", hue="half", dodge=True, ax=ax)
        return ax

    def test_the_padded_sample_is_kept(self):
        series = series_of(self._axes())

        assert len(series) == 2
        assert all(len(one) == 3 for one in series)

    def test_its_value_is_null_rather_than_a_number(self):
        # The distinction the whole thing rests on: `null` is "no reading
        # here", where `0` would be a reading of zero at a category whose
        # data does not exist.
        padded = [point for one in series_of(self._axes()) for point in one]
        gaps = [point for point in padded if point["y"] is None]

        assert len(gaps) == 1
        assert gaps[0]["x"] == "c"

    def test_it_keeps_its_position(self):
        # Dropping it would break the pairing the padding exists for.
        series = series_of(self._axes())

        for one in series:
            assert [point["x"] for point in one] == ["a", "b", "c"]

    def test_the_payload_is_loadable(self):
        # This is the assertion that was a strict xfail until maidr 4.3.0.
        parses_as_strict_json(self._axes())


class TestWhatMustNotChange:
    def test_a_clean_line_keeps_every_point(self):
        line = plt.plot([1, 2, 3], [10, 20, 30])[0]

        assert len(series_of(line)[0]) == 3

    def test_a_categorical_x_is_not_mistaken_for_non_finite(self):
        # The guard has to be a test *of numbers*. `math.isfinite` raises on a
        # string, and treating that as "not finite" would delete every point
        # of any chart whose x axis is categorical.
        line = plt.plot(["a", "b", "c"], [1, 2, 3])[0]

        assert [point["x"] for point in series_of(line)[0]] == ["a", "b", "c"]


class TestTheCandlestickWithAGap:
    """A row mplfinance draws as a gap took the whole figure down.

    mplfinance accepts a row whose open, high, low and close are all NaN and
    draws it as empty geometry. ``float(nan)`` raises none of the errors the
    extraction loop skipped a row on, so the candle went out as a bare
    ``NaN`` -- the #427 failure again, and worse here, because the volume
    bars and moving averages on the same figure share the payload and went
    dark with it (#706).
    """

    @staticmethod
    def _frame():
        import pandas as pd

        frame = pd.DataFrame(
            {
                "Open": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                "High": [2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                "Low": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                "Close": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
            },
            index=pd.date_range("2026-01-01", periods=6),
        )
        frame.iloc[2] = np.nan
        return frame

    def _candlestick(self):
        mpf = pytest.importorskip("mplfinance")
        frame = self._frame()
        fig, _ = mpf.plot(frame, type="candle", returnfig=True)
        plots = FigureManager.get_maidr(fig)._plots
        return frame, next(p for p in plots if p.type == PlotType.CANDLESTICK)

    def test_its_payload_is_parseable(self):
        _, plot = self._candlestick()

        parses_as_strict_json(plot.ax)

    def test_the_gap_row_is_dropped_and_the_rest_kept(self):
        frame, plot = self._candlestick()
        candles = plot.schema["data"]

        assert len(candles) == len(frame) - 1
        # The rows either side of the gap keep their own values, so what is
        # lost is the gap and nothing else.
        assert [candle["open"] for candle in candles] == [1.0, 2.0, 4.0, 5.0, 6.0]
        assert not any(
            value != value  # NaN is the one float unequal to itself
            for candle in candles
            for value in candle.values()
            if isinstance(value, float)
        )

    def test_the_wick_selectors_still_count_every_row(self):
        # The SVG keeps a body path and two wick paths for the gap row, so the
        # nth-child split between low and high wicks must go on counting the
        # frame, not the candles emitted. The cost is that a highlight after
        # the gap lands one path early; before, there was no highlight at all.
        frame, plot = self._candlestick()
        selectors = plot.schema["selectors"]

        assert len(plot._maidr_wick_collection.get_paths()) == 2 * len(frame)
        assert f"nth-child(-n+{len(frame)})" in selectors["wickLow"]
        assert f"nth-child(n+{len(frame) + 1})" in selectors["wickHigh"]
