"""Tests for error bar plots.

``Axes.errorbar`` is the call that carries uncertainty, and uncertainty is
frequently the finding rather than the decoration: whether two group means
differ is answered by whether their intervals overlap. Until this was patched
a MAIDR reader got the estimate and nothing else.

The bounds are read off the drawn ``LineCollection`` rather than recomputed
from the ``yerr`` the caller passed, because those are different quantities --
matplotlib takes an offset, the schema carries an absolute position -- and the
offset has three shapes before ``uplims``/``lolims`` change the meaning again.
These tests are written against the cases that distinguish those, so an
implementation that reverted to arithmetic on ``yerr`` would fail rather than
coincide.
"""

from __future__ import annotations

import datetime

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


#: Three group means with asymmetric intervals. Every number is distinct, so a
#: reading that took the wrong bound, or the wrong sample, cannot coincide with
#: the right one.
X = [0, 1, 2]
Y = [4.2, 5.1, 7.3]
#: Lower and upper offsets, deliberately unequal per side and per sample.
YERR = [[0.4, 1.1, 0.2], [0.4, 1.5, 0.1]]


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _plots(fig):
    """
    Return the MAIDR plots registered for a figure, or an empty list.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    list
        The registered plots; empty when the figure registered nothing.
    """
    try:
        return FigureManager.get_maidr(fig).plots
    except KeyError:
        return []


def _schema(fig):
    """
    Render the sole registered layer's schema.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    dict
        The layer schema.
    """
    plots = _plots(fig)
    assert len(plots) == 1, f"expected exactly one layer, got {len(plots)}"
    return plots[0].render()


def test_errorbar_registers_an_error_bar_layer():
    """A call with error bars registers as the error bar type."""
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=YERR)

    assert _plots(fig)[0].type == PlotType.ERRORBAR


def test_asymmetric_bounds_are_absolute_positions():
    """
    The emitted bounds are where the bar was drawn, not the offsets passed.

    This is the distinction the schema exists to fix. A reader told "0.4"
    instead of "3.8" is being given a number the chart does not draw anywhere,
    and for an asymmetric interval the two offsets differ per side, so an
    implementation that emitted offsets would be wrong twice per sample.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=YERR)

    points = _schema(fig)["data"]

    assert points[0] == {"x": 0.0, "y": 4.2, "yMin": 3.8, "yMax": 4.6}
    assert points[1] == {"x": 1.0, "y": 5.1, "yMin": 4.0, "yMax": 6.6}
    assert points[2] == {"x": 2.0, "y": 7.3, "yMin": 7.1, "yMax": 7.4}


def test_bounds_carry_no_float_noise():
    """
    A derived bound is announced as the chart draws it, not to 17 digits.

    matplotlib computes the bar endpoint as ``y - err``, and ``4.2 - 0.4`` is
    ``3.8000000000000003`` in IEEE 754. A screen reader spells every one of
    those digits out, so the exact comparison here is the assertion -- not an
    approximate one, which would pass on the noisy value it exists to reject.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=YERR)

    lower = _schema(fig)["data"][0]["yMin"]

    assert repr(lower) == "3.8"


def test_a_tiny_interval_survives_the_noise_stripping():
    """
    Cleaning the noise must not round a small interval away to nothing.

    Rounding to a fixed number of decimals would report this bound as equal to
    the estimate, which is a worse answer than the noise it was meant to
    remove.
    """
    fig, ax = plt.subplots()
    ax.errorbar([0], [1.0], yerr=[0.0005])

    point = _schema(fig)["data"][0]

    assert point["yMin"] == 0.9995
    assert point["yMax"] == 1.0005


def test_symmetric_error_expands_to_both_bounds():
    """A scalar ``yerr`` applies to both sides of every sample."""
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=0.5)

    points = _schema(fig)["data"]

    assert [point["yMin"] for point in points] == [3.7, 4.6, 6.8]
    assert [point["yMax"] for point in points] == [4.7, 5.6, 7.8]


def test_one_sided_error_reads_the_bound_that_exists():
    """
    A zero on one side is a real bound at the estimate, not a missing one.

    ``uplims``/``lolims`` and a zero offset both draw a bar that stops at the
    estimate. Reading the drawn geometry gets that right without special
    casing, which is the reason for reading geometry at all.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=[[0, 0, 0], [0.4, 0.5, 0.6]])

    points = _schema(fig)["data"]

    # The lower bound coincides with the estimate; the upper is above it.
    assert [point["yMin"] for point in points] == Y
    assert [point["yMax"] for point in points] == [4.6, 5.6, 7.9]


def test_horizontal_error_reports_horz_orientation():
    """
    ``xerr`` draws the interval along x, and the layer says so.

    The schema names the category ``x`` and the magnitude ``y`` in both
    orientations, exactly as the box plot already travels, and lets
    ``orientation`` say which is on screen where. Asserting the swap is what
    stops the axes being read back to front.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, xerr=0.3)

    schema = _schema(fig)

    assert schema["orientation"] == "horz"
    # Category is the y position, magnitude is the x value it spans.
    assert schema["data"][0] == {"x": 4.2, "y": 0.0, "yMin": -0.3, "yMax": 0.3}


def test_vertical_error_reports_vert_orientation():
    """``yerr`` is the vertical case, and the default."""
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=0.5)

    assert _schema(fig)["orientation"] == "vert"


def test_both_axes_of_error_describe_the_vertical_interval():
    """
    A call passing both errors describes the y interval.

    Only one interval fits the trace, and ``yerr`` is the conventional
    reading. Pinned because matplotlib renders the two collections x-first:
    taking ``lines[2][0]`` unconditionally would silently describe the x
    interval on every chart that passes both.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, xerr=0.3, yerr=0.5)

    schema = _schema(fig)

    assert schema["orientation"] == "vert"
    assert schema["data"][0] == {"x": 0.0, "y": 4.2, "yMin": 3.7, "yMax": 4.7}


def test_fmt_none_still_reports_the_estimates():
    """
    ``fmt="none"`` draws intervals without markers, and still reads.

    The container has no data line in this mode, and the estimate is not
    recoverable from the geometry -- an asymmetric bar is not centred on its
    own midpoint -- so the centres come from the call's arguments. Asymmetric
    on purpose: a midpoint fallback would pass on a symmetric fixture.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=YERR, fmt="none")

    points = _schema(fig)["data"]

    assert [point["y"] for point in points] == Y
    assert points[1] == {"x": 1.0, "y": 5.1, "yMin": 4.0, "yMax": 6.6}


def test_a_nan_error_drops_only_that_sample_s_bounds():
    """
    One unmeasured sample leaves its neighbours intact.

    matplotlib renders a NaN error as an empty segment that keeps its place in
    the list, so the samples stay aligned -- but there is no endpoint to read.
    Emitting no bounds is what the JS trace treats as "this sample has none";
    emitting NaN would poison the trace's whole pitch range.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=[0.4, np.nan, 0.2])

    points = _schema(fig)["data"]

    assert points[1] == {"x": 1.0, "y": 5.1}
    assert points[0]["yMin"] == 3.8
    assert points[2]["yMax"] == 7.5


def test_a_call_with_no_error_still_registers_its_points():
    """
    ``errorbar`` without any error is a legitimate call, and reads as points.

    It draws bare estimates, so the layer carries them with no bounds rather
    than failing -- a chart that raised here would break the user's figure over
    a call matplotlib is perfectly happy with.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y)

    points = _schema(fig)["data"]

    assert points == [
        {"x": 0.0, "y": 4.2},
        {"x": 1.0, "y": 5.1},
        {"x": 2.0, "y": 7.3},
    ]


def test_categorical_x_keeps_its_labels():
    """A categorical axis is announced by name, not by tick position."""
    fig, ax = plt.subplots()
    ax.errorbar(["control", "low", "high"], Y, yerr=0.5)

    points = _schema(fig)["data"]

    assert [point["x"] for point in points] == ["control", "low", "high"]


def test_a_date_axis_does_not_break_the_figure():
    """
    Error bars on a time series read, rather than raising.

    ``ax.errorbar(dates, ...)`` is ordinary on a time series, and matplotlib
    hands the dates back as ``datetime`` objects rather than as the ordinals it
    drew. Coercing those to float raises, which would take out the user's whole
    figure over an axis matplotlib is perfectly happy with -- so the label
    travels as a string, which the schema allows for ``x``.
    """
    dates = [datetime.date(2026, 1, day) for day in (1, 2, 3)]

    fig, ax = plt.subplots()
    ax.errorbar(dates, Y, yerr=0.5)

    points = _schema(fig)["data"]

    assert [point["x"] for point in points] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    # The magnitude and its bounds are still numbers, so sonification works.
    assert points[0]["y"] == 4.2
    assert points[0]["yMin"] == 3.7


def test_two_calls_register_two_distinct_layers():
    """
    Each ``errorbar`` call describes its own series.

    The layer is handed the container its own call produced. Looking one up on
    the axes instead would find the first container both times, describing the
    first series twice and dropping the second with no error to say so -- which
    is the failure this pins.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=0.5)
    ax.errorbar(X, [1.0, 2.0, 3.0], yerr=0.2)

    plots = _plots(fig)
    assert len(plots) == 2

    first, second = (plot.render()["data"] for plot in plots)
    assert [point["y"] for point in first] == Y
    assert [point["y"] for point in second] == [1.0, 2.0, 3.0]


def test_errorbar_supports_highlighting():
    """
    The bar collection is tagged, so the interval under the cursor highlights.

    Both halves are asserted because the flag alone is weak:
    ``_support_highlighting`` starts True and is only ever cleared, so it
    cannot detect a dropped tagging call. ``elements`` is what the claim
    actually rests on.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=0.5)

    plot = _plots(fig)[0]
    plot._extract_plot_data()

    assert plot._support_highlighting is True
    assert plot.elements, "the bar LineCollection should be tagged"


@pytest.mark.parametrize(
    ("draw", "expected"),
    [
        (lambda ax, df: sns.barplot(df, x="g", y="v", ax=ax), PlotType.BAR),
        (lambda ax, df: sns.pointplot(df, x="g", y="v", ax=ax), PlotType.LINE),
    ],
    ids=["barplot", "pointplot"],
)
def test_seaborn_error_bars_do_not_register_a_second_layer(draw, expected):
    """
    Patching ``Axes.errorbar`` must not add a layer to seaborn's own charts.

    ``sns.barplot`` and ``sns.pointplot`` both draw a confidence interval by
    default. Were either to route through ``Axes.errorbar``, this patch would
    hand the user a second layer describing the same chart -- an extra thing to
    navigate that the figure does not contain.

    Pinned rather than assumed, because it is a claim about another library's
    internals: current seaborn renders those intervals itself, and the day it
    switches, this test is what says so.
    """
    rng = np.random.default_rng(20260811)
    df = pd.DataFrame({"g": ["a"] * 20 + ["b"] * 20, "v": rng.normal(size=40)})

    fig, ax = plt.subplots()
    draw(ax, df)

    plots = _plots(fig)
    assert len(plots) == 1
    assert plots[0].type == expected


def test_the_selector_reaches_one_element_per_sample():
    """
    The layer's selector addresses the drawn bars, one path per sample.

    matplotlib renders the bar ``LineCollection`` as a group of paths in data
    order, which is the shape the JS trace repeats across its three sections.
    A selector resolving to a different count makes that trace drop the
    highlight entirely rather than fail loudly.
    """
    fig, ax = plt.subplots()
    ax.errorbar(X, Y, yerr=0.5)

    assert _schema(fig)["selectors"] == "g[maidr='true'] > path"
