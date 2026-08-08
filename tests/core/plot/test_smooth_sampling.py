"""Tests that a smooth layer keeps evenly spaced, navigable points.

A smooth trace is navigated and auto-played one point at a time at a fixed
rate, so the emitted points have to stay spread along the line.  Shape-based
simplification does the opposite: it collapses a straight fit to its two
endpoints and clusters the survivors of a curved fit around the bends.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot.regplot import _DEFAULT_MAX_SMOOTH_POINTS  # noqa: E402
from maidr.util.rdp_utils import resample_curve  # noqa: E402
from maidr.util.regression_line_utils import find_regression_line  # noqa: E402


def _smooth_points(fig) -> list[dict]:
    """Return the point list of the figure's single smooth layer."""
    plots = FigureManager.get_maidr(fig).plots
    smooth = [p for p in plots if p.type is PlotType.SMOOTH]
    assert len(smooth) == 1, f"expected one smooth layer, got {len(smooth)}"
    return smooth[0].schema["data"][0]


def _source_line(fig) -> np.ndarray:
    """Return the vertices of the line the extractor actually reads.

    Resolved through ``find_regression_line`` — the same lookup
    ``SmoothPlot`` uses — so a test's idea of the source curve cannot drift
    from the extractor's if seaborn ever adds another ``Line2D`` to the axes.
    """
    line = find_regression_line(FigureManager.get_axes(fig)[0])
    assert line is not None, "no regression line found on the axes"
    return np.asarray(line.get_xydata())


def _x_values(points: list[dict]) -> np.ndarray:
    """Pull the x coordinates out of a smooth layer's point list."""
    return np.array([float(p[MaidrKey.X]) for p in points])


@pytest.fixture
def regplot_figure():
    """A seaborn regplot whose fitted line is perfectly straight."""
    rng = np.random.default_rng(42)
    x = np.linspace(0, 10, 50)
    y = 2 * x + 1 + rng.normal(0, 1.5, 50)

    fig, ax = plt.subplots()
    sns.regplot(x=x, y=y, ax=ax)
    yield fig
    plt.close(fig)


@pytest.fixture
def histplot_kde_figure():
    """A seaborn histogram with an overlaid — and genuinely curved — KDE."""
    rng = np.random.default_rng(7)
    data = np.concatenate([rng.normal(-2, 0.5, 300), rng.normal(2, 0.8, 300)])

    fig, ax = plt.subplots()
    sns.histplot(data, kde=True, ax=ax)
    yield fig
    plt.close(fig)


@pytest.fixture
def lowess_regplot_figure():
    """A lowess fit over clustered x, the case a uniform grid does not cover.

    ``statsmodels``'s lowess returns y-hat at the *observed* x values, so a
    skewed sample hands the extractor a curve whose own vertices bunch up at
    one end — unlike a plain fit or a KDE, which seaborn evaluates on a
    ``linspace`` grid.
    """
    rng = np.random.default_rng(0)
    x = np.sort(rng.exponential(2.0, 80))
    y = 2 * x + rng.normal(0, 1.5, 80)

    fig, ax = plt.subplots()
    sns.regplot(x=x, y=y, ax=ax, ci=None, lowess=True)
    yield fig
    plt.close(fig)


def test_lowess_fit_source_curve_really_is_clustered(lowess_regplot_figure):
    """Guards the fixture: without clustered input the next test proves nothing."""
    gaps = np.diff(_source_line(lowess_regplot_figure)[:, 0])

    assert gaps.max() / gaps.min() > 50


def test_straight_regression_line_is_not_collapsed_to_its_endpoints(regplot_figure):
    """A linear fit must stay navigable, not shrink to a start and an end."""
    points = _smooth_points(regplot_figure)

    assert len(points) > 2


def test_straight_regression_line_keeps_the_full_point_budget(regplot_figure):
    """A fit longer than the budget is thinned to it exactly, not below.

    The expected count is derived from the fitted line rather than hard-coded,
    so the assertion tracks ``resample_curve``'s contract instead of whichever
    grid size seaborn happens to evaluate the fit on.
    """
    expected = min(_DEFAULT_MAX_SMOOTH_POINTS, len(_source_line(regplot_figure)))

    points = _smooth_points(regplot_figure)

    assert len(points) == expected


@pytest.mark.parametrize(
    "figure_fixture",
    ["regplot_figure", "histplot_kde_figure", "lowess_regplot_figure"],
    ids=["reg", "kde", "lowess"],
)
def test_smooth_points_are_evenly_spaced(figure_fixture, request):
    """Steps along x stay uniform so auto-play paces the trend correctly."""
    fig = request.getfixturevalue(figure_fixture)
    x = _x_values(_smooth_points(fig))
    gaps = np.diff(x)

    assert np.all(gaps > 0), "x must stay monotonically increasing"
    assert gaps.max() / gaps.min() < 2.0, f"uneven steps along x: {gaps}"


@pytest.mark.parametrize(
    "figure_fixture",
    ["regplot_figure", "histplot_kde_figure", "lowess_regplot_figure"],
    ids=["reg", "kde", "lowess"],
)
def test_smooth_points_span_the_whole_line(figure_fixture, request):
    """Thinning keeps both endpoints, so the trace covers the fitted range."""
    fig = request.getfixturevalue(figure_fixture)
    source_x = _source_line(fig)[:, 0]
    x = _x_values(_smooth_points(fig))

    assert x[0] == pytest.approx(source_x[0])
    assert x[-1] == pytest.approx(source_x[-1])


def test_resample_curve_keeps_a_straight_line_at_full_budget():
    """Collinear points carry no shape, so only the spacing can guide us."""
    points = np.column_stack([np.linspace(0, 1, 100), np.linspace(0, 2, 100)])

    kept = resample_curve(points, target=30)

    assert len(kept) == 30

    gaps = np.diff(kept[:, 0])
    assert gaps.max() / gaps.min() < 2.0


def test_resample_curve_returns_short_curves_untouched():
    """Nothing to thin when the curve already fits in the budget."""
    points = np.column_stack([np.arange(5.0), np.arange(5.0) ** 2])

    kept = resample_curve(points, target=30)

    assert np.array_equal(kept, points)


@pytest.mark.parametrize("n,target", [(100, 30), (31, 30), (61, 30), (7, 5)])
def test_resample_curve_returns_exactly_the_requested_count(n, target):
    """Rounding never collapses two samples onto one vertex.

    The step between samples stays above 1 whenever the curve is longer than
    the target, which is what makes the count exact even at awkward ratios.
    """
    points = np.column_stack([np.linspace(0, 1, n), np.linspace(0, 1, n) ** 2])

    kept = resample_curve(points, target=target)

    assert len(kept) == target


def test_resample_curve_evens_out_a_clustered_source_curve():
    """A lowess fit lands on the observed x values and inherits their gaps.

    Sampling such a curve by vertex index would carry the clustering straight
    through into the emitted points, which is what auto-play pacing feels.
    """
    x = np.concatenate([np.linspace(0, 1, 90), np.linspace(2, 10, 10)])
    points = np.column_stack([x, x**2])
    source_gaps = np.diff(x)
    assert source_gaps.max() / source_gaps.min() > 50, "fixture must be clustered"

    kept = resample_curve(points, target=30)

    gaps = np.diff(kept[:, 0])
    assert gaps.max() / gaps.min() < 2.0, f"clustering survived: {gaps}"


def test_resample_curve_falls_back_to_index_sampling_when_x_doubles_back():
    """A curve with no usable x ordering still gets thinned, just by index."""
    t = np.linspace(0, 2 * np.pi, 100)
    points = np.column_stack([np.cos(t), np.sin(t)])

    kept = resample_curve(points, target=30)

    assert len(kept) == 30
    assert np.array_equal(kept[0], points[0])
    assert np.array_equal(kept[-1], points[-1])


def test_resample_curve_keeps_both_endpoints():
    """The first and last vertices anchor the navigable range."""
    points = np.column_stack([np.linspace(0, 7, 61), np.sin(np.linspace(0, 7, 61))])

    kept = resample_curve(points, target=10)

    assert np.array_equal(kept[0], points[0])
    assert np.array_equal(kept[-1], points[-1])
