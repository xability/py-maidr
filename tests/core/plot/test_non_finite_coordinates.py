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
    """The boundary, drawn on purpose rather than by accident.

    ``seaborn.pointplot`` NaN-pads a hue level that never appears in some
    category, and that padding is load-bearing: it keeps both estimate lines
    at one vertex per category, which is what stops the pairing failing and
    the interval polylines travelling as data (see ``test_pointplot.py``).

    So a real x with a non-finite y is *not* the same thing as a point with
    no position, and the rule asks about x alone. Emitting the value as
    ``null`` instead was measured against the core and is worse than it
    looks: ``LineTrace`` yields ``audio.freq.raw = 0`` and
    ``text.cross.value = null``, so the gap is sonified as a floor tone and
    announced as a word. Naming it properly needs a per-point empty state the
    grammar does not have, which is #429.
    """

    def test_the_padded_sample_is_kept(self):
        import pandas as pd

        unbalanced = pd.DataFrame(
            {
                "g": ["a"] * 4 + ["b"] * 4 + ["c"] * 2,
                "half": ["x", "x", "y", "y", "x", "x", "y", "y", "x", "x"],
                "v": [1.0, 2.0, 5.0, 6.0, 10.0, 11.0, 14.0, 15.0, 20.0, 21.0],
            }
        )
        _, ax = plt.subplots()
        sns.pointplot(unbalanced, x="g", y="v", hue="half", dodge=True, ax=ax)

        series = series_of(ax)

        assert len(series) == 2
        assert all(len(one) == 3 for one in series)

    @pytest.mark.xfail(
        strict=True,
        reason="#429: a positioned sample with no value has no JSON-safe "
        "representation until the grammar can express an empty point",
    )
    def test_its_payload_is_not_parseable_yet(self):
        import pandas as pd

        unbalanced = pd.DataFrame(
            {
                "g": ["a"] * 4 + ["b"] * 4 + ["c"] * 2,
                "half": ["x", "x", "y", "y", "x", "x", "y", "y", "x", "x"],
                "v": [1.0, 2.0, 5.0, 6.0, 10.0, 11.0, 14.0, 15.0, 20.0, 21.0],
            }
        )
        _, ax = plt.subplots()
        sns.pointplot(unbalanced, x="g", y="v", hue="half", dodge=True, ax=ax)

        parses_as_strict_json(ax)


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
