"""A regression line was announced without the band around it (#919).

``ci=95`` is seaborn's default, and the band is the reason a regression is
drawn rather than a bare line: it says how much of the trend the data
supports. ``SmoothPlot`` emitted only the fitted values, so a reader was told
the trend and nothing about how well determined it is.

The bounds ride on the fitted samples as ``yMin``/``yMax``, which is the shape
``LineTrace`` reads since xability/maidr#920 -- so the value and its interval
are heard at one x rather than by switching layers. ``SmoothTrace`` extends
``LineTrace``, so a smooth layer carries them with nothing further needed.

Two facts about seaborn's band decided the implementation, and both were
measured rather than assumed:

* Its polygon runs out along one edge and back along the other. On a
  100-sample fit that is **203 vertices**, with individual x values appearing
  2, 3 or 4 times, so a positional split of the ring would be fragile in the
  way that yields a plausible wrong answer. The edges are recovered by taking
  the lowest and highest vertex at each x.
* The curve is **resampled** before it is emitted, not thinned to a subset.
  Measured: only the two endpoints of a 30-point output were among the band's
  own x values, so a lookup would have attached bounds to 2 points and left 28
  silently bare. The bounds are interpolated instead, which is also how
  matplotlib draws the band between its vertices.
"""

from __future__ import annotations

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


def regression_axes(ci: int | None = 95):
    """Draw a regression whose scatter is loose enough to have a real band."""
    rng = np.random.default_rng(0)
    x = np.arange(1, 21)
    y = x + rng.normal(scale=2.0, size=x.size)
    return sns.regplot(x=x, y=y, ci=ci)


def smooth_points(ax) -> list[dict]:
    maidr = FigureManager.get_maidr(ax.get_figure())
    smooth = [p for p in maidr._plots if str(p.type).endswith("SMOOTH")]
    assert len(smooth) == 1, f"expected one smooth layer, got {len(smooth)}"
    return smooth[0].schema["data"][0]


class TestTheBandReachesTheSchema:
    def test_every_fitted_sample_carries_its_bounds(self):
        # Not "most of them": the resampling is what makes this the assertion
        # worth writing, since a lookup passes on the endpoints alone.
        points = smooth_points(regression_axes())

        assert points
        assert all("yMin" in point and "yMax" in point for point in points)

    def test_the_bounds_bracket_the_fit(self):
        # The band is around the curve, so a point outside it means the two
        # edges were read the wrong way round -- the failure a positional
        # split of the polygon invites.
        points = smooth_points(regression_axes())

        assert all(
            point["yMin"] <= point["y"] <= point["yMax"] for point in points
        )

    def test_the_band_has_width(self):
        # A band collapsed to the line would satisfy the bracketing test above
        # while telling the reader nothing.
        points = smooth_points(regression_axes())

        assert any(point["yMax"] - point["yMin"] > 0 for point in points)

    def test_the_fitted_values_are_untouched(self):
        # The band is added beside the curve, not instead of it.
        points = smooth_points(regression_axes())

        assert all("x" in point and "y" in point for point in points)
        assert all("svg_x" in point and "svg_y" in point for point in points)


class TestAChartWithNoBand:
    def test_ci_none_carries_no_bounds(self):
        points = smooth_points(regression_axes(ci=None))

        assert points
        assert all("yMin" not in point for point in points)
        assert all("yMax" not in point for point in points)

    def test_the_curve_is_still_emitted(self):
        # The feature has to be invisible to a regression drawn without one.
        points = smooth_points(regression_axes(ci=None))

        assert all("x" in point and "y" in point for point in points)


class TestTheBandIsReadRatherThanGuessed:
    """What the two measurements above are protecting.

    Both would produce output that looks right at a glance -- a schema with
    `yMin`/`yMax` keys on it -- so they are pinned by what the numbers say
    rather than by whether the keys exist.
    """

    def test_the_interval_narrows_where_the_data_is_dense(self):
        # A confidence band on a linear fit is narrowest near the centre of x
        # and widest at the ends. If the bounds were read off the wrong
        # vertices, or interpolated against a mismatched grid, that shape is
        # the first thing to go.
        points = smooth_points(regression_axes())
        widths = [point["yMax"] - point["yMin"] for point in points]
        middle = widths[len(widths) // 2]

        assert middle < widths[0]
        assert middle < widths[-1]

    def test_a_shaded_region_that_is_not_the_band_is_not_read_as_one(self):
        # The type test alone does not identify the band: seaborn draws a
        # violin body with `fill_betweenx`, so a violin is the *same class* as
        # a confidence band. Verified below rather than asserted from the
        # docs.
        #
        # What separates them is that a band brackets every fitted sample and
        # an unrelated shaded region does not, so the reading validates itself
        # rather than trusting the class name.
        rng = np.random.default_rng(1)
        violin_ax = sns.violinplot(x=rng.normal(size=60))
        assert [
            c
            for c in violin_ax.collections
            if type(c).__name__ == "FillBetweenPolyCollection"
        ], "expected seaborn to draw the violin body with fill_betweenx"
        plt.close("all")

        # A regression with its own band switched off, beside a shaded region
        # of the same class sitting well away from the fit. Drawn with
        # `fill_between` directly rather than as a violin, so the axes carries
        # exactly one smooth layer and the assertion is about the band alone.
        x = np.arange(1, 21)
        y = x + rng.normal(scale=2.0, size=x.size)
        ax = sns.regplot(x=x, y=y, ci=None)
        ax.fill_between(x, y - 100, y - 90, alpha=0.2)

        assert [
            c
            for c in ax.collections
            if type(c).__name__ == "FillBetweenPolyCollection"
        ], "the decoy region should be on the axes"
        assert all("yMin" not in point for point in smooth_points(ax))
