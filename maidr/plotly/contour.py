from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
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

    **The curves are not in the trace.** Plotly ships a grid and a level
    spacing and computes the curves in the browser, so reading this chart
    means tracing the same marching squares here. That is what `contourpy`
    does -- it is what matplotlib traces its own contours with, and it arrives
    with matplotlib, which py-maidr already requires.

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
            the trace declines -- see :func:`declared_levels` and
            :func:`_grid` for the three reasons -- which leaves the figure
            with no contour layer rather than a wrong one (#636).
        """
        self._series_levels = []

        levels = declared_levels(self._trace)
        grid = _grid(self._trace)
        if levels is None or grid is None:
            return []

        x, y, z = grid
        try:
            from contourpy import contour_generator

            generator = contour_generator(
                x=x, y=y, z=z, name=_CURVE_ALGORITHM, line_type="SeparateCode"
            )
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

        data: list[list[dict]] = []
        for index, level in enumerate(levels):
            curves, _ = generator.lines(level)
            for curve in curves:
                data.append(
                    [
                        {
                            MaidrKey.X: float(vertex[0]),
                            MaidrKey.Y: float(vertex[1]),
                            MaidrKey.LEVEL: level,
                        }
                        for vertex in curve
                    ]
                )
                self._series_levels.append(index)

        return data

    def _get_selector(self) -> list[str]:
        """Return one selector per emitted series, or none for the whole layer.

        Plotly gives every declared level a ``g.contourlevel`` -- including the
        ones the field never reaches, which get the group and no ``path`` --
        and one ``<path>`` per disjoint curve inside it. The **level** is
        therefore addressable: the groups run in the declared order, measured
        on every figure below.

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


def declared_levels(trace: dict) -> list[float] | None:
    """Return the levels the author asked for, or None when plotly picks them.

    Plotly steps ``start``, ``start + size``, ... while the level is below
    ``end + size / 10``, and swaps ``start`` and ``end`` when they arrive the
    wrong way round. Accumulated rather than computed as ``start + k * size``
    so the announced level is bit-for-bit the one plotly drew: with
    ``start=0.2, size=0.2`` both routes agree on 0.4 and disagree on the
    third level, and the level is also what is handed to the curve tracer.

    None is returned -- the layer declines -- whenever plotly would choose the
    levels itself, because the rule it chooses them by lives in plotly.js and
    could not be reproduced here: measured across nine fields, eight fit
    "round ``(max - min) / 15`` up to a 1/2/5x10ⁿ step", and a field spanning
    ``0 .. 3`` does not. So a trace that leaves any of ``start``, ``end`` or
    ``size`` out, that sets ``size`` to zero (plotly replaces it), or that
    sets ``autocontour: True`` (which overrides an explicit spec -- measured)
    is left unread rather than read at levels the chart does not draw. See
    #642.
    """
    contours = trace.get("contours")
    if not isinstance(contours, dict):
        return None
    if trace.get("autocontour") is True:
        return None
    # A constraint contour draws one curve at `value` and means "the region
    # where z is above it", which is a different chart from a set of levels;
    # it carries no start/end/size and so declines here anyway.
    if contours.get("type") not in (None, "levels"):
        return None

    start = _a_number(contours.get("start"))
    end = _a_number(contours.get("end"))
    size = _a_number(contours.get("size"))
    if start is None or end is None or size is None or size <= 0:
        return None

    low, high = (start, end) if start <= end else (end, start)
    limit = high + size / _END_TOLERANCE
    if (high - low) / size > _LEVEL_LIMIT:
        return None

    levels = []
    level = low
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
