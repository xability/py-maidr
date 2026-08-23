from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.histogram import _plotly_dtick
from maidr.plotly.plotly_plot import PlotlyPlot, as_list

_logger = logging.getLogger(__name__)

#: Which marching-squares implementation to trace the curves with.
#:
#: Not a detail: ``mpl2014`` and ``serial`` disagree about the **order** they
#: return curves in, and the order is what pairs a series with the ``<path>``
#: that draws it. Measured on a level carrying two open curves and one closed
#: one, plotly writes the open ones first and ``mpl2014`` returns them in
#: exactly that order, while ``serial`` returns the closed one first. It is
#: also what matplotlib traces its own contours with, so the two py-maidr
#: contour readings describe curves computed the same way.
_CURVE_ALGORITHM = "mpl2014"

#: How many levels a trace may declare before it is declined.
#:
#: A runaway guard, not a judgement about how many levels are useful:
#: ``size`` is the author's, so ``dict(start=0, end=1, size=1e-9)`` asks for a
#: billion of them and would hang the export -- and building a schema must
#: never cost the render (#421, #636). No figure anyone draws comes near this.
_LEVEL_LIMIT = 1000

#: How many levels plotly aims for when the author names no ``ncontours``.
#: Plotly's own default, and the divisor of the rough step an automatic
#: contour rounds up from.
_DEFAULT_LEVEL_COUNT = 15

#: How far a multiple may miss a round number and still count as one, when
#: locating the first and last levels inside a field's range. Only the
#: ``ceil``/``floor`` are given this room: whether the result then *equals*
#: the range's own end is tested exactly, because plotly tests it exactly and
#: the difference decides a whole level (see :func:`automatic_levels`).
_MULTIPLE_TOLERANCE = 1e-9

#: What fraction of the narrowest grid cell a traced curve must span to be a
#: curve rather than the point where the field grazes a level. Far above the
#: last bits that separate five copies of one vertex (1.6e-15 on a grid of 5s,
#: measured) and far below any crossing, which is interpolated along a cell
#: edge and so spans a real part of one.
_POINT_FRACTION = 1e-9

#: How far past ``end`` plotly's level loop still steps, as a fraction of
#: ``size``. Measured rather than assumed, across seven specs: a run at
#: ``start=0.2, end=0.8, size=0.05`` draws a level at ``0.8000000000000002``
#: -- past ``end``, so the loop is not ``<= end`` -- while ``start=0, end=0.9,
#: size=0.5`` stops at ``0.5`` and does *not* draw ``1.0``, so it is not
#: ``end + size / 2`` either. ``end + size / 10`` fits all seven.
_END_TOLERANCE = 10


class PlotlyContourPlot(PlotlyPlot):
    """Extract data from a Plotly ``contour`` trace.

    A scalar field drawn as the curves along which it is constant. The core
    reads it as `CONTOUR`, whose point carries a `level` as well as an x and a
    y, and whose series is **one curve** rather than one level -- a field with
    two peaks crosses a level twice, and joining the two islands into one
    series would announce a curve running across ground the field never took.

    **Neither the curves nor, usually, the levels are in the trace.** Plotly
    ships a grid, works out where to cut it, and traces the curves in the
    browser. Reading this chart means doing both here: the levels by
    :func:`levels_of`, the curves by `contourpy` -- what matplotlib traces its
    own contours with, and what arrives with matplotlib, which py-maidr
    already requires.

    Two independent implementations agreeing is not a contract, so what they
    agree about was measured rather than assumed. Across 33 fields and 207
    levels -- random sums of gaussians, a saddle, a monkey saddle, ripples, a
    staircase, noise -- plotly and ``contourpy`` **always** found the same
    number of curves in a level, and put them in the same order all but 18
    times. So the curves themselves are the same curves and the reading is
    sound, while *which drawn path is which curve* is not always answerable,
    which is what :meth:`_get_selector` turns on.

    Parameters
    ----------
    trace : dict
        The Plotly trace dictionary.
    layout : dict
        The Plotly figure layout.
    layer_position : int
        The trace's zero-based position among the subplot's traces that draw
        into the ``contourlayer``, from
        :func:`~maidr.plotly.candlestick.layer_position`. Only the figure-wide
        pass knows it, which is why this layer is built there rather than by
        :class:`~maidr.plotly.plotly_plot_factory.PlotlyPlotFactory`.
    **kwargs : str
        Axis names forwarded to the parent class.
    """

    def __init__(
        self, trace: dict, layout: dict, *, layer_position: int, **kwargs: str
    ) -> None:
        self._layer_position = layer_position
        #: The level index behind each emitted series, in emission order.
        #:
        #: What tells each series which ``g.contourlevel`` draws it, and --
        #: by having a repeat in it -- that a level broke into islands, which
        #: is when the layer declines its selectors. It indexes the declared
        #: levels rather than counting series, and that is load-bearing: a
        #: level nothing reaches emits no series but **does** reach the
        #: document, as a ``g.contourlevel`` holding no ``path`` at all
        #: (measured), so the groups and the levels stay in step while the
        #: series do not.
        self._series_levels: list[int] = []
        super().__init__(trace, layout, PlotType.CONTOUR, **kwargs)

    def _extract_plot_data(self) -> list[list[dict]]:
        """Trace one series per curve, each point carrying its level.

        Returns
        -------
        list of list of dict
            One series per curve, in plotly's own drawing order. Empty when
            the trace declines -- see :func:`levels_of` and :func:`_grid` for
            the reasons -- which leaves the figure with no contour layer
            rather than a wrong one (#636).
        """
        self._series_levels = []

        grid = self._field()
        if grid is None:
            return []

        x, y, z = grid
        # The field, not just the trace: an automatic contour chooses its
        # levels from the range of what it draws. Asked for separately from
        # the grid because the two are not always the same array -- see
        # `_level_field`.
        levels = levels_of(self._trace, self._level_field(z))
        if not levels:
            return []

        # The whole of the tracing, not only the generator's construction.
        # `.lines()` is where the work happens, so it is where an unforeseen
        # grid or a stricter future contourpy would raise -- and an exception
        # escaping here leaves `render()` and takes the entire figure's
        # schema with it, which is the one outcome every guard in this module
        # exists to avoid (#421, #636). Costing one layer is the point.
        try:
            from contourpy import contour_generator

            generator = contour_generator(
                x=x, y=y, z=z, name=_CURVE_ALGORITHM, line_type="SeparateCode"
            )
            traced = [generator.lines(level)[0] for level in levels]
        except Exception:
            # `mpl2014` is the one algorithm whose curve order was measured
            # against plotly's, so a contourpy that no longer offers it
            # leaves nothing to emit in the order the selectors assume.
            # Declining costs one layer; guessing would put every highlight
            # on the wrong curve.
            #
            # Logged rather than swallowed outright, because everything a
            # *chart* can decline for is guarded above: reaching here means
            # the environment is not what it was measured to be, and a layer
            # that vanishes with nothing said is hard to tell from one that
            # was never there.
            _logger.debug(
                "maidr: could not trace a plotly contour with contourpy",
                exc_info=True,
            )
            return []

        # Built after the tracing rather than during it, so a failure part
        # way through leaves no half-filled `_series_levels` behind: the two
        # are read together and a mismatch would put every later series on
        # the wrong level's group.
        # A curve counts as one when it goes somewhere, measured against the
        # grid it was traced through -- see `_has_extent`.
        cell = _smallest_step(x, y)
        data: list[list[dict]] = []
        for index, curves in enumerate(traced):
            for curve in curves:
                if not _has_extent(curve, cell):
                    continue
                data.append(
                    [
                        {
                            MaidrKey.X: float(vertex[0]),
                            MaidrKey.Y: float(vertex[1]),
                            MaidrKey.LEVEL: levels[index],
                        }
                        for vertex in curve
                    ]
                )
                self._series_levels.append(index)

        return data

    def _level_field(self, z: Any) -> Any:
        """The values an automatic level list takes its range from.

        The grid itself, for a ``contour``: the numbers it draws are the
        numbers it was given. A ``histogram2dcontour`` hands the tracer a
        grid with zeros where a cell has no answer, and those zeros are not
        values the chart measured -- see
        :meth:`~maidr.plotly.histogram2dcontour.PlotlyHistogram2dContourPlot._level_field`.
        """
        return z

    def _field(self) -> tuple[list[float], list[float], Any] | None:
        """The grid the curves are traced through, or None when there is none.

        A ``contour`` carries its field, so this is where the trace's own
        ``z`` is read. A ``histogram2dcontour`` carries samples instead and
        bins them into one -- which is the *only* difference between the two
        readings, and why it overrides this and nothing else.
        """
        return _grid(self._trace)

    def _get_selector(self) -> list[str]:
        """Return one selector per emitted series, or none for the whole layer.

        Plotly gives every declared level a ``g.contourlevel`` -- including the
        ones the field never reaches, which get the group and no ``path`` --
        and one ``<path>`` per disjoint curve inside it. The **level** is
        therefore addressable: the groups run in the declared order, measured
        on every figure below.

        ``:nth-of-type`` counts by *tag* among all siblings rather than among
        the ones matching the class beside it, so it is exact only where the
        siblings are homogeneous. Measured across seven configurations --
        every ``coloring`` mode, ``showlabels``, a ``histogram2dcontour``
        sibling, and two contours on one subplot -- they are: a
        ``.contourlayer`` holds nothing but ``g.contour``, a ``g.contourlines``
        nothing but ``g.contourlevel``, and a ``g.contourlevel`` nothing but
        ``path``.

        A **curve within a level** is not. Plotly and ``contourpy`` order the
        islands of one level differently, and not only on contrived fields: a
        sweep of 33 fields and 207 levels -- random sums of gaussians, a
        saddle, a monkey saddle, ripples, a staircase, noise -- put the two in
        the opposite order 18 times, five of them on ordinary two-peaked
        gaussian fields. A positional selector would resolve to a real element
        and to the wrong one, and the core parses the resolved path to place
        the per-point highlights, so every point of that series would land on
        an island the reader is not on. Worse than none, which is the outcome
        #145 settled.

        The same sweep found **no** disagreement about how many curves a level
        has: 207 levels, 207 agreements. So the ambiguity is exactly the
        ordering, and it only exists where a level has more than one curve. A
        layer whose every drawn level draws a single curve therefore has one
        forced mapping rather than a chosen one, and keeps its highlight; a
        layer with an island anywhere ships without one and keeps its audio,
        braille and text.

        The one further case with nothing to address is ``coloring: "fill"``
        (the default) with ``showlines: False``: measured in Chromium, plotly
        then writes **no** ``g.contourlevel`` at all and draws only the bands.
        The layer still reads -- a band's boundary is exactly the level curve,
        so what is announced is true of the drawing -- and ships without a
        highlight.

        Returns
        -------
        list of str
            One selector per series, in emission order, or an empty list.
        """
        if not draws_its_lines(self._trace):
            return []
        if len(set(self._series_levels)) != len(self._series_levels):
            return []

        return [
            f"{self._subplot_css_prefix()}.contourlayer > "
            f"g.contour:nth-of-type({self._layer_position + 1}) "
            f"g.contourlevel:nth-of-type({level + 1}) "
            f"path:nth-of-type(1)"
            for level in self._series_levels
        ]


def is_contour_trace(trace: dict) -> bool:
    """Report whether a trace is a contour plot."""
    return trace.get("type") == "contour"


def draws_its_lines(trace: dict) -> bool:
    """Report whether plotly writes this trace's level curves as paths.

    ``showlines`` is only honoured under ``coloring: "fill"``, which is the
    default. Measured: with ``coloring: "heatmap"`` and ``showlines: False``
    the curves are still drawn, and only the filled case removes them -- and
    removes the ``g.contourlevel`` groups with them, so there is no element
    left to point at.
    """
    contours = trace.get("contours")
    if not isinstance(contours, dict):
        return True
    if contours.get("coloring", "fill") != "fill":
        return True
    return contours.get("showlines") is not False


def levels_of(trace: dict, z: Any = None) -> list[float] | None:
    """Return the levels plotly draws: the author's, or the ones it picks.

    Which route applies is asked first, rather than read off a None coming
    back from the first one. :func:`declared_levels` answers None for two
    unrelated reasons -- the author did not name their own levels, and the
    author named a *billion* of them -- and only the first is a reason to
    pick levels instead. Falling through on both would read a runaway spec at
    nine levels of someone else's choosing, which is a chart the author did
    not write and plotly does not draw.

    Parameters
    ----------
    trace : dict
        One trace of the figure.
    z : Any, optional
        The field, needed only when the levels are automatic -- they are
        chosen from its range. Without it an automatic trace declines.

    Returns
    -------
    list of float or None
        The levels, or None when there are none to read.
    """
    if declares_levels(trace):
        return declared_levels(trace)
    return automatic_levels(trace, z)


def declares_levels(trace: dict) -> bool:
    """Whether the levels are the author's rather than plotly's to pick.

    **Both ends** is what makes them the author's. Plotly coerces
    ``autocontour`` to true when either ``start`` or ``end`` is missing, so a
    trace naming one of them, or only a ``size``, has its levels picked for
    it -- measured, all three draw the same nine levels as a trace naming
    nothing at all. An explicit ``autocontour: True`` overrides even a
    complete spec, and a ``constraint`` contour is not a set of levels at
    all (see :func:`_levels_spec`).
    """
    contours = _levels_spec(trace)
    if contours is None or trace.get("autocontour") is True:
        return False
    return (
        _a_number(contours.get("start")) is not None
        and _a_number(contours.get("end")) is not None
    )


def declared_levels(trace: dict) -> list[float] | None:
    """Return the levels the author asked for, or None when plotly picks them.

    Plotly steps ``start``, ``start + size``, ... while the level is below
    ``end + size / 10``, and swaps ``start`` and ``end`` when they arrive the
    wrong way round. Accumulated rather than computed as ``start + k * size``
    so the announced level is bit-for-bit the one plotly drew: with
    ``start=0.2, size=0.2`` both routes agree on 0.4 and disagree on the
    third level, and the level is also what is handed to the curve tracer.

    What makes a spec the author's is :func:`declares_levels`; None here
    means either that it is not theirs or that theirs runs away (see
    :func:`_stepped`), which is why :func:`levels_of` asks which case it is
    before reading this.

    With both ends named, a missing or zero ``size`` is **not** a decline:
    plotly keeps the ends and derives a width for them, through the same
    round-up an automatic contour uses. Measured on ``start=0.2, end=0.8``:
    no size and a zero size both draw a width of 0.05, which is
    ``(0.8 - 0.2) / 15`` rounded up, and ``ncontours=4`` draws 0.2.
    """
    if not declares_levels(trace):
        return None

    contours = _levels_spec(trace) or {}
    start = _a_number(contours.get("start"))
    end = _a_number(contours.get("end"))
    if start is None or end is None:  # pragma: no cover - `declares_levels`
        return None

    low, high = (start, end) if start <= end else (end, start)
    size = _a_number(contours.get("size"))
    if size is None or size <= 0:
        count = _a_number(trace.get("ncontours"))
        size = _plotly_dtick((high - low) / (count or _DEFAULT_LEVEL_COUNT))
    return _stepped(low, high, size)


def automatic_levels(trace: dict, z: Any) -> list[float] | None:
    """Return the levels plotly picks for itself, from the field's range.

    The rule lives in plotly.js and is reproduced here rather than declined,
    which is what #642 was filed for. It turned out to be four steps, each
    measured against the browser:

    1. A rough step of ``(zmax - zmin) / (ncontours or 15)``, rounded up to a
       1/2/5x10ⁿ value by the same ``roundUp`` a histogram's bin width goes
       through -- **strictly** greater, which is the whole of what made a
       field spanning ``0 .. 3`` look unreproducible (#646). The ``or`` reads
       a zero ``ncontours`` as none given, which no measured figure can
       reach: plotly's own validator rejects anything below 1, so a trace
       built through `graph_objects` never carries one.
    2. ``start``: the first multiple of the step at or above ``zmin``, moved
       up one when it lands *on* it, so no level sits at the floor of the
       field.
    3. ``end``: the last multiple at or below ``zmax``, moved down one when
       it lands on it, for the same reason at the ceiling.
    4. If those cross -- an ``ncontours`` so small that no multiple fits
       inside at all -- both become their own midpoint, and the field gets a
       single level. Measured: ``ncontours=2`` over ``0 .. 100`` draws one
       level at 50, and ``ncontours=1`` over ``0 .. 10`` draws one at 10.

    A field with no range at all needs no case of its own: its rough step is
    zero, the round-up answers 1, and step 4 catches it.

    Steps 2 and 3 each round twice, and all four roundings pull in opposite
    directions on purpose. The multiple itself is taken with a tolerance,
    because a range that divides evenly rarely says so in binary --
    ``-0.3 / 0.05`` is -5.999999999999999, and rounding that at face value
    starts the list a whole level late. The tests for a level landing *on* the
    floor or the ceiling are then exact, because the value the tolerance
    recovered is a hair off the bound rather than on it: ``0.009 / 0.0001``
    rounds up to a top level of ``0.009000000000000001``, and a tolerant
    comparison would read that as sitting on the ceiling and drop the level
    plotly drew there.

    Measured against plotly's drawn levels on **49 figures** -- 26 z ranges
    from ``0 .. 0.07`` to ``0 .. 1000``, positive, negative and straddling, 8
    explicit ``ncontours`` from 1 to 30, and 15 ranges chosen for landing on
    exactly those ties. All 49 agree, level for level, and each of the four
    roundings is the difference on at least one of them.
    """
    if _levels_spec(trace) is None or z is None:
        return None

    # Through the mask rather than around it. `_grid` hands over a masked
    # array, and reading `np.asarray` off one gives the buffer *under* the
    # mask -- which happens to hold the NaN that caused the masking today,
    # so the filter below would keep working by luck if a masked value were
    # ever a finite one.
    values = np.ma.filled(np.ma.asarray(z, dtype=float), np.nan)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    low, high = float(np.min(finite)), float(np.max(finite))
    # A constant field needs no guard of its own. Its range is zero, so the
    # rough step is zero and the round-up answers 1; the first multiple above
    # the floor is then past the last below the ceiling, and the fallback in
    # step 4 puts one level at the constant value -- which is exactly what
    # plotly draws for it (measured: a grid of 3s gets a single level at 3).
    # That level *is* the whole field, so it holds no curve, and #636's guard
    # drops the empty layer.
    count = _a_number(trace.get("ncontours"))
    size = _plotly_dtick((high - low) / (count or _DEFAULT_LEVEL_COUNT))
    if size <= 0:
        return None

    start = math.ceil(low / size - _MULTIPLE_TOLERANCE) * size
    if start == low:
        start += size
    end = math.floor(high / size + _MULTIPLE_TOLERANCE) * size
    if end == high:
        end -= size
    if start > end:
        start = end = (start + end) / 2

    return _stepped(start, end, size)


def _levels_spec(trace: dict) -> dict | None:
    """The trace's ``contours``, when it describes a set of levels at all.

    A **constraint** contour draws one curve at ``value`` and means "the
    region beyond it", which is a different chart -- measured, one group at
    ``value`` however its ``start``/``end``/``size`` are written, so reading
    those would announce levels it does not draw. A trace with no ``contours``
    at all is a set of levels plotly picks, so it passes.
    """
    contours = trace.get("contours")
    if contours is None:
        return {}
    if not isinstance(contours, dict):
        return None
    if contours.get("type") not in (None, "levels"):
        return None
    return contours


def _stepped(start: float, end: float, size: float) -> list[float] | None:
    """Step from ``start`` while the level is below ``end + size / 10``.

    The one loop both paths use, because plotly uses one: the tolerance was
    measured on an explicit spec and the automatic ``end`` is fed to the same
    arithmetic. None when the count would run away -- see :data:`_LEVEL_LIMIT`.
    """
    if (end - start) / size > _LEVEL_LIMIT:
        return None

    levels = []
    level = start
    limit = end + size / _END_TOLERANCE
    while level < limit:
        levels.append(level)
        level += size
    return levels


def _grid(trace: dict) -> tuple[list[float], list[float], Any] | None:
    """Return the field as ``(x, y, z)``, or None when it cannot be traced.

    ``z`` comes back masked where it is missing, which is what makes the
    curves stop at a hole the way plotly's do -- measured on a field with the
    peak punched out: both dropped the level the hole ate and agreed on the
    rest.

    The mask is what ``contourpy`` documents for missing points. Passing the
    NaN array straight through gives the same curves today -- measured, and it
    is why removing the mask breaks no test -- but that is ``mpl2014``
    treating NaN as missing rather than anything promised, so the documented
    route is the one taken.
    """
    rows = [as_list(row) for row in as_list(trace.get("z"))]
    if not rows:
        return None

    width = len(rows[0])
    if any(len(row) != width for row in rows):
        # Plotly draws no rectangle from a ragged grid, and the tracer wants
        # one array.
        return None

    # A cell that is not a finite number becomes NaN, which is what a hole in
    # the field is: `_a_number` answers None and numpy writes NaN for it.
    z = np.array([[_a_number(value) for value in row] for row in rows], dtype=float)
    if trace.get("transpose") is True:
        # `transpose` turns z over and leaves x and y alone -- measured on an
        # asymmetric field, where the two readings put the peak in different
        # places and plotly drew the transposed one.
        z = z.T
    if z.shape[0] < 2 or z.shape[1] < 2:
        # Marching squares needs a cell, which needs two rows and two columns.
        return None

    x = _coordinates(trace, "x", z.shape[1])
    y = _coordinates(trace, "y", z.shape[0])
    if x is None or y is None:
        return None

    return x, y, np.ma.masked_invalid(z)


def _has_extent(curve: Any, cell: float) -> bool:
    """Whether a traced curve goes anywhere, rather than touching a point.

    Where the field grazes a level at exactly one grid point -- a lone cell
    holding the level's own value -- ``contourpy`` returns a closed curve
    whose every vertex is that point: five copies of it, spanning nothing.
    Plotly draws no path there, measured on a ``min`` aggregate whose lowest
    interior cell is exactly a level. Dropping it is not only agreement with
    plotly, though: a series of one point repeated is not a curve for anyone
    to read along, and it would take a ``g.contourlevel`` index with it that
    a real curve in the same level needs.

    "Spanning nothing" has to be measured rather than tested for zero. The
    level that grazes a cell is rarely the cell's value written out -- an
    automatic 0.4 arrives as ``0.39999999999999997`` -- and the five vertices
    then differ in the last bits, 1.6e-15 apart on a grid whose cells are 5
    wide. So the span is compared against the grid, at a fraction no curve
    tracing a real crossing comes near: the vertices are interpolated along
    the cell edges, so a curve that crosses at all crosses a measurable part
    of one.
    """
    vertices = np.asarray(curve, dtype=float)
    if vertices.size == 0:
        return False
    span = max(float(np.ptp(vertices[:, 0])), float(np.ptp(vertices[:, 1])))
    return span > cell * _POINT_FRACTION


def _smallest_step(x: list[float], y: list[float]) -> float:
    """The narrowest cell in the grid, as the scale a curve is measured on.

    The narrowest rather than the average, so an unevenly spaced grid is
    judged by its own finest detail rather than by a figure no cell has.
    """
    steps = [
        abs(b - a)
        for axis in (x, y)
        for a, b in zip(axis, axis[1:])
        if abs(b - a) > 0
    ]
    return min(steps) if steps else 1.0


def _coordinates(trace: dict, key: str, count: int) -> list[float] | None:
    """Return one axis's grid coordinates, or None when they are not numbers.

    An explicit array wins when it describes the grid; otherwise the
    ``x0``/``dx`` pair does, at plotly's own defaults of 0 and 1. An array of
    the wrong length is declined rather than padded: plotly does something
    with it, but not something that was measured, and a grid guessed wrong
    puts every curve in the wrong place.

    A **categorical** axis is declined by the same test. A contour crosses
    between columns, so a curve sits at a fraction of the way from one
    category to the next -- a position a category name cannot express, and
    which naming the nearer category would misreport.
    """
    declared = as_list(trace.get(key))
    if declared:
        if len(declared) != count:
            return None
        values = [_a_number(value) for value in declared]
        if any(value is None for value in values):
            return None
        return values  # type: ignore[return-value]

    origin = _a_number(trace.get(f"{key}0"))
    step = _a_number(trace.get(f"d{key}"))
    origin = 0.0 if origin is None else origin
    step = 1.0 if step is None else step
    return [origin + step * index for index in range(count)]


def _a_number(value: Any) -> float | None:
    """Return ``value`` as a finite float, or None when it is not one."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
