"""A boxen plot announced its scaffolding and left out the chart (#253).

``sns.boxenplot`` draws a *letter-value* plot: the quartile box, then the
eighths, then the sixteenths, as deep as the sample supports. The depth is the
point -- it is what a boxen has and a box plot does not, and it is why someone
reaches for one on a large sample.

MAIDR had no type that could hold a variable-depth ladder, so the chart fell
through to the generic matplotlib patches. What came out was not a partial
reading. Measured on three categories of 200 observations::

    line  : 3 series of 2 points, each series one value repeated twice
    point : 3 layers, x = 0.0 / 1.0 / 2.0

The line layer was the median segments, so the chart announced itself as a
line chart and said each median twice. The point layers were the outliers
alone, at numeric slots rather than at ``a``/``b``/``c``. Every rung of every
ladder was absent and nothing said so.

maidr 4.3.0 shipped ``TraceType.BOXEN``, which carries a median, a ladder of
``{p, lo, hi}`` rungs and the values beyond the deepest one. These tests check
the ladder against ``np.percentile`` rather than against a stored payload,
because the failure this replaces looked entirely plausible: the way to tell a
ladder that was read from one that was assembled is whether its rungs are the
quantiles seaborn computed.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


GROUPS = {
    "a": np.random.default_rng(0).normal(0, 1, 200),
    "b": np.random.default_rng(1).normal(2, 1.5, 200),
}


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "g": np.repeat(list(GROUPS), [len(v) for v in GROUPS.values()]),
            "v": np.concatenate(list(GROUPS.values())),
        }
    )


def hue_frame() -> pd.DataFrame:
    df = frame()
    df["h"] = np.tile(np.repeat(["p", "q"], 100), 2)
    return df


def layers(ax) -> list:
    ax = getattr(ax, "axes", ax)
    return FigureManager.get_maidr(ax.get_figure())._plots


def ladders(ax) -> list[dict]:
    """Every boxen point on the axes, in draw order."""
    return [
        point
        for plot in layers(ax)
        if plot.type.value == "boxen"
        for point in plot.schema["data"]
    ]


def true_rungs(values: np.ndarray, depth: int) -> list[tuple[float, float, float]]:
    """The ladder seaborn would compute, straight from ``np.percentile``.

    Deliberately re-derived from the definition rather than imported from
    seaborn, so a change of behaviour upstream shows up as a failure here
    instead of being mirrored into both sides at once.
    """
    return [
        (
            0.5 ** (depth + 1 - rung),
            float(np.percentile(values, 100 * 0.5 ** (depth + 1 - rung))),
            float(np.percentile(values, 100 * (1 - 0.5 ** (depth + 1 - rung)))),
        )
        for rung in range(depth)
    ]


class TestTheLadderIsTheChart:
    def test_the_layer_is_a_boxen_and_nothing_else(self):
        # The scaffolding layers are the defect, not a harmless extra: a
        # reader switching layers found a "line chart" of medians and three
        # scatter clouds, and no rung anywhere.
        ax = sns.boxenplot(frame(), x="g", y="v")

        assert [plot.type.value for plot in layers(ax)] == ["boxen"]

    def test_every_rung_is_the_quantile_seaborn_computed(self):
        ax = sns.boxenplot(frame(), x="g", y="v")
        drawn = ladders(ax)

        assert len(drawn) == len(GROUPS)
        for point, values in zip(drawn, GROUPS.values()):
            got = [(rung["p"], rung["lo"], rung["hi"]) for rung in point["levels"]]
            assert got == pytest.approx(true_rungs(values, len(got)))

    def test_the_rungs_are_distinct(self):
        # The regression that made this worth reading from the boxes rather
        # than from a set of their shared edges. Two boxes meet at a quantile
        # holding separately computed floats; when they differed in the last
        # bits both survived the set, and one group came out with five rungs
        # instead of four, `lo` repeated across two of them, and the widest
        # rung a copy of its neighbour -- all of it plausible in the payload.
        for point in ladders(sns.boxenplot(frame(), x="g", y="v")):
            los = [rung["lo"] for rung in point["levels"]]
            his = [rung["hi"] for rung in point["levels"]]

            assert len(set(los)) == len(los)
            assert len(set(his)) == len(his)

    def test_the_rungs_run_outermost_first_and_nest(self):
        # Order is what the core walks, and nesting is what makes it a ladder:
        # each rung must sit strictly inside the one deeper than it.
        for point in ladders(sns.boxenplot(frame(), x="g", y="v")):
            levels = point["levels"]

            assert [rung["p"] for rung in levels] == sorted(
                rung["p"] for rung in levels
            )
            for deeper, shallower in zip(levels, levels[1:]):
                assert deeper["lo"] <= shallower["lo"]
                assert shallower["hi"] <= deeper["hi"]

    def test_the_widest_rung_is_the_quartile_pair(self):
        # Every letter-value ladder starts from the middle half, whatever its
        # depth. If this drifts, every `p` below it is mislabelled too.
        for point, values in zip(
            ladders(sns.boxenplot(frame(), x="g", y="v")), GROUPS.values()
        ):
            widest = point["levels"][-1]

            assert widest["p"] == 0.25
            assert widest["lo"] == pytest.approx(float(np.percentile(values, 25)))
            assert widest["hi"] == pytest.approx(float(np.percentile(values, 75)))

    def test_the_median_is_the_median(self):
        for point, values in zip(
            ladders(sns.boxenplot(frame(), x="g", y="v")), GROUPS.values()
        ):
            assert point["median"] == pytest.approx(float(np.median(values)))
            assert point["levels"][-1]["lo"] <= point["median"]
            assert point["median"] <= point["levels"][-1]["hi"]


class TestTheCategoriesAreNamed:
    def test_each_ladder_carries_its_label(self):
        # The old scatter layers positioned the outliers at 0.0 and 1.0. A
        # reader was told a number where the axis says a name.
        drawn = ladders(sns.boxenplot(frame(), x="g", y="v"))

        assert [point["z"] for point in drawn] == list(GROUPS)

    def test_a_hue_split_names_both_dimensions(self):
        ax = sns.boxenplot(hue_frame(), x="g", y="v", hue="h")

        assert [point["z"] for point in ladders(ax)] == [
            "a, p",
            "a, q",
            "b, p",
            "b, q",
        ]

    def test_the_hue_dimension_itself_is_named(self):
        ax = sns.boxenplot(hue_frame(), x="g", y="v", hue="h")
        schema = [plot.schema for plot in layers(ax)][0]

        assert schema["axes"]["z"] == {"label": "h"}


class TestOrientation:
    def test_a_horizontal_boxen_reads_the_same(self):
        # Orientation is taken from the median segment, so this covers the
        # inference without a keyword being threaded through.
        upright = ladders(sns.boxenplot(frame(), x="g", y="v"))
        plt.close("all")
        sideways = ladders(sns.boxenplot(frame(), y="g", x="v"))

        assert sideways == upright

    def test_the_value_axis_is_not_the_category_slot(self):
        # The failure a naive orientation guess produces: reading the boxes'
        # *category* extents, which run 0.6 to 1.4 and are the same for every
        # chart regardless of its data.
        point = ladders(sns.boxenplot(frame(), y="g", x="v"))[1]

        assert point["median"] == pytest.approx(float(np.median(GROUPS["b"])))


class TestAnotherLineOnTheAxes:
    """A median is matched by containment, not by position in ``ax.lines``.

    Taking the n-th line for the n-th ladder works on a chart seaborn drew by
    itself. Add a threshold to it and the list shifts: the first ladder is
    paired with the reference line, and every median after it is read off the
    wrong artist. A boxen with a threshold drawn on it is an ordinary chart,
    and the numbers it would report are wrong rather than missing.

    Drawn *before* the boxen as well as after, and the order is the whole
    test. Appending a threshold leaves the medians at the indices they were
    already at, so a positional match survives it and a test that only does
    that is green without exercising anything. Drawing the reference first --
    just as ordinary, and the usual way round when the threshold is context
    for the data -- puts it at index 0 and shifts every median along.
    """

    def _axes(self, first: bool):
        _, ax = plt.subplots()
        if first:
            ax.axhline(0.0, color="grey")
        sns.boxenplot(frame(), x="g", y="v", ax=ax)
        if not first:
            ax.axhline(0.0, color="grey")
        return ax

    @pytest.mark.parametrize("first", [True, False], ids=["before", "after"])
    def test_the_medians_are_still_the_medians(self, first):
        drawn = ladders(self._axes(first))

        assert len(drawn) == len(GROUPS)
        for point, values in zip(drawn, GROUPS.values()):
            assert point["median"] == pytest.approx(float(np.median(values)))

    @pytest.mark.parametrize("first", [True, False], ids=["before", "after"])
    def test_the_threshold_is_not_read_as_a_ladder(self, first):
        assert len(ladders(self._axes(first))) == len(GROUPS)


class TestDepth:
    @pytest.mark.parametrize("depth", [1, 2, 3, 5])
    def test_an_explicit_depth_is_the_depth_emitted(self, depth):
        ax = sns.boxenplot(frame(), x="g", y="v", k_depth=depth)

        for point in ladders(ax):
            assert len(point["levels"]) == depth

    def test_a_deeper_ladder_is_a_superset_of_a_shallower_one(self):
        # Depth adds rungs outward; it does not move the ones already there.
        shallow = ladders(sns.boxenplot(frame(), x="g", y="v", k_depth=2))[0]
        plt.close("all")
        deep = ladders(sns.boxenplot(frame(), x="g", y="v", k_depth=4))[0]

        assert [
            (r["p"], r["lo"], r["hi"]) for r in deep["levels"][-2:]
        ] == pytest.approx([(r["p"], r["lo"], r["hi"]) for r in shallow["levels"]])

    def test_full_depth_keeps_the_extremes(self):
        # `k_depth="full"` is the one setting whose outermost pair seaborn
        # replaces with the sample min and max. Its nominal `p` is kept rather
        # than emitted as 0, which the core would drop -- and dropping it
        # would take the range out of the reading entirely.
        point = ladders(sns.boxenplot(frame(), x="g", y="v", k_depth="full"))[0]
        deepest = point["levels"][0]

        assert deepest["lo"] == pytest.approx(float(GROUPS["a"].min()))
        assert deepest["hi"] == pytest.approx(float(GROUPS["a"].max()))
        assert 0 < deepest["p"] < 0.5


class TestOutliers:
    def test_they_are_the_values_beyond_the_deepest_rung(self):
        for point, values in zip(
            ladders(sns.boxenplot(frame(), x="g", y="v")), GROUPS.values()
        ):
            deepest = point["levels"][0]
            lower = point.get("lowerOutliers", [])
            upper = point.get("upperOutliers", [])

            assert lower == sorted(v for v in values if v < deepest["lo"])
            assert upper == sorted(v for v in values if v > deepest["hi"])

    def test_a_full_ladder_leaves_none(self):
        # `k_depth="full"` extends the boxes to the whole sample, so there is
        # nothing outside them. An empty list here is a real reading, not a
        # missing one.
        point = ladders(sns.boxenplot(frame(), x="g", y="v", k_depth="full"))[0]

        assert point.get("lowerOutliers", []) == []
        assert point.get("upperOutliers", []) == []


class TestThePayloadLoads:
    def test_it_survives_strict_json(self):
        # The core parses the SVG's `maidr` attribute with `JSON.parse`, which
        # rejects the bare `NaN`/`Infinity` tokens `json.dumps` writes (#427).
        def reject(token):
            raise ValueError(token)

        ax = sns.boxenplot(frame(), x="g", y="v")
        schema = FigureManager.get_maidr(ax.get_figure())._flatten_maidr()

        json.loads(json.dumps(schema), parse_constant=reject)
