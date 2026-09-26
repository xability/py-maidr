"""Read the values a Bokeh glyph draws, off the document model.

A Bokeh glyph does not hold its data. Each coordinate is a *spec* naming
where the numbers come from: a column of the renderer's data source, a
constant, or an expression evaluated in the browser (``vbar_stack`` spells
every bar's ``bottom`` and ``top`` as a running sum of source columns).
This module turns those specs back into arrays the way BokehJS does, so the
schema describes what is drawn rather than what the author typed.

It also keeps two spellings of a value apart: :func:`to_native` is what the
MAIDR schema announces (a date as an ISO string), and :func:`to_coordinate`
is what BokehJS places a mark at (a date as milliseconds since the epoch,
which is how a ``DatetimeAxis`` is scaled).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Sequence

import numpy as np

from maidr.plotly.plotly_plot import as_list


class UnreadableSpec(Exception):
    """A glyph property whose values cannot be recovered in Python.

    Raised for a ``CustomJS`` transform or expression, a column the source
    does not have, or a data source that holds no columns of its own
    (``AjaxDataSource`` and friends fetch theirs in the browser). The caller
    skips the renderer with a warning rather than guessing.
    """


def source_length(data: dict) -> int:
    """
    The number of rows a ``ColumnDataSource``'s ``data`` holds.

    Parameters
    ----------
    data : dict
        The source's ``data`` mapping.

    Returns
    -------
    int
        The length its columns share, or 0 for an empty source.

    Raises
    ------
    UnreadableSpec
        When the columns differ in length, which Bokeh itself only warns
        about: no row count would say which values belong together.
    """
    lengths = set()
    for column in data.values():
        try:
            lengths.add(len(column))
        except TypeError:
            continue
    if len(lengths) > 1:
        raise UnreadableSpec(
            f"its data source has columns of different lengths {sorted(lengths)}"
        )
    return lengths.pop() if lengths else 0


def _spec_parts(spec: Any) -> tuple[str, Any, Any]:
    """
    Split a dataspec value into its kind, payload and transform.

    Bokeh accepts one spec in several spellings -- a bare string (a column
    name for a coordinate), a number, a ``{"field": ...}`` dict, and the
    ``Field``/``Value``/``Expr`` objects ``bokeh.core.property.vectorization``
    defines -- and reading the attribute hands back whichever was assigned.

    Returns
    -------
    tuple of (str, Any, Any)
        ``("field", name, transform)``, ``("value", value, transform)`` or
        ``("expr", expression, transform)``.
    """
    from bokeh.core.property.vectorization import Expr, Field, Value

    if isinstance(spec, Field):
        return "field", spec.field, _given(spec.transform)
    if isinstance(spec, Value):
        return "value", spec.value, _given(spec.transform)
    if isinstance(spec, Expr):
        return "expr", spec.expr, _given(spec.transform)
    if isinstance(spec, dict):
        transform = spec.get("transform")
        if "field" in spec:
            return "field", spec["field"], transform
        if "expr" in spec:
            return "expr", spec["expr"], transform
        return "value", spec.get("value"), transform
    if isinstance(spec, str):
        return "field", spec, None
    return "value", spec, None


def _given(value: Any) -> Any:
    """
    The transform a spec carries, or ``None``.

    An absent transform is a sentinel whose name and home module have moved
    between Bokeh releases; a present one is always a ``Model``, so that is
    what is asked.
    """
    from bokeh.model import Model

    return value if isinstance(value, Model) else None


def spec_field(glyph: Any, prop: str) -> str | None:
    """
    The source column a glyph property reads, when it reads one directly.

    Parameters
    ----------
    glyph : bokeh.models.Glyph
        The glyph.
    prop : str
        The property name, e.g. ``"x"``.

    Returns
    -------
    str or None
        The column name, or ``None`` for a constant or an expression.
    """
    kind, payload, _ = _spec_parts(getattr(glyph, prop, None))
    return payload if kind == "field" else None


def spec_transform(glyph: Any, prop: str) -> Any:
    """
    The transform a glyph property applies, or ``None``.

    Parameters
    ----------
    glyph : bokeh.models.Glyph
        The glyph.
    prop : str
        The property name.

    Returns
    -------
    Any
        The ``Transform`` model (``Dodge``, a colour mapper, ...), or ``None``.
    """
    _, _, transform = _spec_parts(getattr(glyph, prop, None))
    return transform


def spec_expression(glyph: Any, prop: str) -> Any:
    """
    The expression a glyph property evaluates, or ``None``.

    Parameters
    ----------
    glyph : bokeh.models.Glyph
        The glyph.
    prop : str
        The property name.

    Returns
    -------
    Any
        The ``Expression`` model (``Stack``, ``CumSum``, ...), or ``None``.
    """
    kind, payload, _ = _spec_parts(getattr(glyph, prop, None))
    return payload if kind == "expr" else None


def resolve(glyph: Any, prop: str, data: dict) -> list:
    """
    The values a glyph property takes, one per source row.

    Transforms that only move a mark on screen -- ``Dodge``, ``Jitter`` --
    are ignored, because the value a reader wants is the one the author
    plotted, not the offset it is drawn at. A mapper (colour, marker,
    hatch) is ignored for the same reason: the mapped *field* is the data.
    Any other transform changes the value in the browser and is refused. ``Stack`` and
    ``CumSum`` expressions are evaluated, since they are the only place a
    stacked bar's extent exists.

    Parameters
    ----------
    glyph : bokeh.models.Glyph
        The glyph.
    prop : str
        The property to read.
    data : dict
        The renderer's ``ColumnDataSource.data``.

    Returns
    -------
    list
        One value per row of the source.

    Raises
    ------
    UnreadableSpec
        When the values exist only in the browser.
    """
    from bokeh.models import CumSum, Dodge, Jitter, Stack
    from bokeh.models.mappers import Mapper

    n = source_length(data)
    kind, payload, transform = _spec_parts(getattr(glyph, prop, None))
    if transform is not None and not isinstance(transform, (Dodge, Jitter, Mapper)):
        # Any other transform -- a ``CustomJSTransform``, an interpolator --
        # changes the value drawn, and only the browser computes it; reading
        # the raw column would announce numbers the chart does not show.
        raise UnreadableSpec(f"{type(transform).__name__} is evaluated in the browser")

    if kind == "field":
        if payload not in data:
            raise UnreadableSpec(f"column {payload!r} is not in the data source")
        return _column(data[payload])
    if kind == "value":
        return [payload] * n
    if isinstance(payload, Stack):
        total = np.zeros(n, dtype=float)
        for field in payload.fields:
            if field not in data:
                raise UnreadableSpec(f"column {field!r} is not in the data source")
            total = total + _numeric(data[field])
        return total.tolist()
    if isinstance(payload, CumSum):
        if payload.field not in data:
            raise UnreadableSpec(f"column {payload.field!r} is not in the data source")
        running = np.cumsum(_numeric(data[payload.field]))
        if payload.include_zero:
            running = np.concatenate([[0.0], running[:-1]])
        return running.tolist()
    raise UnreadableSpec(f"{type(payload).__name__} is evaluated in the browser")


def _column(values: Any) -> list:
    """A source column as a plain list, dates kept as ``datetime64``."""
    if isinstance(values, np.ndarray):
        return list(values)
    if hasattr(values, "to_numpy"):
        # A pandas Series: through numpy, so a date column arrives as
        # ``datetime64`` the way a numpy column does.
        return list(values.to_numpy())
    return list(values)


def _numeric(values: Any) -> np.ndarray:
    """A column as floats, ``None`` read as NaN the way BokehJS reads it."""
    return np.array(
        [np.nan if v is None else v for v in _column(values)], dtype=float
    )


def visible_indices(renderer: Any, n: int) -> list[int]:
    """
    The source rows a renderer draws, after its ``CDSView`` filter.

    Every filter BokehJS can evaluate without running user JS is evaluated
    here. A ``CustomJSFilter`` cannot be, so it is treated as passing every
    row -- the reader then hears rows the chart does not draw, which is the
    lesser failure than hearing none of them.

    Parameters
    ----------
    renderer : bokeh.models.GlyphRenderer
        The renderer.
    n : int
        The number of rows in its source.

    Returns
    -------
    list of int
        The drawn row indices, ascending.
    """
    view = getattr(renderer, "view", None)
    view_filter = getattr(view, "filter", None)
    if view_filter is None:
        return list(range(n))
    mask = _filter_mask(view_filter, renderer.data_source.data, n)
    return [i for i in range(n) if mask[i]]


def _filter_mask(view_filter: Any, data: dict, n: int) -> np.ndarray:
    """Evaluate one ``Filter`` model into a boolean mask over ``n`` rows."""
    import bokeh.models as bm

    name = type(view_filter).__name__
    if name == "AllIndices":
        return np.ones(n, dtype=bool)
    # An ``IndexFilter`` or ``BooleanFilter`` left at its default ``None``
    # keeps every row, as BokehJS evaluates it; only a given list narrows.
    if isinstance(view_filter, bm.IndexFilter):
        if view_filter.indices is None:
            return np.ones(n, dtype=bool)
        mask = np.zeros(n, dtype=bool)
        for index in view_filter.indices:
            if 0 <= int(index) < n:
                mask[int(index)] = True
        return mask
    if isinstance(view_filter, bm.BooleanFilter):
        if view_filter.booleans is None:
            return np.ones(n, dtype=bool)
        flags = list(view_filter.booleans)
        return np.array([bool(flags[i]) if i < len(flags) else False for i in range(n)])
    if isinstance(view_filter, bm.GroupFilter):
        column = _column(data.get(view_filter.column_name, [None] * n))
        return np.array([column[i] == view_filter.group for i in range(n)])
    operands = getattr(view_filter, "operands", None)
    if name == "IntersectionFilter" and operands:
        return np.logical_and.reduce([_filter_mask(f, data, n) for f in operands])
    if name == "UnionFilter" and operands:
        return np.logical_or.reduce([_filter_mask(f, data, n) for f in operands])
    if name == "DifferenceFilter" and operands:
        mask = _filter_mask(operands[0], data, n)
        for other in operands[1:]:
            mask = mask & ~_filter_mask(other, data, n)
        return mask
    if name == "SymmetricDifferenceFilter" and operands:
        masks = [_filter_mask(f, data, n) for f in operands]
        return np.logical_xor.reduce(masks)
    if name == "InversionFilter":
        return ~_filter_mask(view_filter.operand, data, n)
    return np.ones(n, dtype=bool)


def is_missing(value: Any) -> bool:
    """
    Whether a value is one BokehJS leaves a gap for: None, NaN or NaT.

    Parameters
    ----------
    value : Any
        One value read from a source column.

    Returns
    -------
    bool
        True for ``None``, a NaN, ``NaT`` or pandas' ``NA``.
    """
    if value is None or type(value).__name__ in ("NaTType", "NAType"):
        # pandas' ``NaT`` and ``NA``, named rather than imported.
        return True
    if isinstance(value, np.datetime64):
        return bool(np.isnat(value))
    try:
        return math.isnan(value)
    except TypeError:
        return False


def is_temporal(values: Sequence[Any]) -> bool:
    """
    Whether a column holds dates rather than numbers or factors.

    Parameters
    ----------
    values : sequence
        The column's values.

    Returns
    -------
    bool
        True when any present value is a ``datetime64`` or a date.
    """
    return any(
        isinstance(v, (np.datetime64, date)) for v in values if not is_missing(v)
    )


def dates_to_iso(values: Sequence[Any]) -> list:
    """
    Spell a column of dates as ISO strings, one unit for the whole column.

    Delegates to the Plotly path's :func:`~maidr.plotly.plotly_plot.as_list`,
    so a daily series reads ``2024-01-01`` on both rather than one of them
    carrying a midnight the other does not.

    Parameters
    ----------
    values : sequence
        ``datetime64``, ``datetime`` or ``pandas.Timestamp`` entries; a
        missing one stays ``None``.

    Returns
    -------
    list
        ISO strings, with ``None`` where a value was missing.
    """
    stamps = np.array(
        [
            np.datetime64("NaT", "us") if is_missing(v) else np.datetime64(_naive(v))
            for v in values
        ]
    )
    return [None if s == "NaT" else s for s in as_list(stamps)]


def epoch_ms_to_iso(values: Sequence[Any]) -> list:
    """
    Spell epoch milliseconds -- how a ``DatetimeAxis`` stores time -- as ISO.

    Parameters
    ----------
    values : sequence of float
        Milliseconds since the epoch, UTC.

    Returns
    -------
    list
        ISO strings, ``None`` where a value was missing.
    """
    return dates_to_iso(
        [
            None
            if is_missing(v)
            else datetime.fromtimestamp(float(v) / 1000.0, tz=timezone.utc)
            for v in values
        ]
    )


def _naive(value: Any) -> Any:
    """Drop a timezone the way BokehJS does, by reading the UTC instant."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    to_datetime64 = getattr(value, "to_datetime64", None)
    if to_datetime64 is not None:
        return to_datetime64()
    return value


def to_native(value: Any) -> Any:
    """
    One value as the MAIDR schema carries it.

    Numpy scalars become Python ones, a date an ISO string, a nested factor
    a list, and a missing value ``None`` -- a bare ``NaN`` is not JSON and
    stops ``JSON.parse`` on the page.

    Parameters
    ----------
    value : Any
        A value read from a source column.

    Returns
    -------
    Any
        A JSON-serializable value.
    """
    if is_missing(value):
        return None
    if isinstance(value, (np.datetime64, date)) or hasattr(value, "to_datetime64"):
        return dates_to_iso([value])[0]
    if isinstance(value, (list, tuple)):
        return [to_native(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def to_coordinate(value: Any) -> Any:
    """
    One value as BokehJS places it on an axis.

    The page moves a highlight cursor to this, so it must be in the axis's
    own units: a date is milliseconds since the epoch, and a nested factor
    the list BokehJS resolves against its ``FactorRange``.

    Parameters
    ----------
    value : Any
        A value read from a source column.

    Returns
    -------
    Any
        A JSON-serializable coordinate, or ``None`` for a missing value.
    """
    if is_missing(value):
        return None
    if isinstance(value, (np.datetime64, date)) or hasattr(value, "to_datetime64"):
        stamp = np.datetime64(_naive(value), "us")
        return float(stamp.astype("int64")) / 1000.0
    return to_native(value)


def factor_label(value: Any) -> str:
    """
    A categorical coordinate as the one string a reader hears.

    A nested factor ``("Apples", "2015")`` is joined the way Bokeh's own
    axis stacks its levels, outermost first.

    Parameters
    ----------
    value : Any
        A factor, nested or not.

    Returns
    -------
    str
        The label.
    """
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(to_native(value))
