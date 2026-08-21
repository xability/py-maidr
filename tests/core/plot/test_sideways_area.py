"""
A sideways band was announced against the wrong axis titles (#566).

``fill_betweenx(y, x1)`` fills between the vertical positions ``y`` and the
horizontal curve ``x1``, so its positions belong to the y axis and its
magnitudes to the x axis -- the mirror of every other chart ``AreaPlot``
reads. Emitted unchanged, the two spellings produced **byte-identical**
payloads for charts that are transposes of each other::

    ax.set_xlabel("horizontal"); ax.set_ylabel("vertical")
    ax.fill_between(X, V)    # axes x=horizontal y=vertical, points (1,2)...
    ax.fill_betweenx(X, V)   # axes x=horizontal y=vertical, points (1,2)...

so a reader was told "horizontal 1, vertical 2" where the chart draws the
point at vertical 1, horizontal 2.

The **titles** move rather than the data, and this file pins both halves of
that, because each is wrong on its own:

- moving the data would put the positions in ``y``, which the core sonifies,
  pitching ``[1, 2, 3, 4]`` -- a rising ramp on every sideways band ever
  drawn, whatever the data says;
- emitting ``orientation`` would be a promise the core does not keep:
  ``src/util/orientation.ts`` marks ``AREA`` as not oriented on purpose.

The same exchange, for the same reason, is what the core's Vega-Lite adapter
does to a horizontal waterfall.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pytest

from maidr.core.enum import MaidrKey
from maidr.core.figure_manager import FigureManager
from maidr.exception import UnsupportedPlotError

POSITIONS = np.array([1.0, 2.0, 3.0, 4.0])
MAGNITUDES = np.array([2.0, 4.0, 3.0, 5.0])


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _titled_axes():
    fig, ax = plt.subplots()
    ax.set_xlabel("horizontal")
    ax.set_ylabel("vertical")
    return fig, ax


def _schema(fig) -> dict:
    plots = FigureManager.get_maidr(fig).plots
    assert len(plots) == 1
    return plots[0].schema


def _labels(schema) -> tuple:
    axes = schema["axes"]
    return axes[MaidrKey.X.value]["label"], axes[MaidrKey.Y.value]["label"]


def _points(schema) -> list:
    return [
        (point[MaidrKey.X], point[MaidrKey.Y]) for point in schema["data"][0]
    ]


def test_a_sideways_band_names_each_axis_it_was_drawn_against():
    fig, ax = _titled_axes()
    ax.fill_betweenx(POSITIONS, MAGNITUDES)

    # The positions run down the page and the magnitudes out along x, so the
    # trace's `x` field holds vertical numbers and its `y` field horizontal
    # ones -- which is what the titles now say.
    assert _labels(_schema(fig)) == ("vertical", "horizontal")


def test_an_upright_band_is_unchanged():
    fig, ax = _titled_axes()
    ax.fill_between(POSITIONS, MAGNITUDES)

    assert _labels(_schema(fig)) == ("horizontal", "vertical")


def test_a_stackplot_is_unchanged():
    # `stackplot` reaches the same class and is never sideways. Asserted
    # because the swap is a flag on the layer rather than on the call, and a
    # flag defaulting the wrong way would transpose every area chart.
    fig, ax = _titled_axes()
    ax.stackplot(POSITIONS, MAGNITUDES)

    assert _labels(_schema(fig)) == ("horizontal", "vertical")


def test_the_magnitudes_stay_where_the_trace_pitches_them():
    # The half that must NOT move. The core sonifies an area trace's `y`; put
    # the positions there and every sideways band plays a rising ramp,
    # whatever its data. Asserted as the same points the upright spelling
    # emits, since that is exactly the field layout being preserved.
    fig, ax = _titled_axes()
    ax.fill_betweenx(POSITIONS, MAGNITUDES)

    assert _points(_schema(fig)) == [(1.0, 2.0), (2.0, 4.0), (3.0, 3.0), (4.0, 5.0)]


def test_the_two_spellings_differ_in_their_titles_and_nowhere_else():
    # What the defect was: identical payloads for transposed charts. The two
    # are compared directly rather than each against a literal, so they
    # cannot quietly converge again.
    upright, upright_ax = _titled_axes()
    upright_ax.fill_between(POSITIONS, MAGNITUDES)
    sideways, sideways_ax = _titled_axes()
    sideways_ax.fill_betweenx(POSITIONS, MAGNITUDES)

    one, other = _schema(upright), _schema(sideways)

    assert _points(one) == _points(other)
    assert _labels(one) != _labels(other)
    assert _labels(one) == tuple(reversed(_labels(other)))


def test_a_number_format_travels_with_the_title_it_describes():
    # A formatter set on the x axis describes the horizontal numbers, which
    # for a sideways band are the ones in `y`. The swap therefore has to
    # happen after the format is merged into each `AxisConfig`, not while the
    # labels are being read.
    fig, ax = _titled_axes()
    ax.xaxis.set_major_formatter(mticker.StrMethodFormatter("${x:,.0f}"))
    ax.fill_betweenx(POSITIONS, MAGNITUDES)

    axes = _schema(fig)["axes"]
    assert axes[MaidrKey.Y.value]["format"]["type"] == "currency"
    assert "format" not in axes[MaidrKey.X.value]


def test_a_number_format_stays_put_for_an_upright_band():
    fig, ax = _titled_axes()
    ax.xaxis.set_major_formatter(mticker.StrMethodFormatter("${x:,.0f}"))
    ax.fill_between(POSITIONS, MAGNITUDES)

    axes = _schema(fig)["axes"]
    assert axes[MaidrKey.X.value]["format"]["type"] == "currency"
    assert "format" not in axes[MaidrKey.Y.value]


def test_no_orientation_is_claimed():
    # `orientation` is the field that says a chart is drawn sideways, and the
    # core marks AREA as not oriented on purpose -- it navigates along the
    # series either way. Emitting one would be a promise nothing keeps, the
    # shape xability/maidr#949 named.
    fig, ax = _titled_axes()
    ax.fill_betweenx(POSITIONS, MAGNITUDES)

    # One assertion, not two: `MaidrKey` subclasses `str`, so the enum member
    # and the bare spelling are the same key.
    assert MaidrKey.ORIENTATION not in _schema(fig)


@pytest.mark.parametrize("sideways", [False, True])
def test_a_band_between_two_curves_still_registers_nothing(sideways):
    # Symmetric, and deliberately so (#339): the band's content is the gap
    # rather than either edge. Pinned here because the sweep that found this
    # issue first mis-read the two-curve form as an asymmetry between the two
    # spellings, and it is not one.
    fig, ax = _titled_axes()
    if sideways:
        ax.fill_betweenx(POSITIONS, MAGNITUDES - 1, MAGNITUDES + 1)
    else:
        ax.fill_between(POSITIONS, MAGNITUDES - 1, MAGNITUDES + 1)

    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)
