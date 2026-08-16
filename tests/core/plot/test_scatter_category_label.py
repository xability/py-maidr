"""A categorical scatter announced a slot index where the chart shows a name.

#439 fixed the *position*: `sns.stripplot` scatters each point sideways by a
random offset and `sns.swarmplot` packs them, and the offset -- not the
observation -- was what `get_offsets()` returned and what was announced.
Snapping to the tick stopped a rendering artefact being reported as a
measurement, and restored column navigation, since `ScatterTrace` groups
columns by exact `x` equality and 90 jittered points made 90 columns of one.

It could not fix the *name*. `ScatterPoint.x` is typed `number` in the
grammar, and the trace subtracts x values to sort, to index columns and to
resolve a highlight, so a string there gives an unstable sort and a broken
index rather than an announcement. A reader still heard "g is 0" where the
chart says "a".

xability/maidr#927 added `xLabel` / `yLabel` for exactly this: the name
travels *alongside* the position rather than replacing it, which is also what
the chart is -- a category at a slot. This is the producer half.

Both axes are asked, because either can be the categorical one:
`sns.stripplot(df, x='g', y='v')` puts the names on x and
`sns.stripplot(df, y='g', x='v')` puts them on y. Asking about x alone was
itself the #353 defect.
"""

from __future__ import annotations

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


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "g": np.repeat(list("abc"), 8),
            "v": np.random.default_rng(0).normal(size=24),
        }
    )


def points(ax) -> list[dict]:
    """Every sample of every point layer on the axes, in layer order."""
    ax = getattr(ax, "axes", ax)
    maidr = FigureManager.get_maidr(ax.get_figure())
    return [
        sample
        for plot in maidr._plots
        if plot.type.value == "point"
        for sample in plot.schema["data"]
    ]


@pytest.mark.parametrize("kind", ["stripplot", "swarmplot"])
class TestTheCategoryAxisIsNamed:
    def test_every_sample_carries_its_category(self, kind):
        drawn = points(getattr(sns, kind)(frame(), x="g", y="v"))

        assert {sample["xLabel"] for sample in drawn} == {"a", "b", "c"}

    def test_the_name_matches_the_slot_it_sits_on(self, kind):
        # The pairing is the point. A layer that named every sample "a" would
        # satisfy the set test above and be useless.
        drawn = points(getattr(sns, kind)(frame(), x="g", y="v"))
        pairs = {(sample["x"], sample["xLabel"]) for sample in drawn}

        assert pairs == {(0.0, "a"), (1.0, "b"), (2.0, "c")}

    def test_the_measurement_axis_is_not_named(self, kind):
        # y carries real numbers here; naming those would be the same defect
        # mirrored, and there are no y tick names to draw on anyway.
        drawn = points(getattr(sns, kind)(frame(), x="g", y="v"))

        assert not any("yLabel" in sample for sample in drawn)

    def test_the_position_is_still_the_tick_not_the_jitter(self, kind):
        # The half #439 already fixed, pinned here too: the label must not
        # arrive at the cost of the coordinate drifting back to the offset.
        drawn = points(getattr(sns, kind)(frame(), x="g", y="v"))

        assert {sample["x"] for sample in drawn} == {0.0, 1.0, 2.0}


class TestTurnedOnItsSide:
    """Categories sit on y when the chart is horizontal."""

    def test_the_y_axis_is_named(self):
        drawn = points(sns.stripplot(frame(), y="g", x="v"))

        assert {(sample["y"], sample["yLabel"]) for sample in drawn} == {
            (0.0, "a"),
            (1.0, "b"),
            (2.0, "c"),
        }

    def test_the_measurement_axis_is_not_named(self):
        drawn = points(sns.stripplot(frame(), y="g", x="v"))

        assert not any("xLabel" in sample for sample in drawn)


class TestWhatMustNotChange:
    def test_a_numeric_scatter_carries_no_labels(self):
        # The guard that matters most. `_category_tick_labels` is empty on a
        # numeric axis -- matplotlib leaves a `UnitData` only where it mapped
        # strings -- so a measurement cannot be renamed after whichever tick it
        # happens to fall nearest.
        _, ax = plt.subplots()
        ax.scatter([1.5, 2.5], [10, 20])
        drawn = points(ax)

        assert drawn == [{"x": 1.5, "y": 10.0}, {"x": 2.5, "y": 20.0}]

    def test_a_numeric_scatter_keeps_its_exact_values(self):
        # Snapping a measurement onto a gridline would round every value while
        # the payload still looked like a scatter plot.
        _, ax = plt.subplots()
        ax.scatter([0.37, 1.84], [3.14, 2.72])

        assert [(p["x"], p["y"]) for p in points(ax)] == [
            (0.37, 3.14),
            (1.84, 2.72),
        ]

    def test_a_categorical_scatterplot_is_named_too(self):
        # Not only the jittering charts: `sns.scatterplot` on a discrete x
        # reaches the same axis, and a reader there was equally unserved.
        drawn = points(sns.scatterplot(frame(), x="g", y="v"))

        assert {sample["xLabel"] for sample in drawn} == {"a", "b", "c"}
