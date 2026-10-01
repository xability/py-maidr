"""Bokeh columns of plain numbers are read a column at a time.

A line, a step, a point cloud or a ``varea``/``harea`` band on two numeric
axes called :func:`is_missing`, :func:`to_native` and :func:`to_coordinate`
on every sample -- a band :func:`_extent` as well -- and a point cloud
sharing its source with a line asked :func:`mark_anchor` for every point.
For a column of plain numbers each of those answers is known for the whole
column at once, so :func:`_plain_numbers` reads it in one pass.

Each path is pinned against the per-value reading it replaced, reached by
switching the bulk reading off, and the work itself is counted rather than
timed.
"""

from __future__ import annotations

import itertools
import json
import re
import uuid
from typing import Any, Callable

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("bokeh")

from bokeh.models import (  # noqa: E402
    BooleanFilter,
    CDSView,
    ColumnDataSource,
    IndexFilter,
)
from bokeh.plotting import figure  # noqa: E402

from maidr.bokeh import bokeh_maidr, layers  # noqa: E402
from maidr.bokeh.bokeh_maidr import BokehMaidr  # noqa: E402
from maidr.bokeh.data import is_missing, to_coordinate, to_native  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402

#: A figure builder.
Build = Callable[[], Any]

#: A Bokeh model id, ``"p1234"``, from a counter every new model advances.
_MODEL_ID = re.compile(r'"p[0-9]+"')


def _walk(n: int, seed: int = 0) -> np.ndarray:
    """A reproducible random walk of ``n`` floats."""
    return np.random.default_rng(seed).normal(size=n).cumsum()


def _read(build: Build, monkeypatch: pytest.MonkeyPatch) -> str:
    """
    A figure's schema and highlights, serialized, with ids minted in order.

    Parameters
    ----------
    build : callable
        Makes the figure; called afresh for every reading.
    monkeypatch : pytest.MonkeyPatch
        Installs the counting ``uuid4``.

    Returns
    -------
    str
        The schema and every layer's highlight, as JSON, with Bokeh's model
        ids numbered by first appearance: each reading builds new models.
    """
    counter = itertools.count()
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=next(counter)))
    maidr_ = BokehMaidr(build())
    highlights = [layer.highlight for layer in maidr_.layers]
    read = json.dumps([maidr_._flatten_maidr(), highlights])
    ids: dict[str, int] = {}
    return _MODEL_ID.sub(lambda m: f'"<{ids.setdefault(m.group(0), len(ids))}>"', read)


# --- one column -------------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        pytest.param([1.5, -0.0, 0.0, float("nan"), float("inf")], id="floats"),
        pytest.param([float("-inf"), 2.0], id="negative-infinity"),
        pytest.param(list(np.array([1.5, np.nan, -np.inf, -0.0])), id="float64"),
        pytest.param([1, -2, 3], id="ints"),
        pytest.param(list(np.arange(5)), id="int64"),
        pytest.param([2**62, -(2**62)], id="large-ints"),
    ],
)
def test_a_plain_column_reads_as_it_does_value_by_value(values: list) -> None:
    read = layers._plain_numbers(values)

    assert read is not None
    gaps, announced = read
    assert gaps == [is_missing(value) for value in values]
    assert repr(announced) == repr([to_native(value) for value in values])
    assert [type(value) for value in announced] == [
        type(to_native(value)) for value in values
    ]
    # A plain number is placed where it is announced.
    assert repr(announced) == repr([to_coordinate(value) for value in values])


@pytest.mark.parametrize(
    "values",
    [
        pytest.param([1, 2.5], id="ints-and-floats"),
        pytest.param([1.0, None], id="none"),
        pytest.param([True, False], id="bools"),
        pytest.param(list(np.arange(3, dtype=np.float32)), id="float32"),
        pytest.param(list(np.arange(3, dtype=np.int32)), id="int32"),
        pytest.param([np.float64(1.0), 2.0], id="float64-and-float"),
        pytest.param(["a", "b"], id="strings"),
        pytest.param(list(np.array(["2024-01-01"], dtype="datetime64[D]")), id="dates"),
        pytest.param([2**63, 1], id="int-beyond-int64"),
        pytest.param([10**400, 1], id="int-beyond-float"),
        pytest.param([], id="empty"),
    ],
)
def test_any_other_column_keeps_the_per_value_reading(values: list) -> None:
    assert layers._plain_numbers(values) is None


class _PassesForFloat(type):
    """A metaclass whose classes compare and hash as ``float`` does."""

    def __eq__(cls, other: object) -> bool:
        return other is float or cls is other

    def __hash__(cls) -> int:
        return hash(float)


class _Scaled(float, metaclass=_PassesForFloat):
    """A float that announces itself a hundred times larger."""

    def item(self) -> float:
        return float(self) * 100


class _Unhashable(type):
    """A metaclass whose classes cannot be hashed."""

    def __eq__(cls, other: object) -> bool:
        return cls is other

    __hash__ = None  # type: ignore[assignment]


class _Opaque(float, metaclass=_Unhashable):
    """A float whose class cannot be put in a set."""


@pytest.mark.parametrize(
    "values",
    [
        pytest.param([_Scaled(1.0), _Scaled(2.0)], id="lookalike"),
        pytest.param([_Opaque(1.0), _Opaque(2.0)], id="unhashable-type"),
        pytest.param([1.0, _Scaled(2.0)], id="lookalike-after-a-float"),
    ],
)
def test_a_column_is_plain_only_by_the_identity_of_its_types(values: list) -> None:
    """Never by hashing a type, or by asking it whether it equals ``float``."""
    assert layers._plain_numbers(values) is None


#: Band edges of every plain kind, the awkward values among them.
_FLOATS = [
    float("nan"),
    float("inf"),
    float("-inf"),
    0.0,
    -0.0,
    1.0,
    2.5,
    1e308,
    -1e308,
]
_INTS = [0, 1, -1, 7, 2**62, -(2**62), 2**63 - 1, -(2**63)]
_EDGES = {
    "float": _FLOATS,
    "float64": [np.float64(value) for value in _FLOATS],
    "int": _INTS,
    "int64": [np.int64(value) for value in _INTS],
}


@pytest.mark.parametrize("high_kind", list(_EDGES))
@pytest.mark.parametrize("low_kind", list(_EDGES))
def test_a_plain_extent_is_what_extent_announces(low_kind: str, high_kind: str) -> None:
    for low, high in itertools.product(_EDGES[low_kind], _EDGES[high_kind]):
        expected = to_native(layers._extent(low, high))

        read = layers._plain_extent(to_native(low), to_native(high))

        assert repr(read) == repr(expected), (low, high)
        assert type(read) is type(expected), (low, high)


# --- whole figures ------------------------------------------------------------------


def _line() -> Any:
    p = figure()
    y = _walk(80)
    y[[3, 4]] = np.nan
    y[9] = np.inf
    x = np.arange(80.0)
    x[20] = np.nan
    x[30] = -np.inf
    p.line(x, y)
    return p


def _labelled_lines() -> Any:
    p = figure()
    p.line(np.arange(40.0), _walk(40), legend_label="walk")
    p.line(list(range(40)), [v % 6 for v in range(40)], legend_label="ints")
    return p


def _multi_line() -> Any:
    p = figure()
    p.multi_line(
        [[1.0, 2.0, np.nan, 4.0], [1.0, 2.0, 3.0]],
        [[1.0, np.inf, 3.0], [-0.0, 2.0, 3.0, 4.0]],
    )
    return p


def _step() -> Any:
    p = figure()
    p.step(np.arange(30.0), _walk(30), mode="center", legend_label="steps")
    return p


def _scatter() -> Any:
    p = figure()
    x = np.arange(60.0)
    y = _walk(60)
    x[[2, 3]] = np.nan
    y[[5, 40]] = np.nan
    y[50] = np.inf
    p.scatter(x, y, legend_label="points")
    return p


def _filtered_scatter() -> Any:
    source = ColumnDataSource(dict(x=np.arange(30), y=np.arange(30) % 7))
    p = figure()
    p.scatter("x", "y", source=source, view=CDSView(filter=IndexFilter([0, 4, 29])))
    p.scatter(
        "x",
        "y",
        source=source,
        marker="square",
        view=CDSView(filter=BooleanFilter([i % 3 == 0 for i in range(30)])),
    )
    return p


def _shared() -> Any:
    x = np.arange(50.0)
    y = _walk(50)
    y[[7, 8]] = np.nan
    y[9] = np.inf
    source = ColumnDataSource(dict(x=x, y=y))
    p = figure()
    p.line("x", "y", source=source)
    p.scatter("x", "y", source=source)
    return p


def _dates() -> Any:
    p = figure(x_axis_type="datetime")
    p.line(np.arange(20) * 86_400_000.0, _walk(20))
    p.scatter(pd.date_range("2024-01-01", periods=20), _walk(20, 1))
    return p


def _varea() -> Any:
    """A band from zero, with gaps and infinities in every column."""
    p = figure()
    x = np.arange(60.0)
    x[[2, 3]] = np.nan
    x[10] = -np.inf
    top = _walk(60) + 20
    top[[5, 6]] = np.nan
    top[7] = np.inf
    top[8] = -0.0
    p.varea(x=x, y1=0, y2=top, legend_label="band")
    return p


def _varea_between() -> Any:
    """A band between two float columns: zero, ``-0.0``, gaps and overflow."""
    bottom = _walk(40, 1)
    bottom[[0, 1]] = [0.0, -0.0]
    bottom[2] = np.nan
    bottom[3] = -np.inf
    top = bottom + 5
    top[[0, 1, 2, 3]] = [1.0, 2.0, 3.0, 4.0]
    bottom[4], top[4] = -1e308, 1e308
    source = ColumnDataSource(dict(x=np.arange(40.0), lo=bottom, hi=top))
    p = figure()
    p.varea(x="x", y1="lo", y2="hi", source=source)
    return p


def _varea_ints() -> Any:
    """Integer columns, where the extent is exact and stays an integer."""
    p = figure()
    p.varea(
        x=list(range(30)),
        y1=[i % 3 for i in range(30)],
        y2=[2**62 + i for i in range(30)],
    )
    return p


def _varea_mixed() -> Any:
    """Columns of different kinds: floats, ``int64`` and ``float64``."""
    p = figure()
    p.varea(
        x=[float(i) for i in range(25)],
        y1=list(np.arange(25) % 4),
        y2=list(np.linspace(1.0, 9.0, 25)),
    )
    return p


def _harea() -> Any:
    """A band on its side, so its cursor is ``[edge, at]``."""
    p = figure()
    y = np.arange(50.0)
    y[4] = np.nan
    right = _walk(50) + 30
    right[[9, 10]] = np.nan
    right[11] = np.inf
    p.harea(y=y, x1=1, x2=right, legend_label="sideways")
    return p


def _varea_stack() -> Any:
    source = ColumnDataSource(
        dict(x=np.arange(30.0), a=_walk(30) + 10, b=_walk(30, 2) + 10)
    )
    p = figure()
    p.varea_stack(["a", "b"], x="x", source=source, legend_label=["a", "b"])
    return p


def _harea_stack() -> Any:
    source = ColumnDataSource(
        dict(y=np.arange(30.0), a=_walk(30) + 10, b=_walk(30, 2) + 10)
    )
    p = figure()
    p.harea_stack(["a", "b"], y="y", source=source, legend_label=["a", "b"])
    return p


FIGURES: dict[str, Build] = {
    "line": _line,
    "labelled-lines": _labelled_lines,
    "multi-line": _multi_line,
    "step": _step,
    "scatter": _scatter,
    "filtered-scatter": _filtered_scatter,
    "shared-source": _shared,
    "varea": _varea,
    "varea-between": _varea_between,
    "varea-ints": _varea_ints,
    "varea-mixed": _varea_mixed,
    "harea": _harea,
    "varea-stack": _varea_stack,
    "harea-stack": _harea_stack,
}


@pytest.mark.parametrize("name", list(FIGURES))
def test_a_figure_reads_in_bulk_as_it_does_value_by_value(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = layers._plain_numbers
    ran = []

    def counting(values: list) -> tuple[list, list] | None:
        read = plain(values)
        ran.append(read is not None)
        return read

    monkeypatch.setattr(layers, "_plain_numbers", counting)
    bulk = _read(FIGURES[name], monkeypatch)
    assert any(ran), "the bulk reading never ran"

    monkeypatch.setattr(layers, "_plain_numbers", lambda values: None)
    per_value = _read(FIGURES[name], monkeypatch)

    assert bulk == per_value


def test_a_datetime_axis_keeps_the_per_value_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Numbers on a ``DatetimeAxis`` are epoch milliseconds, announced as dates."""
    bulk = _read(_dates, monkeypatch)

    monkeypatch.setattr(layers, "_plain_numbers", lambda values: None)

    assert bulk == _read(_dates, monkeypatch)
    assert "2024-01-01" in bulk
    assert "1970-01-01" in bulk


def _dated_band() -> Any:
    p = figure(x_axis_type="datetime")
    p.varea(x=np.arange(20) * 86_400_000.0, y1=0, y2=_walk(20) + 10)
    return p


def test_a_band_on_a_datetime_axis_keeps_the_per_value_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its positions are epoch milliseconds, announced as dates."""
    bulk = _read(_dated_band, monkeypatch)

    monkeypatch.setattr(layers, "_plain_numbers", lambda values: None)

    assert bulk == _read(_dated_band, monkeypatch)
    assert "1970-01-01" in bulk


def _shared_with_a_gap() -> Any:
    """A point cloud on a line's source, its y column not plain numbers."""
    source = ColumnDataSource(dict(x=[1.0, 2.0, 3.0], y=[10.0, None, 30.0]))
    p = figure()
    p.line("x", "y", source=source)
    p.scatter("x", "y", source=source)
    return p


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(_shared, id="plain"),
        pytest.param(_shared_with_a_gap, id="not-plain"),
        pytest.param(_line, id="line"),
        pytest.param(_filtered_scatter, id="filtered-scatter"),
        pytest.param(_varea, id="varea"),
        pytest.param(_harea_stack, id="harea-stack"),
    ],
)
def test_the_columns_are_resolved_as_often_and_in_the_order_they_were(
    build: Build, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The bulk reading resolves the same columns, as often, in the same order.

    A source column is only read through :func:`resolve`, so this is what a
    column that is not the same on every read -- or fails on a later one --
    would see.
    """
    resolve = layers.resolve

    def reads(per_value: bool) -> list[str]:
        seen: list[str] = []

        def counting(glyph: Any, prop: str, data: dict) -> list:
            seen.append(prop)
            return resolve(glyph, prop, data)

        with monkeypatch.context() as patch:
            patch.setattr(layers, "resolve", counting)
            if per_value:
                patch.setattr(layers, "_plain_numbers", lambda values: None)
            BokehMaidr(build())
        return seen

    assert reads(per_value=False) == reads(per_value=True)


# --- the work itself --------------------------------------------------------------


def test_a_plain_line_is_not_announced_value_by_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    convert = layers.to_native

    def counting(value: Any) -> Any:
        calls.append(1)
        return convert(value)

    monkeypatch.setattr(layers, "to_native", counting)
    p = figure()
    p.line(np.arange(1000.0), _walk(1000))

    BokehMaidr(p)._flatten_maidr()

    assert len(calls) < 50, f"{len(calls)} conversions for 2000 plain values"


def test_a_plain_band_is_not_announced_value_by_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    convert = layers.to_native

    def counting(value: Any) -> Any:
        calls.append(1)
        return convert(value)

    monkeypatch.setattr(layers, "to_native", counting)
    p = figure()
    p.varea(x=np.arange(1000.0), y1=0, y2=_walk(1000) + 50)

    BokehMaidr(p)._flatten_maidr()

    assert len(calls) < 50, f"{len(calls)} conversions for a 1000-row band"


def test_a_point_cloud_on_a_shared_source_is_anchored_a_column_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the first point goes through ``mark_anchor``, which resolves the
    columns; the other 49 are read off what it resolved."""
    calls = []
    anchor = layers.mark_anchor

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return anchor(*args, **kwargs)

    monkeypatch.setattr(layers, "mark_anchor", counting)
    monkeypatch.setattr(bokeh_maidr, "mark_anchor", counting)

    maidr_ = BokehMaidr(_shared())

    cloud = next(
        layer for layer in maidr_.layers if layer.schema["type"] == PlotType.SCATTER
    )
    assert cloud.highlight["kind"] == "cursor"
    assert len(calls) == 1
