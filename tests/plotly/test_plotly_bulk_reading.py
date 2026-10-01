"""Plotly columns are read in bulk where a value-by-value pass changes nothing.

Four costs of a large Plotly chart were all per value or per trace, for an
answer known before the loop started:

* every scatter, line and multiline point called ``_to_native`` twice,
  although a decoded column is already Python floats, which it returns as
  they are -- 200k calls for a 100k-point scatter;
* a heatmap called its own ``_to_native`` once per cell, a million times at
  1000 x 1000, where a row of floats only needs copying;
* a noisy contour field measured each of its tens of thousands of curves
  with its own NumPy reductions;
* ``draws_marks`` decoded every scatter trace's arrays three times over,
  once per question asked of the same trace.

Every point is also keyed by the plain strings ``MaidrKey`` members stand
for, which serialize the same: a dict keyed by an enum member is one the
garbage collector has to track, and a 100k-point chart made 100k of them.

Each change is pinned against the reading it replaced -- kept here as the
reference, or reached by switching the bulk path off -- and the work itself
is counted rather than timed.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import uuid
from typing import Any, Callable

import numpy as np
import pytest

go = pytest.importorskip("plotly.graph_objects")

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.plotly import contour as plotly_contour  # noqa: E402
from maidr.plotly import plotly_maidr  # noqa: E402
from maidr.plotly.heatmap import PlotlyHeatmapPlot  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402
from maidr.plotly.plotly_plot import PlotlyPlot  # noqa: E402

#: A figure builder.
Build = Callable[[], Any]


def _schema(figure: Any, monkeypatch: pytest.MonkeyPatch) -> str:
    """
    A figure's whole schema, serialized, with ids minted in order.

    Parameters
    ----------
    figure : plotly.graph_objects.Figure
        The figure to read.
    monkeypatch : pytest.MonkeyPatch
        Installs the counting ``uuid4``.

    Returns
    -------
    str
        The schema as JSON.
    """
    counter = itertools.count()
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=next(counter)))
    return json.dumps(PlotlyMaidr(figure)._flatten_maidr())


def _per_value(self: PlotlyPlot, values: list) -> list:
    """``_natives`` as the loop it replaced: one ``_to_native`` per value."""
    return [self._to_native(value) for value in values]


class _Plain(PlotlyPlot):
    """A concrete layer that inherits ``_to_native`` as it is."""

    def _extract_plot_data(self) -> list:
        return []


# --- the conversion itself ----------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        pytest.param([1.5, 2.0, float("nan"), float("inf")], id="floats"),
        pytest.param([1, 2, 3], id="ints"),
        pytest.param([1, 2.5, None, True, "a"], id="natives"),
        pytest.param([np.float64(1.5), 2.0], id="numpy-scalar"),
        pytest.param([np.datetime64("2024-01-02"), None], id="datetime64"),
        pytest.param([dt.date(2024, 1, 2), dt.datetime(2024, 1, 2, 3)], id="dates"),
        pytest.param([np.str_("a"), "b"], id="numpy-string"),
        pytest.param([], id="empty"),
    ],
)
def test_natives_are_what_converting_each_value_gives(values: list) -> None:
    plot = _Plain.__new__(_Plain)

    got = plot._natives(values)

    assert repr(got) == repr(_per_value(plot, values))
    assert [type(value) for value in got] == [
        type(value) for value in _per_value(plot, values)
    ]


def test_a_subclass_with_its_own_conversion_converts_every_value() -> None:
    """A heatmap's ``_to_native`` turns an ``int`` into a ``float``."""
    plot = PlotlyHeatmapPlot.__new__(PlotlyHeatmapPlot)

    assert plot._natives([1, 2]) == [1.0, 2.0]
    assert [type(value) for value in plot._natives([1, 2])] == [float, float]


# --- scatter, line and multiline ------------------------------------------------


def _walk(n: int, seed: int = 0) -> np.ndarray:
    """A reproducible random walk of ``n`` floats."""
    return np.random.default_rng(seed).normal(size=n).cumsum()


def _gappy() -> Any:
    y = _walk(80)
    y[[3, 4]] = np.nan
    y[9] = np.inf
    return go.Figure(go.Scatter(x=np.arange(80.0), y=y, mode="markers"))


def _multiline() -> Any:
    figure = go.Figure()
    for index in range(4):
        figure.add_trace(
            go.Scatter(
                x=np.arange(50.0), y=_walk(50, index), mode="lines", name=f"s{index}"
            )
        )
    figure.add_trace(go.Scatter(x=[], y=[], mode="lines", name="empty"))
    return figure


FIGURES: dict[str, Build] = {
    "floats": lambda: go.Figure(
        go.Scatter(x=np.arange(60.0), y=_walk(60), mode="markers")
    ),
    "nan-inf": _gappy,
    "none": lambda: go.Figure(
        go.Scatter(x=[1, 2, 3, 4], y=[1.0, None, 3.0, 4.0], mode="markers")
    ),
    "ints": lambda: go.Figure(go.Scatter(x=list(range(20)), y=list(range(20)))),
    "mixed": lambda: go.Figure(
        go.Scatter(x=[1, 2.5, 3], y=[True, 2, 3.5], mode="markers")
    ),
    "strings": lambda: go.Figure(
        go.Scatter(x=["a", "b", "c"], y=[1.0, 3.0, 2.0], mode="markers")
    ),
    "datetime64": lambda: go.Figure(
        go.Scatter(
            x=np.arange("2024-01-01", "2024-01-11", dtype="datetime64[D]"),
            y=_walk(10),
            mode="lines",
        )
    ),
    "dates": lambda: go.Figure(
        go.Scatter(x=[dt.date(2024, 1, day) for day in range(1, 8)], y=_walk(7))
    ),
    "y-only": lambda: go.Figure(go.Scatter(y=_walk(30), mode="markers")),
    "named-line": lambda: go.Figure(
        go.Scatter(x=np.arange(40.0), y=_walk(40), mode="lines", name="walk")
    ),
    "multiline": _multiline,
    "scattergl": lambda: go.Figure(
        go.Scattergl(x=np.arange(40.0), y=_walk(40), mode="markers")
    ),
}


@pytest.mark.parametrize("name", list(FIGURES))
def test_a_trace_reads_in_bulk_as_it_does_value_by_value(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    bulk = _schema(FIGURES[name](), monkeypatch)

    monkeypatch.setattr(PlotlyPlot, "_natives", _per_value)
    per_value = _schema(FIGURES[name](), monkeypatch)

    assert bulk == per_value


def test_a_float_column_is_not_converted_value_by_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    convert = PlotlyPlot._to_native

    def counting(value: Any) -> Any:
        calls.append(1)
        return convert(value)

    monkeypatch.setattr(PlotlyPlot, "_to_native", staticmethod(counting))
    figure = go.Figure(
        go.Scatter(x=np.arange(1000.0), y=_walk(1000), mode="lines", name="a")
    )

    PlotlyMaidr(figure)._flatten_maidr()

    assert len(calls) < 50, f"{len(calls)} conversions for 2000 float values"


def test_each_scatter_trace_is_asked_whether_it_draws_marks_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each ask decodes both of a trace's arrays."""
    calls = []
    draws = plotly_maidr.draws_marks

    def counting(trace: Any) -> bool:
        calls.append(1)
        return draws(trace)

    monkeypatch.setattr(plotly_maidr, "draws_marks", counting)
    figure = go.Figure()
    for index in range(5):
        figure.add_trace(
            go.Scatter(x=np.arange(20.0), y=_walk(20, index), mode="markers")
        )

    PlotlyMaidr(figure)._flatten_maidr()

    assert len(calls) == 5


# --- heatmap ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "row",
    [
        pytest.param([0.5, float("nan"), -0.0, 2.0], id="floats"),
        pytest.param([1, 2, 3], id="ints"),
        pytest.param([1, 2.5, 3], id="ints-and-floats"),
        pytest.param([1.0, None, 2.0], id="none"),
        pytest.param([True, 1.0], id="bool"),
        pytest.param(["1", "2.5"], id="strings"),
        pytest.param(np.array([1.5, 2.5]), id="numpy-row"),
        pytest.param([], id="empty"),
    ],
)
def test_a_heatmap_row_reads_as_it_does_cell_by_cell(row: Any) -> None:
    plot = PlotlyHeatmapPlot.__new__(PlotlyHeatmapPlot)

    got = plot._native_row(row)
    want = [PlotlyHeatmapPlot._to_native(value) for value in row]

    assert repr(got) == repr(want)
    assert [type(value) for value in got] == [type(value) for value in want]


# --- contour ------------------------------------------------------------------------


def _curves_one_by_one(curves: list, cell: float, level: Any) -> list[list[dict]]:
    """The reading ``_kept_curves`` replaced: each curve on its own."""
    return [
        [
            {MaidrKey.X: x, MaidrKey.Y: y, MaidrKey.LEVEL: level}
            for x, y in curve.tolist()
        ]
        for curve in curves
        if plotly_contour._has_extent(curve, cell)
    ]


def _random_curves(seed: int) -> list:
    """Curves of assorted lengths, some grazing a single point."""
    rng = np.random.default_rng(seed)
    curves = []
    for _ in range(int(rng.integers(1, 30))):
        length = int(rng.integers(1, 12))
        if rng.random() < 0.3:
            point = rng.normal(size=2)
            # A grazed point: copies of one vertex, a few ulps apart.
            curve = np.repeat(point[None, :], length, axis=0)
            curve += rng.normal(scale=1e-15, size=curve.shape)
        else:
            curve = rng.normal(size=(length, 2)).cumsum(axis=0)
        curves.append(curve)
    return curves


@pytest.mark.parametrize("seed", range(40))
def test_a_level_reads_in_one_pass_as_it_does_curve_by_curve(seed: int) -> None:
    curves = _random_curves(seed)
    cell = 0.5

    got = plotly_contour._kept_curves(curves, cell, 0.25)

    assert json.dumps(got) == json.dumps(_curves_one_by_one(curves, cell, 0.25))


@pytest.mark.parametrize(
    "curves",
    [
        pytest.param([], id="no-curves"),
        pytest.param(
            [np.zeros((0, 2)), np.array([[0.0, 0.0], [1.0, 1.0]])], id="an-empty-curve"
        ),
        pytest.param([np.array([[np.nan, 0.0], [1.0, 1.0]])], id="nan-x"),
        pytest.param([np.array([[0.0, np.nan], [1.0, 1.0]])], id="nan-y"),
        pytest.param([np.array([[2.0, 3.0]] * 5)], id="one-point"),
    ],
)
def test_the_edge_cases_read_as_they_did(curves: list) -> None:
    got = plotly_contour._kept_curves(curves, 0.5, 1.0)

    assert json.dumps(got) == json.dumps(_curves_one_by_one(curves, 0.5, 1.0))
