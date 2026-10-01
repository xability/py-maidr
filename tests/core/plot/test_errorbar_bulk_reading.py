"""``ErrorBarPlot`` reads centers of plain numbers a column at a time.

The per-sample loop asked :func:`_is_drawn` and :meth:`_scalar` of every
center, and :meth:`_extract_bounds` of every interval, which built a list and
called ``np.isfinite`` on each endpoint. On a long series that was most of
the extraction. For centers that are plain arrays of floats or integers each
of those answers is known for the whole column at once, so
:meth:`_numeric_samples` reads them in one pass, and :func:`_segment_bounds`
reads the two-point segments matplotlib drew the same way.

Each path is pinned against the per-sample loop it replaced, reached by
switching the bulk reading off, and the work itself is counted rather than
timed.
"""

from __future__ import annotations

import itertools
import json
import uuid
from typing import Any, Callable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes

import maidr
from maidr.core.enum import MaidrKey
from maidr.core.figure_manager import FigureManager
from maidr.core.plot import errorbar
from maidr.core.plot.errorbar import ErrorBarPlot

#: A chart builder, drawing into the axes it is handed.
Draw = Callable[[Axes], Any]


@pytest.fixture(autouse=True)
def _close_figures() -> Any:
    yield
    plt.close("all")


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def _vertical(ax: Axes) -> None:
    rng = _rng()
    ax.errorbar(np.arange(60.0), rng.normal(size=60), yerr=rng.random(60), fmt="o")


def _horizontal(ax: Axes) -> None:
    rng = _rng(1)
    ax.errorbar(rng.normal(size=60), np.arange(60.0), xerr=rng.random(60), fmt="o")


def _both_errors(ax: Axes) -> None:
    rng = _rng(2)
    error = rng.random(40)
    ax.errorbar(np.arange(40.0), rng.normal(size=40), xerr=error, yerr=error)


def _missing_estimates(ax: Axes) -> None:
    y = _rng(3).normal(size=40)
    y[[2, 3]] = np.nan
    y[7] = np.inf
    x = np.arange(40.0)
    x[11] = np.nan
    ax.errorbar(x, y, yerr=0.5)


def _missing_errors(ax: Axes) -> None:
    """A NaN error leaves its sample's segment without its ends."""
    error = _rng(4).random(40)
    error[[5, 6]] = np.nan
    ax.errorbar(np.arange(40.0), _rng(4).normal(size=40), yerr=error)


def _asymmetric(ax: Axes) -> None:
    error = _rng(5).random(30)
    ax.errorbar(np.arange(30.0), _rng(5).normal(size=30), yerr=[error, 2 * error])


def _no_marker(ax: Axes) -> None:
    """``fmt="none"`` draws no data line, so the centers are the call's."""
    ax.errorbar(list(range(30)), list(_rng(6).normal(size=30)), yerr=0.3, fmt="none")


def _limits(ax: Axes) -> None:
    x = np.arange(30.0)
    ax.errorbar(x, _rng(7).normal(size=30), yerr=0.4, uplims=True, lolims=x % 2 == 0)


def _integers(ax: Axes) -> None:
    ax.errorbar(np.arange(30), np.arange(30) * 2, yerr=1)


def _negative_zero(ax: Axes) -> None:
    """Zero-width bars around ``-0.0``, whose sign the bounds must keep."""
    y = _rng(8).normal(size=30)
    y[:10] = -0.0
    error = _rng(8).random(30)
    error[:10] = 0.0
    ax.errorbar(np.arange(30.0), y, yerr=error)


def _no_error(ax: Axes) -> None:
    ax.errorbar(np.arange(20.0), _rng(9).normal(size=20))


def _float_noise(ax: Axes) -> None:
    """``4.2 - 0.4`` is ``3.8000000000000003``; the bounds are cleaned of it."""
    ax.errorbar(np.arange(20.0), [4.2] * 20, yerr=0.4)


def _float32(ax: Axes) -> None:
    ax.errorbar(
        np.arange(20, dtype=np.float32),
        _rng(10).normal(size=20).astype(np.float32),
        yerr=np.float32(0.25),
    )


def _one_point(ax: Axes) -> None:
    ax.errorbar([1.0], [2.0], yerr=[0.5])


def _lists(ax: Axes) -> None:
    """Lists reach the data line as object arrays of Python numbers."""
    ax.errorbar(list(range(25)), [i * 0.5 for i in range(25)], yerr=0.2)


def _listed_arrays(ax: Axes) -> None:
    """``list()`` of an array holds ``np.float64`` and ``np.int64``."""
    ax.errorbar(list(np.arange(25)), list(_rng(11).normal(size=25)), yerr=0.2)


def _beyond_float(ax: Axes) -> None:
    """An integer past the float range raises in the loop, as it always has."""
    ax.errorbar([0, 1], [1.0, 2.0], yerr=0.5)
    ax.containers[-1].lines[0].set_xdata(np.array([0, 10**400], dtype=object))


def _dates(ax: Axes) -> None:
    ax.errorbar(pd.date_range("2024-01-01", periods=20), np.arange(20.0), yerr=1.0)


def _categories(ax: Axes) -> None:
    ax.errorbar([f"c{i}" for i in range(12)], np.arange(12.0), yerr=0.5)


def _masked(ax: Axes) -> None:
    y = np.ma.masked_array(np.arange(20.0), mask=[i % 5 == 0 for i in range(20)])
    ax.errorbar(np.arange(20.0), y, yerr=0.5)


#: Each chart, and whether its centers are read a column at a time.
CHARTS: dict[str, tuple[Draw, bool]] = {
    "vertical": (_vertical, True),
    "horizontal": (_horizontal, True),
    "both-errors": (_both_errors, True),
    "missing-estimates": (_missing_estimates, True),
    "missing-errors": (_missing_errors, True),
    "asymmetric": (_asymmetric, True),
    "no-marker": (_no_marker, True),
    "limits": (_limits, True),
    "integers": (_integers, True),
    "negative-zero": (_negative_zero, True),
    "no-error": (_no_error, True),
    "float-noise": (_float_noise, True),
    "float32": (_float32, True),
    "one-point": (_one_point, True),
    "lists": (_lists, True),
    "listed-arrays": (_listed_arrays, True),
    "beyond-float": (_beyond_float, False),
    "dates": (_dates, False),
    "categories": (_categories, False),
    "masked": (_masked, False),
}


def _render(draw: Draw, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """
    One chart's errorbar data, as JSON, and its whole page, made reproducible.

    Parameters
    ----------
    draw : callable
        Draws the chart.
    monkeypatch : pytest.MonkeyPatch
        Installs the counting ``uuid4`` and pins the SVG's date.

    Returns
    -------
    tuple of str
        The data of every errorbar layer, and ``str(maidr.render(ax))``, or
        the exception each raised.
    """
    counter = itertools.count()
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=next(counter)))
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    fig, ax = plt.subplots()
    draw(ax)
    layers = [
        plot
        for plot in FigureManager.get_maidr(fig).plots
        if isinstance(plot, ErrorBarPlot)
    ]
    data = _outcome(lambda: json.dumps([plot._extract_plot_data() for plot in layers]))
    page = _outcome(lambda: str(maidr.render(ax)))
    plt.close("all")
    return data, page


def _outcome(read: Callable[[], str]) -> str:
    """What ``read`` returns, or the exception it raises, named."""
    try:
        return read()
    except Exception as error:  # noqa: BLE001 -- compared, not swallowed
        return f"{type(error).__name__}: {error}"


@pytest.mark.parametrize("name", list(CHARTS))
def test_a_chart_reads_in_bulk_as_it_does_sample_by_sample(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    draw, bulk_expected = CHARTS[name]
    numeric = ErrorBarPlot._numeric_samples
    ran = []

    def counting(*args: Any) -> list | None:
        read = numeric(*args)
        ran.append(read is not None)
        return read

    monkeypatch.setattr(ErrorBarPlot, "_numeric_samples", staticmethod(counting))
    bulk = _render(draw, monkeypatch)
    assert any(ran) is bulk_expected

    monkeypatch.setattr(
        ErrorBarPlot, "_numeric_samples", staticmethod(lambda *args: None)
    )
    per_sample = _render(draw, monkeypatch)

    assert bulk == per_sample


def test_the_points_are_keyed_by_plain_strings() -> None:
    """A dict keyed by a ``MaidrKey`` member is one the garbage collector
    tracks."""
    fig, ax = plt.subplots()
    _vertical(ax)

    (plot,) = FigureManager.get_maidr(fig).plots
    data = plot._extract_plot_data()

    keys = [key for point in data for key in point]
    assert keys and not any(isinstance(key, MaidrKey) for key in keys)


def test_a_plain_series_is_not_read_sample_by_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    is_drawn = errorbar._is_drawn
    bounds = ErrorBarPlot._extract_bounds

    def counting_drawn(value: Any) -> bool:
        calls.append("drawn")
        return is_drawn(value)

    def counting_bounds(*args: Any) -> Any:
        calls.append("bounds")
        return bounds(*args)

    monkeypatch.setattr(errorbar, "_is_drawn", counting_drawn)
    monkeypatch.setattr(ErrorBarPlot, "_extract_bounds", staticmethod(counting_bounds))
    fig, ax = plt.subplots()
    ax.errorbar(np.arange(1000.0), _rng().normal(size=1000), yerr=0.5)

    (plot,) = FigureManager.get_maidr(fig).plots
    assert len(plot._extract_plot_data()) == 1000
    assert calls == []


#: Segments of every shape ``_extract_bounds`` reads, the awkward values
#: among them.
_ENDS = [0.0, -0.0, 1.5, -2.0, float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("component", [0, 1])
def test_two_point_segments_bound_as_extract_bounds_reads_them(
    component: int,
) -> None:
    segments = [
        np.array([[a, b], [c, d]]) for a, b, c, d in itertools.product(_ENDS, repeat=4)
    ]

    read = errorbar._segment_bounds(segments, len(segments), component)

    assert read is not None
    noise = ErrorBarPlot._without_float_noise
    for index, bounds in enumerate(read):
        expected = ErrorBarPlot._extract_bounds(segments, index, component)
        got = None if bounds is None else (noise(bounds[0]), noise(bounds[1]))
        assert repr(got) == repr(expected), segments[index]


@pytest.mark.parametrize(
    "segments",
    [
        pytest.param(
            [np.array([[0.0, 1.0], [0.0, 2.0]]), np.array([[1.0, 3.0]])],
            id="a-bar-with-one-end",
        ),
        pytest.param([np.array([])], id="an-empty-segment"),
        pytest.param(
            [np.array([[0.0, 1.0], [0.0, 2.0], [0.0, 3.0]])], id="three-points"
        ),
    ],
)
def test_any_other_segment_is_bounded_sample_by_sample(segments: list) -> None:
    assert errorbar._segment_bounds(segments, len(segments), 1) is None


@pytest.mark.parametrize(
    "column",
    [
        pytest.param([1.0, 2.0], id="list"),
        pytest.param(np.array([1.0, "2.0"], dtype=object), id="a-string"),
        pytest.param(np.array([1.0, None], dtype=object), id="none"),
        pytest.param(np.array([1.0, True], dtype=object), id="a-bool"),
        pytest.param(np.array([1.0, np.float32(2.0)], dtype=object), id="float32"),
        pytest.param(np.ma.masked_array([1.0, 2.0], mask=[True, False]), id="masked"),
        pytest.param(np.array([True, False]), id="bools"),
        pytest.param(np.array(["a", "b"]), id="strings"),
        pytest.param(np.array([1.0, "a"], dtype=object), id="objects"),
        pytest.param(np.array(["2024-01-01"], dtype="datetime64[D]"), id="dates"),
        pytest.param(np.arange(4.0).reshape(2, 2), id="two-dimensional"),
        pytest.param(
            np.array([1.0], dtype=np.longdouble),
            id="long-double",
            marks=pytest.mark.skipif(
                np.dtype(np.longdouble).itemsize <= 8,
                reason="long double is float64 here, and read as one",
            ),
        ),
    ],
)
def test_any_other_column_keeps_the_per_sample_loop(column: Any) -> None:
    centers = np.arange(float(np.size(column)))

    read = ErrorBarPlot._numeric_samples(centers, column, [], 1)

    assert read is None
