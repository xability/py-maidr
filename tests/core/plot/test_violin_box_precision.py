"""Rounding violin box statistics to 4 decimals flattened small data (#398).

`round(x, 4)` is absolute, not significant. It does not keep four digits of
precision; it discards everything below `1e-4`. For any dataset sitting under
that -- micrograms, molar concentrations, failure probabilities, seconds in a
fast benchmark -- every statistic came out `0.0`, so `min`, `q1`, `q2`, `q3`
and `max` were identical and the box read as a flat line at zero.

Nothing errored. The chart drew correctly, the layer was present, the count of
violins was right. Only the distribution was gone.

Formatting for announcement belongs to the frontend, which is the only place
that can choose digits relative to the magnitude. Emitting raw also settles
two disagreements this path was on the wrong side of: the outliers emitted
beside these keys were never rounded, and neither the matplotlib box plot nor
the plotly violin path rounds at all.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402,F401
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

sns = pytest.importorskip("seaborn")
pd = pytest.importorskip("pandas")

#: Well below the old 1e-4 floor, and the scale at which the failure was total.
MICRO = 2e-6


def box_layer(frame) -> dict:
    figure, axes = plt.subplots()
    try:
        sns.violinplot(data=frame, x="g", y="v", ax=axes)
        layers = FigureManager.get_maidr(figure)._flatten_maidr()["subplots"][0][0][
            "layers"
        ]
        return next(
            layer for layer in layers if layer["type"] is PlotType.VIOLIN_BOX
        )["data"][0]
    finally:
        plt.close(figure)


def micro_frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame({"g": ["a"] * 40, "v": rng.normal(MICRO, 3e-7, 40)})


class TestSmallMagnitudesSurvive:
    def test_the_quartiles_are_not_all_zero(self):
        record = box_layer(micro_frame())
        stats = [record[key] for key in ("min", "q1", "q2", "q3", "max")]
        assert not all(value == 0.0 for value in stats)

    def test_the_five_statistics_stay_distinct(self):
        # The failure's real shape: not merely small numbers, but a box whose
        # every edge collapsed onto the same one, so the distribution stopped
        # being announced at all.
        record = box_layer(micro_frame())
        stats = [record[key] for key in ("min", "q1", "q2", "q3", "max")]
        assert len(set(stats)) == len(stats)

    def test_the_values_land_at_the_data_s_own_scale(self):
        record = box_layer(micro_frame())
        assert record["q2"] == pytest.approx(MICRO, rel=0.5)

    def test_the_order_still_holds(self):
        record = box_layer(micro_frame())
        assert (
            record["min"]
            <= record["q1"]
            <= record["q2"]
            <= record["q3"]
            <= record["max"]
        )


class TestOrdinaryMagnitudesAreUnchangedInMeaning:
    def frame(self) -> pd.DataFrame:
        rng = np.random.default_rng(0)
        return pd.DataFrame({"g": ["a"] * 40, "v": rng.normal(2.0, 0.3, 40)})

    def test_the_statistics_are_still_ordered(self):
        record = box_layer(self.frame())
        assert (
            record["min"]
            <= record["q1"]
            <= record["q2"]
            <= record["q3"]
            <= record["max"]
        )

    def test_full_precision_now_reaches_the_schema(self):
        # The other end of the same change: at an ordinary scale the old code
        # truncated real digits rather than erasing the number. At least one
        # of the five must now differ from its own four-decimal rounding, or
        # the rounding is still happening somewhere.
        record = box_layer(self.frame())
        stats = [record[key] for key in ("min", "q1", "q2", "q3", "max")]
        assert any(value != round(value, 4) for value in stats)


class TestTheRecordIsInternallyConsistent:
    def test_outliers_and_quartiles_are_both_raw(self):
        # The outliers were never rounded, so a rounded quartile could sit
        # beside a full-precision outlier in one record and the two would not
        # be comparable.
        frame = pd.DataFrame(
            {"g": ["a"] * 11, "v": [-5e-5] + [1e-6 * i for i in range(1, 11)]}
        )
        record = box_layer(frame)
        outliers = record["lowerOutliers"] + record["upperOutliers"]
        if outliers:
            assert not all(value == 0.0 for value in outliers)
        assert record["q1"] != 0.0
