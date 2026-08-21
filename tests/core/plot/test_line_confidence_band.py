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
