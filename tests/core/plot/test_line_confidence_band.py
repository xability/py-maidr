"""
A line carries the interval shaded around it (#562).

`sns.lineplot` aggregates repeated x values and draws a 95% confidence band
**by default**; matplotlib's own documentation writes the same chart as
``plot`` plus ``fill_between``. Either way the line was announced alone, so a
reader was told the trend and never that the chart shows any uncertainty at
all -- while a `regplot` on the same page did carry its band. The gap
xability/r-maidr#135 closed for `geom_smooth(se = TRUE)` and #451 for a
regression.

``SmoothPoint``'s `yMin`/`yMax` is the shape, and the reading is
`SmoothPlot`'s, lifted into :mod:`maidr.util.confidence_band` so both use one.

**Bracketing alone is not enough, and this is the case that shows why.**
`ax.fill_between(x, y)` shades from the baseline up to the series, so a line
drawn on top of its own area sits exactly on that region's upper edge and
passes every containment test. Read as a band it announces "2.0, between 0 and
2.0" -- an interval the chart does not state and whose width is the value over
again. A band lies *around* a series; an area merely touches it.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn as sns

from maidr.core.figure_manager import FigureManager
from maidr.util.confidence_band import DRAWN_ALONG_Y, shaded_along_y

X = np.linspace(0, 10, 20)
Y = np.sin(X) + 2.0


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _series(fig) -> list:
    """Every line layer's series, in registration order."""
    return [
        series
        for plot in FigureManager.get_maidr(fig).plots
        if plot.type.value == "line"
        for series in plot.schema["data"]
    ]


def _band(point) -> tuple | None:
    """A point's interval, rounded, or None where it carries none."""
    if "yMin" not in point:
        return None
    return round(point["yMin"], 3), round(point["yMax"], 3)


def test_a_hand_drawn_band_reaches_the_line_s_points():
    fig, ax = plt.subplots()
    ax.plot(X, Y)
    ax.fill_between(X, Y - 0.3, Y + 0.3)

    first = _series(fig)[0][0]
    assert _band(first) == (round(Y[0] - 0.3, 3), round(Y[0] + 0.3, 3))


def test_every_point_of_the_line_carries_it():
    # Not only the first: the band is interpolated at each emitted position,
    # because a line's samples need not be among the region's own vertices.
    fig, ax = plt.subplots()
    ax.plot(X, Y)
    ax.fill_between(X, Y - 0.3, Y + 0.3)

    assert all(_band(point) is not None for point in _series(fig)[0])


def test_a_seaborn_confidence_band_reaches_them_too():
    # The band seaborn draws on its own, which is the common way to meet one.
    rng = np.random.default_rng(0)
    frame = pd.DataFrame(
        {
            "x": np.tile(X, 4),
            "y": np.concatenate([Y + rng.normal(scale=0.3, size=X.size) for _ in range(4)]),
        }
    )
    fig, ax = plt.subplots()
    sns.lineplot(data=frame, x="x", y="y", ax=ax)

    first = _series(fig)[0][0]
    band = _band(first)
    assert band is not None
    assert band[0] < first["y"] < band[1]


def test_a_line_with_nothing_shaded_around_it_carries_none():
    fig, ax = plt.subplots()
    ax.plot(X, Y)

    assert _band(_series(fig)[0][0]) is None


def test_an_area_a_line_sits_on_is_not_an_interval():
    # The false positive bracketing alone would accept. The line lies exactly
    # on the area's upper edge, so "between 0 and y" would be announced at
    # every point -- an interval the chart does not state.
    fig, ax = plt.subplots()
    ax.fill_between(X, Y)
    ax.plot(X, Y)

    assert _band(_series(fig)[0][0]) is None


def test_an_area_from_an_explicit_zero_floor_is_not_one_either():
    # `fill_between(x, y, 0)` is the same chart written out, and reaches the
    # same guard.
    fig, ax = plt.subplots()
    ax.fill_between(X, Y, 0)
    ax.plot(X, Y)

    assert _band(_series(fig)[0][0]) is None


def test_an_area_under_a_series_that_changes_sign_is_not_one_either():
    # The case a whole-series test misses (#714). An area under a signed
    # series switches edges where it crosses the baseline: the line sits on
    # the region's *upper* edge where y > 0 and on its *lower* edge where
    # y < 0, so it is on neither edge throughout and was read as a band --
    # "0.05, between 0 and 0.05" at every point. The test is per position: an
    # area is on one edge or the other everywhere, a band is off both.
    signed = np.sin(X)
    fig, ax = plt.subplots()
    ax.plot(X, signed)
    ax.fill_between(X, 0, signed)

    assert [_band(point) for point in _series(fig)[0]] == [None] * X.size


def test_a_band_that_touches_its_line_at_one_endpoint_is_still_attached():
    # The other side of the per-position rule. A real band can meet its line
    # at an endpoint -- a regression's does, where the fit is pinned -- and
    # isolated contact must not read as an area.
    lower, upper = Y - 0.3, Y + 0.3
    lower[0] = upper[0] = Y[0]
    fig, ax = plt.subplots()
    ax.plot(X, Y)
    ax.fill_between(X, lower, upper)

    points = _series(fig)[0]
    assert _band(points[0]) == (round(Y[0], 3), round(Y[0], 3))
    assert _band(points[1]) == (round(Y[1] - 0.3, 3), round(Y[1] + 0.3, 3))


def test_the_edges_are_the_lowest_and_highest_vertex_at_each_x():
    # Read straight off a ring that repeats x values -- as matplotlib's do,
    # running out along one edge and back along the other -- with a
    # non-finite vertex that has to be left out rather than poison the
    # column it sits in.
    from matplotlib.collections import PolyCollection

    from maidr.util.confidence_band import edges_of

    ring = [
        (0.0, 1.0),
        (1.0, 2.0),
        (2.0, 1.0),
        (2.0, 3.0),
        (1.0, 4.0),
        (0.0, 3.0),
        (1.0, np.nan),
        (0.0, 1.0),
    ]
    region = PolyCollection([ring])

    lower, upper = edges_of(
        region, np.array([0.0, 1.0, 2.0]), np.array([2.0, 3.0, 2.0])
    )
    assert lower.tolist() == [1.0, 2.0, 1.0]
    assert upper.tolist() == [3.0, 4.0, 3.0]


def test_a_where_region_with_several_paths_is_read_across_all_of_them():
    # `fill_between(..., where=...)` draws one polygon per run, so the band
    # is several paths and every one of them has to be read.
    from maidr.util.confidence_band import edges_of

    line = X.copy()
    shown = (X < 4) | (X > 6)
    fig, ax = plt.subplots()
    ax.plot(X, line)
    region = ax.fill_between(X, line - 0.3, line + 0.3, where=shown)
    assert len(region.get_paths()) == 2

    lower, upper = edges_of(region, X[shown], line[shown])
    assert np.allclose(lower, line[shown] - 0.3)
    assert np.allclose(upper, line[shown] + 0.3)


def test_each_line_gets_its_own_band():
    # Two lines and two bands. The lower band is wide enough to bracket only
    # its own line, but a region is claimed by one series either way -- so
    # this fails if the first line took both.
    fig, ax = plt.subplots()
    ax.plot(X, Y)
    ax.fill_between(X, Y - 0.2, Y + 0.2)
    ax.plot(X, Y + 3)
    ax.fill_between(X, Y + 2.8, Y + 3.2)

    first, second = _series(fig)
    assert _band(first[0]) == (round(Y[0] - 0.2, 3), round(Y[0] + 0.2, 3))
    assert _band(second[0]) == (round(Y[0] + 2.8, 3), round(Y[0] + 3.2, 3))


def test_a_regression_still_carries_its_own_band():
    # The reading this shares with `SmoothPlot`, asserted from the other side
    # so lifting it cannot quietly change what a `regplot` says.
    rng = np.random.default_rng(0)
    fig, ax = plt.subplots()
    sns.regplot(x=X, y=Y + rng.normal(scale=0.2, size=X.size), ax=ax)

    smooth = next(
        plot for plot in FigureManager.get_maidr(fig).plots
        if plot.type.value == "smooth"
    )
    point = smooth.schema["data"][0][0]
    assert point["yMin"] < point["y"] < point["yMax"]


def test_the_figure_still_renders():
    import maidr

    fig, ax = plt.subplots()
    ax.plot(X, Y)
    ax.fill_between(X, Y - 0.3, Y + 0.3)

    assert len(maidr.render(fig)._repr_html_()) > 0


def test_a_shaded_region_that_does_not_enclose_the_line_is_not_its_band():
    # What the containment test is for. A chart may shade something that has
    # nothing to do with this line -- seaborn draws a violin body with
    # `fill_betweenx`, so a shaded region is not identifiable by type. Here it
    # sits well below the line, and reading it would announce an interval the
    # line is not even inside.
    fig, ax = plt.subplots()
    ax.plot(X, Y)
    ax.fill_between(X, Y - 5.0, Y - 4.0)

    assert _band(_series(fig)[0][0]) is None


def test_one_band_around_two_lines_belongs_to_one_of_them():
    # Two lines a hair apart and a single band, wide enough to enclose both.
    # It was drawn for the first, and the second has no interval -- so
    # answering with the same region twice would tell a reader about an
    # uncertainty the chart never drew for that series.
    fig, ax = plt.subplots()
    ax.plot(X, Y)
    ax.fill_between(X, Y - 1.0, Y + 1.0)
    ax.plot(X, Y + 0.1)

    first, second = _series(fig)
    assert _band(first[0]) == (round(Y[0] - 1.0, 3), round(Y[0] + 1.0, 3))
    assert _band(second[0]) is None


# --- A band shaded the other way about (#601) ---------------------------------
#
# `edges_of` reads the lowest and highest vertex **at each x**, which is a
# reading of a vertical interval. A `fill_betweenx` band has none to read, and
# bracketing does not reject it: a horizontal band around a horizontal line
# surrounds that line vertically too, because it surrounds it.
#
# Measured before the fix, on the chart below:
#
#     {'x': 1.0, 'y': 0.0, 'yMin': 0.0, 'yMax': 1.5}
#     {'x': 2.0, 'y': 1.0, 'yMin': 0.5, 'yMax': 3.0}
#     {'x': 3.0, 'y': 2.0, 'yMin': 1.5, 'yMax': 3.5}
#     {'x': 2.0, 'y': 3.0, 'yMin': 0.5, 'yMax': 3.0}
#     {'x': 4.0, 'y': 4.0, 'yMin': 3.0, 'yMax': 4.0}
#
# against a true interval, on x, of (0.5,1.5) (1.5,2.5) (2.5,3.5) (1.5,2.5)
# (3.5,4.5). The polygon's *vertical extent* at each x -- an artefact of the
# band being sloped -- announced on the axis that carries the positions, which
# this chart states no uncertainty about at all. The last point's `yMax` is its
# own `y`.

POS = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
VAL = np.array([1.0, 2.0, 3.0, 2.0, 4.0])


def _sideways(ax) -> None:
    """A horizontal line chart with a horizontal interval around it."""
    ax.plot(VAL, POS)
    ax.fill_betweenx(POS, VAL - 0.5, VAL + 0.5, alpha=0.3)


def test_a_horizontal_band_is_not_read_as_a_vertical_interval():
    fig, ax = plt.subplots()
    _sideways(ax)

    assert [_band(point) for point in _series(fig)[0]] == [None] * len(POS)


def test_the_line_itself_is_unaffected():
    """Declining the band costs the chart nothing else."""
    fig, ax = plt.subplots()
    _sideways(ax)

    points = _series(fig)[0]
    assert [point["x"] for point in points] == list(VAL)
    assert [point["y"] for point in points] == list(POS)


def test_the_patch_records_which_way_every_region_it_draws_was_shaded():
    """The tag is what decides, so its two values are asserted directly.

    Read rather than inferred, because counting distinct coordinates ties on
    a small frame -- measured, this very pair of calls gives ``uniqX == uniqY
    == 5`` for both spellings -- and a tie would have to be declined, which
    would drop bands that read correctly today.
    """
    fig, ax = plt.subplots()
    upright = ax.fill_between(POS, VAL - 0.5, VAL + 0.5)
    sideways = ax.fill_betweenx(POS, VAL - 0.5, VAL + 0.5)

    assert getattr(upright, DRAWN_ALONG_Y) is False
    assert getattr(sideways, DRAWN_ALONG_Y) is True
    assert shaded_along_y(upright) is False
    assert shaded_along_y(sideways) is True


def test_a_region_this_patch_did_not_draw_reads_as_it_always_did():
    """An absent tag says only that, and must not mean "horizontal".

    Nothing in the suite draws such a region -- both spellings go through the
    patch -- so the fallback is asserted directly. Getting it the other way
    round would silently drop the band from every chart whose region some
    other library shaded.
    """
    from matplotlib.collections import PolyCollection

    assert shaded_along_y(PolyCollection([])) is False


def test_a_band_drawn_inside_another_patch_is_tagged_too():
    """`stackplot` draws its bands through `fill_between` under the internal
    context, and a region that registers no layer of its own is still read as
    some line's band later. So the tag cannot be set only on the path that
    registers one."""
    fig, ax = plt.subplots()
    ax.stackplot(POS, VAL, VAL + 1.0)

    drawn = [c for c in ax.collections if hasattr(c, DRAWN_ALONG_Y)]
    assert len(drawn) == 2
    assert all(getattr(c, DRAWN_ALONG_Y) is False for c in drawn)
