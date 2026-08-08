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
from maidr.util.svg_utils import to_scaled_coords  # noqa: E402


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


def _svg_x_values(points: list[dict]) -> np.ndarray:
    """Pull the on-screen x coordinates out of a smooth layer's point list."""
    return np.array([float(p["svg_x"]) for p in points])


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


@pytest.fixture
def log_x_regplot_figure():
    """A regplot on a log x-axis, where data distance stops matching the screen."""
    rng = np.random.default_rng(1)
    x = np.geomspace(1, 1000, 60)
    y = np.log10(x) * 3 + rng.normal(0, 0.2, 60)

    fig, ax = plt.subplots(figsize=(6, 6))
    sns.regplot(x=x, y=y, ax=ax, ci=None)
    ax.set_xscale("log")
    yield fig
    plt.close(fig)


def test_log_axis_paces_by_the_screen_not_the_data(log_x_regplot_figure):
    """Auto-play advances a constant distance across the plot, as drawn.

    The sweep is meant to track what a sighted reader sees moving left to
    right, so a log axis has to pace by drawn distance. Uniform data steps
    would bunch almost the whole curve into the last part of the plot.
    """
    points = _smooth_points(log_x_regplot_figure)
    screen_gaps = np.abs(np.diff(_svg_x_values(points)))
    data_gaps = np.diff(_x_values(points))

    assert screen_gaps.max() / screen_gaps.min() < 2.0
    # And confirm this genuinely cost the data-space evenness, so the test
    # cannot pass by the two spacings happening to agree.
    assert data_gaps.max() / data_gaps.min() > 50


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
    [
        "regplot_figure",
        "histplot_kde_figure",
        "lowess_regplot_figure",
        "log_x_regplot_figure",
    ],
    ids=["reg", "kde", "lowess", "log"],
)
def test_smooth_points_are_evenly_spaced(figure_fixture, request):
    """Steps stay uniform on screen so auto-play paces the trend correctly."""
    fig = request.getfixturevalue(figure_fixture)
    points = _smooth_points(fig)
    gaps = np.abs(np.diff(_svg_x_values(points)))

    assert np.all(np.diff(_x_values(points)) > 0), "x must stay increasing"
    assert gaps.max() / gaps.min() < 2.0, f"uneven steps across the plot: {gaps}"


@pytest.mark.parametrize(
    "figure_fixture",
    [
        "regplot_figure",
        "histplot_kde_figure",
        "lowess_regplot_figure",
        "log_x_regplot_figure",
    ],
    ids=["reg", "kde", "lowess", "log"],
)
def test_smooth_points_span_the_whole_line(figure_fixture, request):
    """Thinning keeps both endpoints, so the trace covers the fitted range."""
    fig = request.getfixturevalue(figure_fixture)
    source_x = _source_line(fig)[:, 0]
    x = _x_values(_smooth_points(fig))

    assert x[0] == pytest.approx(source_x[0])
    assert x[-1] == pytest.approx(source_x[-1])


@pytest.fixture
def log_y_crossing_zero_figure():
    """A log y-axis whose fitted line dips below zero, which no log can map.

    Matplotlib clips such a value to a sentinel rather than refusing it, so
    this is the case ``to_scaled_coords`` has to catch by round-tripping.
    """
    rng = np.random.default_rng(3)
    x = np.linspace(1, 10, 60)
    y = np.linspace(-5, 20, 60) + rng.normal(0, 1, 60)

    fig, ax = plt.subplots()
    sns.regplot(x=x, y=y, ax=ax, ci=None)
    ax.set_yscale("log")
    yield fig
    plt.close(fig)


@pytest.fixture
def log_x_crossing_zero_figure():
    """The same unmappable case on the other axis.

    ``to_scaled_coords`` checks x and y separately, so covering only one axis
    would leave the other resting on an assumption of symmetry.
    """
    rng = np.random.default_rng(4)
    x = np.linspace(-3, 12, 60)
    y = 2 * x + rng.normal(0, 1.5, 60)

    fig, ax = plt.subplots()
    sns.regplot(x=x, y=y, ax=ax, ci=None)
    ax.set_xscale("log")
    yield fig
    plt.close(fig)


@pytest.mark.parametrize(
    "figure_fixture",
    ["log_y_crossing_zero_figure", "log_x_crossing_zero_figure"],
    ids=["log_y", "log_x"],
)
def test_unmappable_scale_is_detected(figure_fixture, request):
    """Guards the fixtures: the fallback tests mean nothing if the scale maps."""
    fig = request.getfixturevalue(figure_fixture)
    ax = FigureManager.get_axes(fig)[0]
    source = _source_line(fig)

    assert source.min(axis=0).min() < 0, "the fit must reach below zero"
    assert to_scaled_coords(ax, source[:, 0], source[:, 1]) is None


@pytest.mark.parametrize(
    "figure_fixture",
    ["log_y_crossing_zero_figure", "log_x_crossing_zero_figure"],
    ids=["log_y", "log_x"],
)
def test_unmappable_scale_still_thins_the_curve(figure_fixture, request):
    """Falling back to data space must still yield a usable trace.

    Screen-even pacing is out of reach when the scale cannot represent the
    line, but degrading to data-space spacing has to stay graceful — a full
    budget of points spanning the fit, not a collapse or a crash.
    """
    fig = request.getfixturevalue(figure_fixture)
    source_x = _source_line(fig)[:, 0]
    x = _x_values(_smooth_points(fig))
    gaps = np.diff(x)

    assert len(x) == _DEFAULT_MAX_SMOOTH_POINTS
    assert x[0] == pytest.approx(source_x[0])
    assert x[-1] == pytest.approx(source_x[-1])
    assert gaps.max() / gaps.min() < 2.0


def test_curve_within_budget_is_passed_through_untouched():
    """A short fit keeps its exact vertices, not a scale round trip's rounding.

    ``lowess`` over few points returns a fit shorter than the budget, so there
    is nothing to thin — and mapping it through a log scale and back would
    shift the values by the round trip's last bits for no gain.
    """
    rng = np.random.default_rng(5)
    x = np.sort(rng.uniform(1, 100, 12))
    y = np.log10(x) * 4 + rng.normal(0, 0.3, 12)

    fig, ax = plt.subplots()
    sns.regplot(x=x, y=y, ax=ax, ci=None, lowess=True)
    ax.set_xscale("log")
    try:
        source = _source_line(fig)
        assert len(source) <= _DEFAULT_MAX_SMOOTH_POINTS, "fit must be under budget"

        emitted = _x_values(_smooth_points(fig))

        assert np.array_equal(emitted, source[:, 0])
    finally:
        plt.close(fig)


def test_filled_kde_boundary_is_thinned_by_index():
    """A filled KDE registers its polygon outline, which has no x ordering.

    ``sns.kdeplot(fill=True)`` hands ``SmoothPlot`` the boundary of a
    ``PolyCollection`` — a closed loop that runs out along the curve and back
    along the baseline — so x doubles back and the even-x path cannot apply.
    Thinning has to fall through to vertex index and still produce a usable
    trace rather than mangling the outline.
    """
    rng = np.random.default_rng(11)
    data = rng.normal(0, 1, 400)

    fig, ax = plt.subplots()
    sns.kdeplot(data, fill=True, ax=ax)
    try:
        plots = [
            p for p in FigureManager.get_maidr(fig).plots if p.type is PlotType.SMOOTH
        ]
        assert len(plots) == 1
        assert plots[0]._is_polycollection, "fixture must exercise the poly path"

        x = _x_values(plots[0].schema["data"][0])

        assert not np.all(np.diff(x) > 0), "a closed outline must double back"
        assert len(x) == _DEFAULT_MAX_SMOOTH_POINTS
    finally:
        plt.close(fig)


def test_filled_kde_on_a_log_axis_falls_back_twice():
    """Both fallbacks compose: an unmappable scale, then a curve with no order.

    A filled KDE's support runs past its data, into x values a log axis cannot
    map, so the scale falls back to data space — and the outline is a closed
    loop, so thinning falls back again to vertex index. Each is covered alone;
    this pins that stacking them still yields a full, usable trace.
    """
    rng = np.random.default_rng(21)
    data = rng.lognormal(3.0, 0.45, 500)

    fig, ax = plt.subplots()
    sns.kdeplot(data, fill=True, ax=ax)
    ax.set_xscale("log")
    try:
        plots = [
            p for p in FigureManager.get_maidr(fig).plots if p.type is PlotType.SMOOTH
        ]
        assert len(plots) == 1
        points = plots[0].schema["data"][0]
        source = np.asarray(plots[0]._elements[0].get_xydata())

        assert plots[0]._is_polycollection, "fixture must exercise the poly path"
        assert source[:, 0].min() <= 0, "support must reach where a log cannot map"
        assert to_scaled_coords(ax, source[:, 0], source[:, 1]) is None

        x = _x_values(points)

        assert not np.all(np.diff(x) > 0), "a closed outline must double back"
        assert len(x) == _DEFAULT_MAX_SMOOTH_POINTS
    finally:
        plt.close(fig)


def test_resample_curve_keeps_a_straight_line_at_full_budget():
    """Collinear points carry no shape, so only the spacing can guide us."""
    points = np.column_stack([np.linspace(0, 1, 100), np.linspace(0, 2, 100)])

    kept = resample_curve(points, target=30)

    assert len(kept) == 30

    gaps = np.diff(kept[:, 0])
    assert gaps.max() / gaps.min() < 2.0


def test_resample_curve_returns_short_curves_untouched():
    """Nothing to thin when the curve already fits in the budget.

    Identity, not just equality: the docstring promises the input array back
    rather than a copy, so a refactor that quietly started copying would be a
    contract change even though every value still matched.
    """
    points = np.column_stack([np.arange(5.0), np.arange(5.0) ** 2])

    kept = resample_curve(points, target=30)

    assert kept is points


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
