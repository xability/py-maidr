"""`Axes.contour` draws a scalar field, and it was read as nothing.

A contour is the one chart of its family whose value is a **number rather than
a colour**. `QuadContourSet.levels` is the data the caller asked for and
`get_paths()` returns one path per level, so both halves invert exactly and
nothing has to be recovered from a fill -- which is precisely what left the
same chart unread in the Observable adapter (xability/maidr#1084), where a
contour keeps its magnitude only in a continuous colour.

Two things about the drawing had to be decided rather than assumed.

**A level is not one curve.** A field with two peaks crosses a level twice, and
matplotlib draws both islands in a single compound path with two `MOVETO`s.
Read as one series they would be joined by a straight line running between the
peaks -- a curve announced across ground the field never took, which is the
defect xability/maidr#1079 describes for a gappy line.

**A filled contour is a different chart.** `contourf` draws the bands *between*
levels: three levels give two paths, and each outline runs along two different
level curves stitched together. Announcing one as "the 0.2 contour" would be
right for half of its points, so it is declined -- and so is a filled bivariate
`kdeplot`, for the same reason.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.exception import UnsupportedPlotError  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _field(peaks: int = 1):
    """A gaussian bump, or two of them side by side."""
    axis = np.linspace(-3, 3, 40)
    x, y = np.meshgrid(axis, axis)
    if peaks == 1:
        return x, y, np.exp(-(x**2 + y**2))
    return x, y, np.exp(-((x - 1.5) ** 2 + y**2)) + np.exp(-((x + 1.5) ** 2 + y**2))


def _layers(fig):
    """The layers registered for a figure, or an empty list when there are none."""
    try:
        return FigureManager.get_maidr(fig).plots
    except UnsupportedPlotError:
        return []


def _series(fig, index: int = 0):
    """One layer's curves."""
    return _layers(fig)[index].schema[MaidrKey.DATA]


def test_a_contour_is_read_as_the_field_it_draws():
    fig, ax = plt.subplots()

    ax.contour(*_field(), levels=[0.2, 0.5, 0.8])

    assert [layer.type for layer in _layers(fig)] == [PlotType.CONTOUR]


def test_every_curve_carries_the_level_it_runs_at():
    # The levels are the ones the caller asked for, taken off `.levels` rather
    # than inverted from a fill colour.
    fig, ax = plt.subplots()

    ax.contour(*_field(), levels=[0.2, 0.5, 0.8])

    curves = _series(fig)
    assert len(curves) == 3
    assert [curve[0]["level"] for curve in curves] == [0.2, 0.5, 0.8]
    # Constant down a curve, which is what the grammar says `level` is.
    for curve in curves:
        assert {point["level"] for point in curve} == {curve[0]["level"]}


def test_the_curves_run_where_the_field_reaches_that_value():
    # A gaussian bump centred on the origin: the 0.5 contour is the circle of
    # radius sqrt(-ln 0.5), which every point on that curve sits on.
    fig, ax = plt.subplots()

    ax.contour(*_field(), levels=[0.5])

    curve = _series(fig)[0]
    radius = np.sqrt(-np.log(0.5))
    distances = [np.hypot(point["x"], point["y"]) for point in curve]
    assert max(abs(distance - radius) for distance in distances) < 0.05


def test_two_islands_of_one_level_are_two_curves():
    # Matplotlib draws both in one compound path. Emitted as one series they
    # would be joined by a straight line across the saddle between the peaks,
    # announcing a curve where the field has none.
    fig, ax = plt.subplots()

    ax.contour(*_field(peaks=2), levels=[0.5])

    curves = _series(fig)
    assert len(curves) == 2
    assert [curve[0]["level"] for curve in curves] == [0.5, 0.5]
    # One island each side of the origin, so no curve spans both.
    for curve in curves:
        signs = {np.sign(point["x"]) for point in curve if point["x"] != 0}
        assert len(signs) == 1


def test_a_level_nothing_reaches_contributes_no_curve():
    # Matplotlib still emits a path for it, with no vertices. A series with no
    # points is a row a reader can land on and be told nothing about.
    fig, ax = plt.subplots()

    ax.contour(*_field(), levels=[0.2, 0.5, 2.0])

    assert [curve[0]["level"] for curve in _series(fig)] == [0.2, 0.5]


def test_a_field_that_reaches_no_level_registers_nothing():
    fig, ax = plt.subplots()

    ax.contour(*_field(), levels=[2.0, 3.0])

    assert _layers(fig) == []


def test_each_curve_is_addressed_by_the_level_it_belongs_to():
    # Matplotlib draws the set as one group holding a `<path>` per level, so
    # two islands of one level name the same element: a reader on either sees
    # that level outlined, which is what the drawing can say.
    fig, ax = plt.subplots()

    ax.contour(*_field(peaks=2), levels=[0.2, 0.5])

    selectors = _layers(fig)[0].schema[MaidrKey.SELECTOR]
    assert len(selectors) == len(_series(fig))
    assert selectors[0].endswith("path:nth-of-type(1)")
    assert selectors[-1].endswith("path:nth-of-type(2)")


def test_the_selectors_name_elements_that_are_really_there():
    # A selector matching nothing is the highlight-only blind spot
    # xability/maidr#814 names: everything reads and nothing lights up, which
    # no assertion about the payload alone can see.
    fig, ax = plt.subplots()
    ax.contour(*_field(), levels=[0.2, 0.5, 0.8])
    layer = _layers(fig)[0]

    html = maidr.render(fig).get_html_string()

    gid = layer.schema[MaidrKey.SELECTOR][0].split("'")[1]
    group = html.split(f'<g id="{gid}">', 1)
    assert len(group) == 2, "the contour group is not in the rendered SVG"
    assert group[1].split("</g>", 1)[0].count("<path ") == 3


def test_a_filled_contour_is_declined():
    # `contourf` draws the bands between levels: three levels give two paths,
    # and each outline runs along two different level curves.
    fig, ax = plt.subplots()

    ax.contourf(*_field(), levels=[0.2, 0.5, 0.8])

    assert _layers(fig) == []


def test_two_contour_calls_read_their_own_fields():
    # Each call hands its own set over. "The contour set on this Axes" would
    # describe the first one twice.
    fig, ax = plt.subplots()

    ax.contour(*_field(), levels=[0.2])
    ax.contour(*_field(), levels=[0.8])

    assert [
        _series(fig, index)[0][0]["level"] for index in range(len(_layers(fig)))
    ] == [0.2, 0.8]


def _joint():
    rng = np.random.default_rng(0)
    return pd.DataFrame({"a": rng.normal(size=200), "b": rng.normal(size=200)})


def test_a_bivariate_kdeplot_is_read_as_the_field_it_draws():
    # Seaborn draws the joint density as a contour set, which has no line for
    # the smooth registration to find -- so the chart went out silent. The
    # recursion guard is why the `Axes.contour` patch cannot claim it: `kde`
    # sets the internal context around its own call.
    fig, ax = plt.subplots()

    sns.kdeplot(data=_joint(), x="a", y="b", ax=ax)

    assert [layer.type for layer in _layers(fig)] == [PlotType.CONTOUR]
    assert len({curve[0]["level"] for curve in _series(fig)}) > 1


def test_a_filled_bivariate_kdeplot_is_declined():
    fig, ax = plt.subplots()

    sns.kdeplot(data=_joint(), x="a", y="b", fill=True, ax=ax)

    assert _layers(fig) == []


@pytest.mark.parametrize("fill", [False, True])
def test_a_univariate_kdeplot_still_reads_as_a_curve(fill: bool):
    fig, ax = plt.subplots()

    sns.kdeplot(data=_joint(), x="a", fill=fill, ax=ax)

    assert [layer.type for layer in _layers(fig)] == [PlotType.SMOOTH]


def test_a_kde_jointplot_finally_reads_its_joint_panel():
    # It returned `['smooth', 'smooth']` -- the two marginals, and nothing for
    # the panel the chart is drawn for.
    grid = sns.jointplot(data=_joint(), x="a", y="b", kind="kde")

    assert [layer.type for layer in _layers(grid.figure)] == [
        PlotType.CONTOUR,
        PlotType.SMOOTH,
        PlotType.SMOOTH,
    ]


def test_a_field_drawn_before_a_kdeplot_is_not_claimed_twice():
    # The kdeplot patch asks for the sets *this call* added. Everything on the
    # axes would include one `ax.contour` already registered.
    fig, ax = plt.subplots()

    ax.contour(*_field(), levels=[0.2, 0.5])
    sns.kdeplot(data=_joint(), x="a", y="b", ax=ax)

    assert [layer.type for layer in _layers(fig)] == [
        PlotType.CONTOUR,
        PlotType.CONTOUR,
    ]
    assert [curve[0]["level"] for curve in _series(fig, 0)] == [0.2, 0.5]
