"""Build MAIDR layers from the glyph renderers of one Bokeh ``Plot``.

Each supported glyph maps onto the layer type the matplotlib and Plotly
paths already emit for the same chart, with the same data shape:

==========================================  ==================
Bokeh                                       MAIDR layer
==========================================  ==================
``vbar`` / ``hbar``                         ``bar``
``vbar_stack`` / ``hbar_stack``             ``stacked_bar``
``vbar`` with ``dodge()``, nested factors   ``dodged_bar``
``quad``                                    ``hist``
``line`` / ``multi_line``                   ``line`` (one row per series)
``step``                                    ``step``
``scatter`` / ``circle``                    ``point``
``rect`` coloured through a colour mapper   ``heat``
``varea`` / ``varea_stack``                 ``area`` / ``stacked_area``
``harea`` / ``harea_stack``                 ``area`` / ``stacked_area``
``wedge`` / ``annular_wedge``               ``pie``
``segment`` + ``vbar`` on a date axis (OHLC)  ``candlestick``
``hbar`` spanning dates (``left``/``right``)  ``gantt``
``hex_tile`` coloured through a mapper      ``hexbin``
``image`` (a 2-D array and a colour mapper)  ``heat``
==========================================  ==================

Anything else is skipped with a warning naming the glyph.

Every layer also carries a *highlight* entry: where, in the Bokeh document,
the mark MAIDR is announcing lives. Bokeh draws to a ``<canvas>``, so the
CSS selectors the SVG paths use cannot reach it; the page instead answers
MAIDR's ``onNavigate`` callback by selecting that row of the renderer's data
source, or by moving a cursor glyph onto it. See
:mod:`maidr.bokeh.bokeh_maidr` for the page side. The entry is keyed by the
row and column MAIDR reports, which for every type but ``heat`` are the
row and column of the emitted ``data``.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from numbers import Number
from typing import Any, Callable

import numpy as np

from maidr.bokeh.data import (
    UnreadableSpec,
    dates_to_iso,
    epoch_ms_to_iso,
    factor_label,
    is_missing,
    is_temporal,
    resolve,
    source_length,
    spec_expression,
    spec_field,
    spec_transform,
    to_coordinate,
    to_native,
    visible_indices,
)
from maidr.bokeh.utils import warn
from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.histogram import HistPlot

#: Bokeh's ``Step.mode`` in MAIDR's ``stepDirection`` vocabulary. ``after``
#: holds each value until the next sample, as matplotlib's ``steps-post``
#: does; ``before`` jumps first, as ``steps-pre`` does.
_STEP_DIRECTIONS = {"after": "hv", "before": "vh", "center": "mid"}

#: How a Gantt layer's x axis spells a position -- days or hours since the
#: epoch, see ``PlotReader._gantt`` -- back as the date it stands for. A
#: ``format.function`` body, which the core compiles with ``new Function``.
_DATE_FORMATS = {
    "days": "return new Date(value * 864e5).toISOString().slice(0, 10);",
    "hours": (
        "var t = new Date(value * 36e5).toISOString();"
        " return t.slice(0, 10) + ' ' + t.slice(11, 16);"
    ),
}

#: The most cells of an ``image`` read as a heatmap. Past it, a picture is
#: one no reader can walk cell by cell, and the payload would outweigh it.
_IMAGE_CELL_LIMIT = 10_000

#: Where an ``Image`` ``anchor`` puts the ``x``/``y`` it is placed at, as
#: fractions of its width from the left and of its height from the bottom.
_ANCHOR_X = {"left": 0.0, "right": 1.0}
_ANCHOR_Y = {"bottom": 0.0, "top": 1.0}

#: The glyphs read as the slices of a pie: ``annular_wedge`` is a donut's.
_WEDGE_GLYPHS = frozenset({"Wedge", "AnnularWedge"})

#: The glyphs read as a point cloud. Bokeh 3.4 folded the per-marker glyph
#: classes (``Asterisk``, ``Diamond``, ...) into ``Scatter``; ``Circle``
#: survives as the radius-sized dot.
_SCATTER_GLYPHS = frozenset({"Scatter", "Circle"})


@dataclass
class BokehLayer:
    """
    One MAIDR layer and where its marks live in the Bokeh document.

    Attributes
    ----------
    schema : dict
        The MAIDR layer schema.
    plot : bokeh.models.Plot
        The plot the layer was read from.
    highlight : dict or None
        How the page highlights the current mark: ``{"kind": "select",
        "grid": ...}`` or ``{"kind": "points", "points": ...}`` naming
        ``[renderer id, source row]`` pairs, or ``{"kind": "cursor"}`` with
        a ``grid`` or ``points`` naming ``[x, y]`` data coordinates for a
        cursor glyph instead. A layer the core reports by column alone --
        a candlestick -- has ``columns`` in place of ``grid``: per column,
        the list of cells to highlight together.
    x_range_name, y_range_name : str
        The ranges a cursor for this layer must be placed on.
    renderers : list of bokeh.models.GlyphRenderer
        The renderers the layer was read from.
    """

    schema: dict
    plot: Any
    highlight: dict | None = None
    x_range_name: str = "default"
    y_range_name: str = "default"
    renderers: list = field(default_factory=list)


@dataclass
class _Candles:
    """
    A candlestick recognised across renderers, read once.

    Attributes
    ----------
    candles : list of dict
        One ``{value, open, high, low, close[, volume]}`` per candle, by date.
    cells : list of list
        Per candle, the ``[renderer id, source row]`` of its wick and body.
    bodies : list of bokeh.models.GlyphRenderer
        The ``vbar`` renderers the bodies came from.
    bodiless : int
        How many wicks had no body and were left out.
    """

    candles: list
    cells: list
    bodies: list
    bodiless: int = 0


class PlotReader:
    """
    Read one Bokeh ``Plot`` into MAIDR layers.

    Parameters
    ----------
    plot : bokeh.models.Plot
        The plot, usually made by ``bokeh.plotting.figure``.
    """

    def __init__(self, plot: Any) -> None:
        from bokeh.models import DatetimeAxis

        self._plot = plot
        x_axes = list(plot.below) + list(plot.above)
        y_axes = list(plot.left) + list(plot.right)
        self._x_axis = next((a for a in x_axes if _is_axis(a)), None)
        self._y_axis = next((a for a in y_axes if _is_axis(a)), None)
        self._x_dates = isinstance(self._x_axis, DatetimeAxis)
        self._y_dates = isinstance(self._y_axis, DatetimeAxis)
        legend = _legend(plot)
        self._legend_labels, self._legend_rows, self._legend_fields = legend[:3]
        self._legend_title = legend[3]
        #: Renderer id to the candlestick it is part of, and what each
        #: candlestick read as; see :meth:`_find_candlesticks`.
        self._candle_keys: dict[str, tuple] = {}
        self._candle_reads: dict[tuple, _Candles] = {}

    # ------------------------------------------------------------------ #
    #  Plot-level reading                                                  #
    # ------------------------------------------------------------------ #

    @property
    def title(self) -> str:
        """The plot's title text, or ``""``."""
        title = getattr(self._plot, "title", None)
        text = getattr(title, "text", title)
        return str(text or "").strip()

    def _axes(self, z_label: str | None = None) -> dict:
        """The canonical per-axis payload, with ``z`` only when given."""
        axes = {
            MaidrKey.X: {MaidrKey.LABEL: _axis_label(self._x_axis, "X")},
            MaidrKey.Y: {MaidrKey.LABEL: _axis_label(self._y_axis, "Y")},
        }
        if z_label:
            axes[MaidrKey.Z] = {MaidrKey.LABEL: z_label}
        return axes

    def _series_label(self, renderer: Any) -> str | None:
        """What the legend calls a renderer, else its ``name``."""
        label = self._legend_labels.get(renderer.id)
        if label:
            return label
        if any(rid == renderer.id for rid, _ in self._legend_rows):
            # A grouped legend names rows, not the renderer; the renderer's
            # ``name`` would be a guess at which of them it is.
            return None
        name = getattr(renderer, "name", None)
        return str(name) if name else None

    def _schema(
        self, plot_type: PlotType, data: Any, z_label: str | None = None
    ) -> dict:
        """A layer schema in the shape every other path emits."""
        return {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: plot_type,
            MaidrKey.TITLE: self.title,
            MaidrKey.AXES: self._axes(z_label),
            MaidrKey.DATA: data,
        }

    def _x_native(self, values: list) -> list:
        """x values as announced: dates spelled ISO on a datetime axis."""
        return _announced(values, self._x_dates)

    def _y_native(self, values: list) -> list:
        """y values as announced: dates spelled ISO on a datetime axis."""
        return _announced(values, self._y_dates)

    # ------------------------------------------------------------------ #
    #  Grouping renderers into layers                                      #
    # ------------------------------------------------------------------ #

    def layers(self) -> list[BokehLayer]:
        """
        Every layer this plot yields, in the order its renderers were added.

        Returns
        -------
        list of BokehLayer
            The layers; empty when nothing on the plot is supported.
        """
        from bokeh.models import ColumnDataSource, GlyphRenderer

        readable = []
        for renderer in self._plot.renderers:
            if not getattr(renderer, "visible", True):
                continue
            if not isinstance(renderer, GlyphRenderer):
                warn(
                    f"maidr does not read Bokeh {type(renderer).__name__} "
                    "renderers; it is left out of the accessible chart."
                )
                continue
            if not isinstance(renderer.data_source, ColumnDataSource):
                warn(
                    f"maidr cannot read a {type(renderer.data_source).__name__}, "
                    "which loads its data in the browser; the "
                    f"{type(renderer.glyph).__name__} glyph using it is left out."
                )
                continue
            readable.append(renderer)

        # A candlestick is several renderers that only mean OHLC together,
        # so it is recognised across the plot before anything is grouped.
        self._find_candlesticks(readable)
        groups: dict[tuple, list] = {}
        for renderer in readable:
            try:
                key = self._group_key(renderer)
            except Exception as reason:
                # Grouping reads the glyph's columns too, so it needs the same
                # boundary the builders below have: one renderer maidr cannot
                # read costs that renderer, never the whole chart.
                warn(
                    f"maidr cannot read the Bokeh {type(renderer.glyph).__name__} "
                    f"glyph ({_reason(reason)}); it is left out of the "
                    "accessible chart."
                )
                continue
            if key is None:
                warn(
                    f"maidr does not support Bokeh {type(renderer.glyph).__name__} "
                    "glyphs yet; it is left out of the accessible chart."
                )
                continue
            groups.setdefault(key, []).append(renderer)

        builders: dict[str, Callable[[list], BokehLayer | None]] = {
            "bar": self._bar,
            "stacked": self._stacked,
            "dodged": self._dodged,
            "nested": self._nested,
            "hist": self._hist,
            "line": self._line,
            "step": self._step,
            "scatter": self._scatter,
            "heat": self._heat,
            "area": self._area,
            "stacked_area": self._stacked_area,
            "pie": self._pie,
            "candlestick": self._candlestick,
            "gantt": self._gantt,
            "hexbin": self._hexbin,
            "image": self._image,
        }
        layers: list[BokehLayer] = []
        for key, renderers in groups.items():
            try:
                layer = builders[key[0]](renderers)
            except Exception as reason:
                # Any failure, not only an `UnreadableSpec`: one glyph maidr
                # misreads must cost that layer, never the whole chart --
                # the rest still reads, and the figure still draws.
                names = sorted({type(r.glyph).__name__ for r in renderers})
                warn(
                    f"maidr cannot read the Bokeh {', '.join(names)} glyph "
                    f"({_reason(reason)}); it is left out of the accessible chart."
                )
                continue
            if layer is not None:
                layer.x_range_name = renderers[0].x_range_name
                layer.y_range_name = renderers[0].y_range_name
                layer.renderers = list(renderers)
                layers.append(layer)
        return layers

    def _group_key(self, renderer: Any) -> tuple | None:
        """Which layer a renderer belongs to, or ``None`` if unsupported."""
        from bokeh.models import CumSum, Stack

        if renderer.id in self._candle_keys:
            return self._candle_keys[renderer.id]
        glyph = renderer.glyph
        name = type(glyph).__name__
        if name in ("VBar", "HBar"):
            value_prop, position_prop = (
                ("top", "x") if name == "VBar" else ("right", "y")
            )
            ranges = (renderer.x_range_name, renderer.y_range_name)
            offset = _offset(renderer, position_prop)
            if isinstance(spec_expression(glyph, value_prop), (Stack, CumSum)):
                # Each ``vbar_stack`` call is one stack; two of them dodged
                # side by side are two stacks, and read as one they would be
                # announced a total no bar is drawn at.
                return ("stacked", name, *ranges, offset)
            if offset is not None:
                return ("dodged", name, *ranges)
            if name == "HBar" and self._spans_dates(renderer):
                return ("gantt", *ranges)
            data = renderer.data_source.data
            try:
                positions = resolve(glyph, position_prop, data)
            except UnreadableSpec:
                positions = []
            if any(_is_nested(_split_offset(p)[0]) for p in positions):
                return ("nested", renderer.id)
            return ("bar", renderer.id)
        if name == "Quad":
            return ("hist", renderer.id)
        if name in ("Line", "MultiLine"):
            return ("line", renderer.x_range_name, renderer.y_range_name)
        if name == "Step":
            return ("step", glyph.mode, renderer.x_range_name, renderer.y_range_name)
        if name in _SCATTER_GLYPHS:
            return ("scatter", renderer.id)
        if name == "Rect" and _is_continuous(_color_mapper(glyph)):
            # A categorical mapper colours cells by a label, which is not a
            # value a heatmap can announce or sonify.
            return ("heat", renderer.id)
        if name == "HexTile":
            return ("hexbin", renderer.id)
        if name == "Image":
            return ("image", renderer.id)
        if name in ("VArea", "HArea"):
            edge = "y2" if name == "VArea" else "x2"
            if isinstance(spec_expression(glyph, edge), (Stack, CumSum)):
                ranges = (renderer.x_range_name, renderer.y_range_name)
                return ("stacked_area", name, *ranges)
            return ("area", renderer.id)
        if name in _WEDGE_GLYPHS:
            # Wedges drawn round one centre are one pie, however many calls
            # drew them -- one ``wedge`` per slice is a common spelling.
            centre = _constant_centre(renderer)
            if centre is None:
                return ("pie", renderer.id)
            return ("pie", renderer.x_range_name, renderer.y_range_name, centre)
        return None

    # ------------------------------------------------------------------ #
    #  Bars                                                                #
    # ------------------------------------------------------------------ #

    def _bar_values(
        self, renderer: Any
    ) -> tuple[bool, list[tuple[Any, Any, int]]]:
        """
        One bar per drawn row: ``(position, magnitude, source row)``.

        The magnitude is the bar's extent, ``top - bottom`` (``right - left``
        for ``hbar``), so a bar that does not start at zero is read as the
        length it is drawn at -- as a matplotlib patch's height is.

        Returns
        -------
        tuple of (bool, list)
            Whether the bars are horizontal, and the bars in drawn order.
        """
        glyph = renderer.glyph
        horizontal = type(glyph).__name__ == "HBar"
        data = renderer.data_source.data
        position_prop, low_prop, high_prop = (
            ("y", "left", "right") if horizontal else ("x", "bottom", "top")
        )
        positions = resolve(glyph, position_prop, data)
        highs = resolve(glyph, high_prop, data)
        lows = resolve(glyph, low_prop, data)
        bars = []
        for index in visible_indices(renderer, source_length(data)):
            position = _split_offset(positions[index])[0]
            if is_missing(position):
                continue
            bars.append((position, _extent(lows[index], highs[index]), index))
        category_range = self._plot.y_range if horizontal else self._plot.x_range
        return horizontal, _in_drawn_order(bars, category_range)

    def _bar_point(
        self, horizontal: bool, position: Any, value: Any, z: Any = None
    ) -> dict:
        """One bar, its magnitude in ``x`` when it is horizontal."""
        category = self._position_native(position, horizontal)
        magnitude = to_native(value)
        x, y = (magnitude, category) if horizontal else (category, magnitude)
        if z is None:
            return {MaidrKey.X: x, MaidrKey.Y: y}
        return {MaidrKey.X: x, MaidrKey.Z: z, MaidrKey.Y: y}

    def _position_native(self, position: Any, horizontal: bool) -> Any:
        """A bar's category as announced: a factor's label, or a date/number."""
        if isinstance(position, str) or isinstance(position, (list, tuple)):
            return factor_label(position)
        dates = self._y_dates if horizontal else self._x_dates
        return _announced([position], dates)[0]

    def _bar(self, renderers: list) -> BokehLayer | None:
        """
        One ``vbar`` or ``hbar`` renderer, read as a bar layer.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The renderers grouped into this layer.

        Returns
        -------
        BokehLayer or None
            The layer, or ``None`` when nothing is drawn.
        """
        renderer = renderers[0]
        horizontal, bars = self._bar_values(renderer)
        if not bars:
            return None
        data = [self._bar_point(horizontal, pos, value) for pos, value, _ in bars]
        schema = self._schema(PlotType.BAR, data)
        schema[MaidrKey.ORIENTATION] = "horz" if horizontal else "vert"
        name = self._series_label(renderer)
        if name:
            schema[MaidrKey.NAME] = name
        grid = [[[renderer.id, index] for _, _, index in bars]]
        return BokehLayer(schema, self._plot, {"kind": "select", "grid": grid})

    def _segmented(
        self, renderers: list, plot_type: PlotType
    ) -> BokehLayer | None:
        """
        One row per renderer, aligned on the categories they share.

        ``vbar_stack`` gives every segment the same source and the same
        category column, but nothing obliges a hand-built stack to, so the
        rows are aligned by category rather than by source row. A category a
        series does not draw is emitted as ``None``, which the core reads as
        a gap rather than a zero.
        """
        horizontal = type(renderers[0].glyph).__name__ == "HBar"
        series = []
        categories: dict = {}
        for renderer in renderers:
            _, bars = self._bar_values(renderer)
            by_category: dict = {}
            for position, value, index in bars:
                key = _factor_key(position)
                if key in by_category:
                    # One row per category is what makes a series; a second
                    # bar there would be dropped without a word.
                    label = factor_label(position)
                    raise UnreadableSpec(
                        f"one series draws more than one bar at {label!r}"
                    )
                by_category[key] = (position, value, index)
                categories.setdefault(key, (position, None, 0))
            series.append((renderer, by_category))
        category_range = self._plot.y_range if horizontal else self._plot.x_range
        drawn = _in_drawn_order(list(categories.values()), category_range)
        categories_in_order = [position for position, _, _ in drawn]
        if not categories_in_order:
            return None

        data: list[list[dict]] = []
        grid: list[list] = []
        for number, (renderer, by_category) in enumerate(series):
            label = self._series_label(renderer) or f"Series {number + 1}"
            row, cells = [], []
            for category in categories_in_order:
                entry = by_category.get(_factor_key(category))
                value = entry[1] if entry else None
                row.append(self._bar_point(horizontal, category, value, z=label))
                cells.append([renderer.id, entry[2]] if entry else None)
            data.append(row)
            grid.append(cells)

        schema = self._schema(plot_type, data, self._legend_title)
        schema[MaidrKey.ORIENTATION] = "horz" if horizontal else "vert"
        return BokehLayer(schema, self._plot, {"kind": "select", "grid": grid})

    def _stacked(self, renderers: list) -> BokehLayer | None:
        """
        The segments of a ``vbar_stack`` or ``hbar_stack``, as a stacked bar.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The renderers grouped into this layer.

        Returns
        -------
        BokehLayer or None
            The layer, or ``None`` when nothing is drawn.
        """
        return self._segmented(renderers, PlotType.STACKED)

    def _dodged(self, renderers: list) -> BokehLayer | None:
        """
        Bars placed side by side by an offset, read as a dodged group.

        Left to right, the way the groups are drawn: the offsets -- given by
        ``dodge()`` or spelled into the coordinates as ``("a", -0.2)`` --
        are what place them, whatever order the renderers were added in.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The offset ``vbar`` or ``hbar`` renderers of one plot.

        Returns
        -------
        BokehLayer or None
            The ``dodged_bar`` layer, or ``None`` when nothing is drawn.
        """
        prop = "y" if type(renderers[0].glyph).__name__ == "HBar" else "x"
        ordered = sorted(renderers, key=lambda r: _offset(r, prop) or 0.0)
        return self._segmented(ordered, PlotType.DODGED)

    def _nested(self, renderers: list) -> BokehLayer | None:
        """
        Bars on a nested ``FactorRange``, read as a dodged group.

        ``x=[("Apples", "2015"), ("Apples", "2016"), ...]`` draws each
        outer factor as a group and each inner factor as a bar within it --
        a dodged bar chart spelled through the axis rather than through
        ``dodge()``. The innermost level names the series and the levels
        above it the category. A grid with a hole in it cannot be a
        rectangular dodged layer, so it falls back to plain bars labelled
        with the whole factor.
        """
        renderer = renderers[0]
        horizontal, bars = self._bar_values(renderer)
        categories: list = []
        groups: list = []
        cells: dict = {}
        for position, value, index in bars:
            outer, inner = tuple(position[:-1]), position[-1]
            if outer not in categories:
                categories.append(outer)
            if inner not in groups:
                groups.append(inner)
            cells.setdefault((outer, inner), (value, index))
        if len(cells) != len(categories) * len(groups):
            return self._bar(renderers)

        data, grid = [], []
        for inner in groups:
            row, row_cells = [], []
            for outer in categories:
                value, index = cells[(outer, inner)]
                row.append(
                    self._bar_point(horizontal, list(outer), value, z=str(inner))
                )
                row_cells.append([renderer.id, index])
            data.append(row)
            grid.append(row_cells)
        schema = self._schema(PlotType.DODGED, data, self._legend_title)
        schema[MaidrKey.ORIENTATION] = "horz" if horizontal else "vert"
        return BokehLayer(schema, self._plot, {"kind": "select", "grid": grid})

    # ------------------------------------------------------------------ #
    #  Histogram                                                           #
    # ------------------------------------------------------------------ #

    def _hist(self, renderers: list) -> BokehLayer | None:
        """
        A ``quad`` per bin, read as a histogram.

        The bins run along whichever axis the quads vary on: ``left``/
        ``right`` for the usual vertical histogram, ``bottom``/``top`` for a
        sideways one, recognised by every quad sharing one ``left``. Each
        point is built by the matplotlib histogram's own
        :meth:`~maidr.core.plot.histogram.HistPlot._bin_point`, so the
        two paths emit one shape.
        """
        renderer = renderers[0]
        glyph = renderer.glyph
        data = renderer.data_source.data
        left, right = resolve(glyph, "left", data), resolve(glyph, "right", data)
        bottom, top = resolve(glyph, "bottom", data), resolve(glyph, "top", data)
        rows = visible_indices(renderer, source_length(data))
        if not rows:
            return None
        horizontal = len({to_native(left[i]) for i in rows}) == 1 and len(
            {to_native(bottom[i]) for i in rows}
        ) > 1
        start, end = (bottom, top) if horizontal else (left, right)
        low, high = (left, right) if horizontal else (bottom, top)
        dates = self._y_dates if horizontal else self._x_dates
        if dates or is_temporal([start[i] for i in rows]):
            # On a ``DatetimeAxis`` plain numbers are epoch milliseconds --
            # the usual way to bin dates with ``np.histogram`` -- and are
            # announced as the dates they are.
            return self._date_bins(renderer, horizontal, start, low, high, rows)
        bins = []
        for index in rows:
            if is_missing(start[index]) or is_missing(end[index]):
                continue
            edge = float(min(start[index], end[index]))
            size = abs(float(end[index]) - float(start[index]))
            bins.append((edge, size, _extent(low[index], high[index]), index))
        if not bins:
            return None
        bins.sort(key=lambda b: b[0])
        orientation = "horz" if horizontal else "vert"
        points = [
            HistPlot._bin_point(orientation, edge, size, count)
            for edge, size, count, _ in bins
        ]
        schema = self._schema(PlotType.HIST, points)
        schema[MaidrKey.ORIENTATION] = orientation
        name = self._series_label(renderer)
        if name:
            schema[MaidrKey.NAME] = name
        grid = [[[renderer.id, index] for *_, index in bins]]
        return BokehLayer(schema, self._plot, {"kind": "select", "grid": grid})

    def _date_bins(
        self,
        renderer: Any,
        horizontal: bool,
        start: list,
        low: list,
        high: list,
        rows: list[int],
    ) -> BokehLayer | None:
        """
        ``quad`` bins on a date axis, read as bars named by their start date.

        A histogram point carries its edges as numbers (``xMin``/``xMax``),
        and a date has none the reader would recognise, so each bin is
        announced as a bar at the date it starts on instead -- "2020-01-01,
        3" rather than an epoch.

        Parameters
        ----------
        renderer : bokeh.models.GlyphRenderer
            The ``quad`` renderer.
        horizontal : bool
            Whether the bins run up the y axis.
        start, low, high : list
            The column each bin starts at, and the two that bound its count.
        rows : list of int
            The source rows the renderer draws.

        Returns
        -------
        BokehLayer or None
            The layer, or ``None`` when no bin has a start date.
        """
        bins = [
            (start[i], _extent(low[i], high[i]), i)
            for i in rows
            if not is_missing(start[i])
        ]
        if not bins:
            return None
        bins.sort(key=lambda b: to_native(b[0]))
        data = [self._bar_point(horizontal, date, count) for date, count, _ in bins]
        schema = self._schema(PlotType.BAR, data)
        schema[MaidrKey.ORIENTATION] = "horz" if horizontal else "vert"
        name = self._series_label(renderer)
        if name:
            schema[MaidrKey.NAME] = name
        grid = [[[renderer.id, index] for *_, index in bins]]
        return BokehLayer(schema, self._plot, {"kind": "select", "grid": grid})

    # ------------------------------------------------------------------ #
    #  Lines, steps and areas                                             #
    # ------------------------------------------------------------------ #

    def _series(self, renderer: Any) -> list[tuple[list, list, str | None]]:
        """
        The series a line-like renderer draws: ``(xs, ys, label)`` each.

        A ``Line`` is one series over its whole source -- Bokeh draws a
        connected glyph through every row and ignores a view's filter for
        it. A ``MultiLine`` is one series per row, labelled by the legend
        column when its legend is grouped by one.
        """
        glyph = renderer.glyph
        data = renderer.data_source.data
        label = self._series_label(renderer)
        if type(glyph).__name__ == "MultiLine":
            xs, ys = resolve(glyph, "xs", data), resolve(glyph, "ys", data)
            names = resolve_column(data, self._legend_fields.get(renderer.id))
            out = []
            for index in visible_indices(renderer, source_length(data)):
                name = self._legend_rows.get((renderer.id, index))
                if name is None:
                    name = names[index] if names else label
                out.append((list(xs[index]), list(ys[index]), _label(name)))
            return out
        return [(resolve(glyph, "x", data), resolve(glyph, "y", data), label)]

    def _line_like(self, renderers: list) -> tuple[list[list[dict]], list[list]]:
        """The rows of a line-shaped layer and the cursor coordinates for it."""
        rows, grid = [], []
        for renderer in renderers:
            for xs, ys, label in self._series(renderer):
                read = self._numeric_series(xs, ys, label)
                if read is not None:
                    row, coords = read
                    if row:
                        rows.append(row)
                        grid.append(coords)
                    continue
                row, coords = [], []
                announced_x = self._x_native(xs)
                announced_y = self._y_native(ys)
                for x, y, ax, ay in zip(xs, ys, announced_x, announced_y):
                    # A sample with no position is nowhere to send a reader,
                    # so it is dropped; one with no value is a gap the core
                    # keeps as ``null``, as the matplotlib line path does.
                    if is_missing(x):
                        continue
                    point = {MaidrKey.X: ax, MaidrKey.Y: ay}
                    if label:
                        point[MaidrKey.Z] = label
                    row.append(point)
                    at = None if is_missing(y) else [to_coordinate(x), to_coordinate(y)]
                    coords.append(at)
                if row:
                    rows.append(row)
                    grid.append(coords)
        return rows, grid

    def _numeric_series(
        self, xs: list, ys: list, label: str | None
    ) -> tuple[list[dict], list] | None:
        """
        One series of plain numbers on two numeric axes, read a column at a time.

        The same points and cursor coordinates the per-sample loop in
        :meth:`_line_like` makes, for the columns where every step of it is
        known in advance: :func:`_plain_numbers` reads which values are
        missing and how each is announced for a whole column at once, and
        :func:`to_coordinate` places a plain number where :func:`to_native`
        announces it. That loop called :func:`is_missing`,
        :func:`to_native` and :func:`to_coordinate` on every sample, and on a
        long series those calls were most of the render.

        The points are keyed by the plain strings ``MaidrKey`` members stand
        for. The JSON is the same, and a dict keyed by an enum member is one
        the garbage collector has to track -- one per sample here.

        Parameters
        ----------
        xs, ys : list
            The series' columns, as :meth:`_series` reads them.
        label : str or None
            The series' name, carried on every point when it has one.

        Returns
        -------
        tuple of (list of dict, list) or None
            The series' points and the cursor coordinates for them, or
            ``None`` when either axis is a ``DatetimeAxis`` or either
            column is anything but plain numbers -- which keeps the
            per-sample reading.
        """
        x = None if self._x_dates else _plain_numbers(xs)
        y = None if self._y_dates else _plain_numbers(ys)
        if x is None or y is None:
            return None
        (x_gaps, x_values), (y_gaps, y_values) = x, y
        # A sample with no position is dropped, and one with no value is a
        # gap the core keeps as ``null`` -- as the per-sample loop does.
        samples = [
            (ax, ay, y_gap)
            for ax, ay, x_gap, y_gap in zip(x_values, y_values, x_gaps, y_gaps)
            if not x_gap
        ]
        kx, ky, kz = MaidrKey.X.value, MaidrKey.Y.value, MaidrKey.Z.value
        if label:
            row = [{kx: ax, ky: ay, kz: label} for ax, ay, _ in samples]
        else:
            row = [{kx: ax, ky: ay} for ax, ay, _ in samples]
        coords = [None if y_gap else [ax, ay] for ax, ay, y_gap in samples]
        return row, coords

    def _line(self, renderers: list) -> BokehLayer | None:
        """
        Every ``line``/``multi_line`` on a pair of ranges, one row per series.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The renderers grouped into this layer.

        Returns
        -------
        BokehLayer or None
            The layer, or ``None`` when nothing is drawn.
        """
        rows, grid = self._line_like(renderers)
        if not rows:
            return None
        schema = self._schema(PlotType.LINE, rows, self._legend_title)
        return BokehLayer(schema, self._plot, {"kind": "cursor", "grid": grid})

    def _step(self, renderers: list) -> BokehLayer | None:
        """
        Every ``step`` of one mode on a pair of ranges, one row per series.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The renderers grouped into this layer.

        Returns
        -------
        BokehLayer or None
            The layer, or ``None`` when nothing is drawn.
        """
        rows, grid = self._line_like(renderers)
        if not rows:
            return None
        schema = self._schema(PlotType.STEP, rows, self._legend_title)
        direction = _STEP_DIRECTIONS.get(renderers[0].glyph.mode)
        if direction:
            schema[MaidrKey.STEP_DIRECTION] = direction
        return BokehLayer(schema, self._plot, {"kind": "cursor", "grid": grid})

    def _bands(self, renderers: list) -> tuple[list[list[dict]], list[list]]:
        """
        One band per ``varea``: its own thickness at each x, and its top edge.

        A stacked band's ``y1``/``y2`` are the running totals below and
        above it, so ``y2 - y1`` is the series' own value -- what the core's
        area trace expects, since it does the stacking itself. The cursor
        sits on the top edge, where the band is drawn.

        An ``harea`` is the same band on its side -- ``x1``/``x2`` at each
        ``y`` -- and is read into the same fields, its positions in ``x``
        and its thicknesses in ``y``: the core steps along an area's ``x``
        and sonifies its ``y``, and ``orientation`` is not read for an area.
        :meth:`_area_schema` swaps the axis titles to match, as the
        matplotlib path does for ``fill_betweenx``. The cursor sits on the
        band's right edge.
        """
        rows, grid = [], []
        for renderer in renderers:
            glyph = renderer.glyph
            data = renderer.data_source.data
            sideways = type(glyph).__name__ == "HArea"
            position, low_prop, high_prop = (
                ("y", "x1", "x2") if sideways else ("x", "y1", "y2")
            )
            positions = resolve(glyph, position, data)
            lows = resolve(glyph, low_prop, data)
            highs = resolve(glyph, high_prop, data)
            label = self._series_label(renderer)
            announced = (
                self._y_native(positions) if sideways else self._x_native(positions)
            )
            row, coords = [], []
            for at, spoken, low, high in zip(positions, announced, lows, highs):
                if is_missing(at):
                    continue
                point = {MaidrKey.X: spoken, MaidrKey.Y: to_native(_extent(low, high))}
                if label:
                    point[MaidrKey.Z] = label
                row.append(point)
                edge = None if is_missing(high) else to_coordinate(high)
                if edge is None:
                    coords.append(None)
                elif sideways:
                    coords.append([edge, to_coordinate(at)])
                else:
                    coords.append([to_coordinate(at), edge])
            if row:
                rows.append(row)
                grid.append(coords)
        return rows, grid

    def _area_schema(
        self, renderers: list, plot_type: PlotType, rows: list, z_label: str | None
    ) -> dict:
        """
        An area layer's schema, its axis titles swapped for an ``harea``.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The band renderers.
        plot_type : PlotType
            ``AREA`` or ``STACKED_AREA``.
        rows : list of list of dict
            The bands, from :meth:`_bands`.
        z_label : str or None
            The legend title, for a stacked area.

        Returns
        -------
        dict
            The layer schema; see :meth:`_bands` for the swap.
        """
        schema = self._schema(plot_type, rows, z_label)
        if type(renderers[0].glyph).__name__ == "HArea":
            axes = schema[MaidrKey.AXES]
            axes[MaidrKey.X], axes[MaidrKey.Y] = axes[MaidrKey.Y], axes[MaidrKey.X]
        return schema

    def _area(self, renderers: list) -> BokehLayer | None:
        """
        One ``varea`` or ``harea``, read as an area layer.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The renderers grouped into this layer.

        Returns
        -------
        BokehLayer or None
            The layer, or ``None`` when nothing is drawn.
        """
        rows, grid = self._bands(renderers)
        if not rows:
            return None
        schema = self._area_schema(renderers, PlotType.AREA, rows, None)
        return BokehLayer(schema, self._plot, {"kind": "cursor", "grid": grid})

    def _stacked_area(self, renderers: list) -> BokehLayer | None:
        """
        The bands of a ``varea_stack`` or ``harea_stack``, as a stacked area.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The renderers grouped into this layer.

        Returns
        -------
        BokehLayer or None
            The layer, or ``None`` when nothing is drawn.
        """
        rows, grid = self._bands(renderers)
        if not rows:
            return None
        plot_type = PlotType.STACKED_AREA if len(rows) > 1 else PlotType.AREA
        schema = self._area_schema(renderers, plot_type, rows, self._legend_title)
        return BokehLayer(schema, self._plot, {"kind": "cursor", "grid": grid})

    # ------------------------------------------------------------------ #
    #  Pie                                                                 #
    # ------------------------------------------------------------------ #

    def _pie(self, renderers: list) -> BokehLayer | None:
        """
        Wedges round one centre, read as a pie walked clockwise.

        MAIDR walks a pie clockwise from ``startAngle``, measured clockwise
        from 12 o'clock. Bokeh measures angles the other way --
        counterclockwise from 3 o'clock -- and draws ``anticlock`` by
        default, so the usual ``cumsum("angle", include_zero=True)`` pie
        runs counterclockwise from 3 o'clock. The slices are therefore
        emitted in the order they sit clockwise round the dial, starting
        where the first drawn slice starts, as the matplotlib path emits a
        ``counterclock`` pie: reversed, with ``startAngle`` on that edge.
        No ``direction`` is declared, so ``data`` is already the walk and
        the highlight grid is keyed the same way.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The ``wedge``/``annular_wedge`` renderers grouped into this pie.

        Returns
        -------
        BokehLayer or None
            The ``pie`` layer, or ``None`` when no slice is drawn.
        """
        slices: list[tuple[float, Any, Any, int, int]] = []
        ring_start: float | None = None
        label_names: list[str] = []
        value_names: list[str] = []
        for renderer in renderers:
            glyph = renderer.glyph
            data = renderer.data_source.data
            rows = visible_indices(renderer, source_length(data))
            starts = _radians(glyph, "start_angle", data)
            ends = _radians(glyph, "end_angle", data)
            clockwise = glyph.direction == "clock"
            values, value_name = self._slice_values(
                renderer, rows, starts, ends, clockwise
            )
            labels, label_name = self._slice_labels(renderer, rows)
            if value_name:
                value_names.append(value_name)
            if label_name:
                label_names.append(label_name)
            for index in rows:
                if is_missing(starts[index]) or is_missing(ends[index]):
                    continue
                if is_missing(values[index]):
                    continue
                first_edge = _dial(starts[index])
                if ring_start is None:
                    ring_start = first_edge
                # Where the slice begins going clockwise: its drawn start
                # when Bokeh draws it clockwise, its drawn end otherwise.
                begins = first_edge if clockwise else _dial(ends[index])
                slices.append(
                    (begins, labels[index], values[index], renderer.id, index)
                )
        if not slices or ring_start is None:
            return None
        start = ring_start
        slices.sort(key=lambda s: round((s[0] - start) % 360, 6) % 360)

        data = []
        for number, (_, label, value, _, _) in enumerate(slices):
            name = _label(label) or f"Slice {number + 1}"
            data.append({MaidrKey.X: name, MaidrKey.Y: to_native(value)})
        schema = self._schema(PlotType.PIE, data)
        schema[MaidrKey.AXES] = {
            MaidrKey.X: {
                MaidrKey.LABEL: _axis_label(
                    self._x_axis, _only_name(label_names) or "Category"
                )
            },
            MaidrKey.Y: {
                MaidrKey.LABEL: _axis_label(
                    self._y_axis, _only_name(value_names) or "Value"
                )
            },
        }
        start_angle = _clean(start % 360)
        if start_angle:
            schema[MaidrKey.START_ANGLE] = start_angle
        grid = [[[rid, index] for *_, rid, index in slices]]
        return BokehLayer(schema, self._plot, {"kind": "select", "grid": grid})

    def _slice_values(
        self,
        renderer: Any,
        rows: list[int],
        starts: list,
        ends: list,
        clockwise: bool,
    ) -> tuple[list, str | None]:
        """
        What each slice of one wedge renderer stands for, and its name.

        The angles are rarely what the author supplied: Bokeh's own pie
        example computes ``angle = value / value.sum() * 2 * pi`` and draws
        ``cumsum("angle")``. So a numeric source column the sweeps are
        proportional to -- the first in source order, among those no glyph
        property reads -- is taken as the value. Failing that, the column a
        ``cumsum`` reads, and failing that the sweep in degrees. With a
        single slice every positive column is "proportional", so the search
        needs two.

        Returns
        -------
        tuple of (list, str or None)
            One value per source row (``None`` where undrawable), and the
            name of the column they came from, if any.
        """
        glyph = renderer.glyph
        data = renderer.data_source.data
        n = source_length(data)
        sweeps: list = [None] * n
        for index in rows:
            if is_missing(starts[index]) or is_missing(ends[index]):
                continue
            sweeps[index] = _sweep(starts[index], ends[index], clockwise)

        drawn = [i for i in rows if sweeps[i] is not None]
        if len(drawn) > 1:
            read = {spec_field(glyph, prop) for prop in glyph.dataspecs()}
            for prop in ("start_angle", "end_angle"):
                expression = spec_expression(glyph, prop)
                read.add(getattr(expression, "field", None))
            target = np.array([sweeps[i] for i in drawn], dtype=float)
            for name in data:
                if name in read:
                    continue
                raw = resolve_column(data, name) or []
                column = _numeric_column(raw)
                if column is None:
                    continue
                if _proportional(column[drawn], target):
                    return [to_native(v) for v in raw], str(name)

        fields = {
            getattr(spec_expression(glyph, prop), "field", None)
            for prop in ("start_angle", "end_angle")
        }
        if len(fields) == 1 and None not in fields:
            (field_name,) = fields
            column = resolve_column(data, field_name)
            if column is not None:
                return [to_native(v) for v in column], str(field_name)
        degrees = [None if s is None else _clean(math.degrees(s)) for s in sweeps]
        return degrees, "Angle (degrees)"

    def _slice_labels(self, renderer: Any, rows: list[int]) -> tuple[list, str | None]:
        """
        What each slice of one wedge renderer is called, and by which column.

        The legend names a slice the way a sighted reader matches it: by a
        ``legend_field`` column, a ``legend_group`` row, or a
        ``legend_label`` on a renderer drawing one slice. Without a legend
        the first column of text no glyph property reads -- a colour column
        is read by ``fill_color`` -- names them.

        Returns
        -------
        tuple of (list, str or None)
            One label per source row, ``None`` where there is none, and the
            column they came from, if any.
        """
        glyph = renderer.glyph
        data = renderer.data_source.data
        n = source_length(data)
        column_name = self._legend_fields.get(renderer.id)
        column = resolve_column(data, column_name)
        if column is not None:
            return column, column_name
        fixed = self._legend_labels.get(renderer.id)
        labels: list = [
            self._legend_rows.get((renderer.id, i), fixed) for i in range(n)
        ]
        if any(label is not None for label in labels):
            return labels, None
        read = {spec_field(glyph, prop) for prop in glyph.dataspecs()}
        for name in data:
            if name in read:
                continue
            values = resolve_column(data, name) or []
            if values and all(isinstance(values[i], str) for i in rows):
                return values, str(name)
        return [None] * n, None

    # ------------------------------------------------------------------ #
    #  Candlestick                                                         #
    # ------------------------------------------------------------------ #

    def _find_candlesticks(self, renderers: list) -> None:
        """
        Recognise the renderers Bokeh's OHLC recipe draws a candlestick with.

        Bokeh has no candlestick glyph. Its documented recipe draws one
        ``segment`` from each day's high to its low -- the wicks -- and one
        or two ``vbar`` renderers between open and close -- the bodies,
        usually one renderer for rising days and one for falling. A wick
        renderer and the bodies standing on its dates are read together as
        one ``candlestick`` layer, and only when that reading is certain
        (see :meth:`_read_candles`); anything less leaves every renderer to
        be read on its own -- the bodies as bars, the segment warned about
        -- as before.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The plot's readable renderers.
        """
        wicks = [r for r in renderers if type(r.glyph).__name__ == "Segment"]
        bodies = [r for r in renderers if type(r.glyph).__name__ == "VBar"]
        for wick in wicks:
            ranges = (wick.x_range_name, wick.y_range_name)
            free = [
                body
                for body in bodies
                if body.id not in self._candle_keys
                and (body.x_range_name, body.y_range_name) == ranges
            ]
            try:
                read = self._read_candles(wick, free)
            except Exception:
                # Not read as a candlestick is not a failure: the renderers
                # are read one by one, and warned about there if need be.
                read = None
            if read is None:
                continue
            key = ("candlestick", wick.id)
            self._candle_reads[key] = read
            for renderer in (wick, *read.bodies):
                self._candle_keys[renderer.id] = key

    def _read_candles(self, wick: Any, bodies: list) -> _Candles | None:
        """
        Read one wick renderer and the bodies on its dates as candles.

        The wicks must be vertical segments, one per date, on a datetime
        axis; every body a candidate ``vbar`` draws must stand on one of
        those dates, and no date may have two. High and low are the wick's
        ends. Open and close are the body's, which way round decided by
        :func:`_open_close`. A wick with no body -- the recipe's
        ``inc``/``dec`` split leaves a day that closed where it opened with
        none -- has no open or close to read, and is left out.

        Parameters
        ----------
        wick : bokeh.models.GlyphRenderer
            A ``segment`` renderer.
        bodies : list of bokeh.models.GlyphRenderer
            The ``vbar`` renderers on the same ranges not yet claimed.

        Returns
        -------
        _Candles or None
            The candles, or ``None`` when this is not certainly OHLC.
        """
        from bokeh.models import CumSum, Stack

        glyph = wick.glyph
        data = wick.data_source.data
        x0, x1 = resolve(glyph, "x0", data), resolve(glyph, "x1", data)
        y0, y1 = resolve(glyph, "y0", data), resolve(glyph, "y1", data)
        rows = visible_indices(wick, source_length(data))
        if not (self._x_dates or is_temporal([x0[i] for i in rows])):
            return None
        stems: dict = {}
        for index in rows:
            if any(is_missing(v[index]) for v in (x0, x1, y0, y1)):
                continue
            at = to_coordinate(x0[index])
            if at != to_coordinate(x1[index]) or at in stems:
                return None
            stems[at] = index
        if not stems:
            return None

        on: dict = {}
        used = []
        for body in bodies:
            body_glyph = body.glyph
            if spec_transform(body_glyph, "x") is not None or any(
                isinstance(spec_expression(body_glyph, prop), (Stack, CumSum))
                for prop in ("top", "bottom")
            ):
                continue
            body_data = body.data_source.data
            xs = resolve(body_glyph, "x", body_data)
            drawn = [
                (to_coordinate(xs[i]), i)
                for i in visible_indices(body, source_length(body_data))
                if not is_missing(xs[i])
            ]
            inside = [(at, i) for at, i in drawn if at in stems]
            if not inside:
                continue
            if len(inside) != len(drawn):
                # Bars off the wicks' dates are something else drawn with
                # them -- volume on a twin axis, say -- not bodies.
                return None
            for at, index in inside:
                if at in on:
                    return None
                on[at] = (body, index)
            used.append(body)
        if not used:
            return None
        prices = _open_close(used)
        if prices is None:
            return None

        candles, cells = [], []
        dates = sorted(on)
        spoken = self._x_native([x0[stems[at]] for at in dates])
        for at, value in zip(dates, spoken):
            body, index = on[at]
            stem = stems[at]
            opened, closed = prices[body.id][index]
            ends = (float(y0[stem]), float(y1[stem]))
            candle = {
                "value": str(value),
                "open": opened,
                "high": max(ends),
                "low": min(ends),
                "close": closed,
            }
            volume = _volume(body, index)
            if volume is None:
                volume = _volume(wick, stem)
            if volume is not None:
                candle["volume"] = volume
            candles.append(candle)
            cells.append([[wick.id, stem], [body.id, index]])
        return _Candles(candles, cells, used, len(stems) - len(on))

    def _candlestick(self, renderers: list) -> BokehLayer | None:
        """
        A wick ``segment`` and its body ``vbar`` s, read as a candlestick.

        The data is the shape the matplotlib and Plotly candlestick paths
        emit -- ``value``, ``open``, ``high``, ``low``, ``close`` per candle,
        ``volume`` only when the source has a volume column -- with no
        ``trend`` or ``volatility``, which the core derives itself.

        The core reports a candle by its column alone -- its row is which
        of open, high, low and close is being read -- so the highlight is
        keyed by ``columns``: selecting the candle's wick and body rows.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The wick and body renderers grouped into this layer.

        Returns
        -------
        BokehLayer or None
            The ``candlestick`` layer.
        """
        read = self._candle_reads[self._candle_keys[renderers[0].id]]
        if read.bodiless:
            wicks = "wick has" if read.bodiless == 1 else "wicks have"
            warn(
                f"{read.bodiless} candlestick {wicks} no body, so the open and "
                "close are not in the figure; left out of the accessible chart."
            )
        schema = self._schema(PlotType.CANDLESTICK, read.candles)
        highlight = {"kind": "select", "columns": read.cells}
        return BokehLayer(schema, self._plot, highlight)

    # ------------------------------------------------------------------ #
    #  Gantt                                                               #
    # ------------------------------------------------------------------ #

    def _spans_dates(self, renderer: Any) -> bool:
        """
        Whether an ``hbar`` runs from one date to another: a Gantt bar.

        Parameters
        ----------
        renderer : bokeh.models.GlyphRenderer
            An ``hbar`` renderer.

        Returns
        -------
        bool
            True when ``left`` and ``right`` both hold dates, or both read a
            column of epoch milliseconds on a datetime x axis.
        """
        glyph = renderer.glyph
        data = renderer.data_source.data
        if self._x_dates and spec_field(glyph, "left") and spec_field(glyph, "right"):
            return True
        try:
            lefts = resolve(glyph, "left", data)
            rights = resolve(glyph, "right", data)
        except UnreadableSpec:
            return False
        return is_temporal(lefts) and is_temporal(rights)

    def _gantt(self, renderers: list) -> BokehLayer | None:
        """
        ``hbar`` s spanning dates, read as a Gantt chart of lanes.

        The shape the matplotlib ``broken_barh`` path emits: ``points``
        nested by lane, each interval ``{x: lane, start, end}``, with
        ``lanes`` naming every lane -- a ``FactorRange`` factor no bar sits
        in is an empty lane, which is what the nesting is for. Lanes run
        bottom to top as the range draws them, since the core's Up arrow
        moves to the next lane; intervals within one run left to right.
        Every ``hbar`` on the pair of ranges is one chart: a Gantt chart
        is often drawn one renderer per resource or colour.

        The ends are dates, and a Gantt point's ``start``/``end`` are
        numbers the core subtracts to announce a length. They are emitted
        as days since the epoch -- hours when some end is not at midnight
        -- with ``unit`` saying so, and the x axis carries a ``format``
        that spells a position back as the date it is.

        A bar's ``label`` is what the legend calls it, when the legend
        names something other than the lane.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The date-spanning ``hbar`` renderers on one pair of ranges.

        Returns
        -------
        BokehLayer or None
            The ``gantt`` layer, or ``None`` when no bar is drawn.
        """
        spans: list[tuple] = []
        for renderer in renderers:
            glyph = renderer.glyph
            data = renderer.data_source.data
            lanes = resolve(glyph, "y", data)
            lefts = resolve(glyph, "left", data)
            rights = resolve(glyph, "right", data)
            names = resolve_column(data, self._legend_fields.get(renderer.id))
            fixed = self._series_label(renderer)
            for index in visible_indices(renderer, source_length(data)):
                lane = _split_offset(lanes[index])[0]
                if any(is_missing(v) for v in (lane, lefts[index], rights[index])):
                    continue
                ends = sorted(
                    float(to_coordinate(end)) for end in (lefts[index], rights[index])
                )
                label = self._legend_rows.get((renderer.id, index))
                if label is None:
                    label = names[index] if names else fixed
                spans.append((lane, *ends, _label(label), renderer.id, index))
        if not spans:
            return None

        order = _factors(self._plot.y_range, [span[0] for span in spans])
        row_of = {_factor_key(lane): row for row, lane in enumerate(order)}
        day = 86_400_000.0
        whole_days = all(end % day == 0 for span in spans for end in span[1:3])
        unit, scale = ("days", day) if whole_days else ("hours", day / 24)

        points: list[list[dict]] = [[] for _ in order]
        grid: list[list] = [[] for _ in order]
        for lane, start, end, label, rid, index in sorted(spans, key=lambda s: s[1]):
            row = row_of.get(_factor_key(lane))
            if row is None:
                continue
            name = _lane_name(lane)
            point = {
                MaidrKey.X: name,
                MaidrKey.START: _clean(start / scale),
                MaidrKey.END: _clean(end / scale),
            }
            if label and label != str(name):
                point[MaidrKey.LABEL] = label
            points[row].append(point)
            grid[row].append([rid, index])

        gantt = {
            MaidrKey.POINTS: points,
            MaidrKey.LANES: [_lane_name(lane) for lane in order],
            # The GanttData field; ``MaidrKey`` has no member for it.
            "unit": unit,
        }
        schema = self._schema(PlotType.GANTT, gantt)
        schema[MaidrKey.ORIENTATION] = "horz"
        schema[MaidrKey.AXES][MaidrKey.X][MaidrKey.FORMAT] = {
            "function": _DATE_FORMATS[unit]
        }
        return BokehLayer(schema, self._plot, {"kind": "select", "grid": grid})

    # ------------------------------------------------------------------ #
    #  Scatter and heatmap                                                 #
    # ------------------------------------------------------------------ #

    def _scatter(self, renderers: list) -> BokehLayer | None:
        """
        One marker renderer, read as a point cloud.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The renderers grouped into this layer.

        Returns
        -------
        BokehLayer or None
            The layer, or ``None`` when nothing is drawn.
        """
        renderer = renderers[0]
        glyph = renderer.glyph
        data = renderer.data_source.data
        xs, ys = resolve(glyph, "x", data), resolve(glyph, "y", data)
        visible = visible_indices(renderer, source_length(data))
        x = None if self._x_dates else _plain_numbers(xs)
        y = None if self._y_dates else _plain_numbers(ys)
        if x is not None and y is not None:
            # Plain numbers on two numeric axes, read a column at a time
            # rather than a value at a time; see :meth:`_numeric_series`.
            (x_gaps, x_values), (y_gaps, y_values) = x, y
            rows = [i for i in visible if not x_gaps[i] and not y_gaps[i]]
            kx, ky = MaidrKey.X.value, MaidrKey.Y.value
            points = [{kx: x_values[i], ky: y_values[i]} for i in rows]
        else:
            rows = [
                i for i in visible if not is_missing(xs[i]) and not is_missing(ys[i])
            ]
            announced_x = self._x_native([xs[i] for i in rows])
            announced_y = self._y_native([ys[i] for i in rows])
            points = [
                {MaidrKey.X: ax, MaidrKey.Y: ay}
                for ax, ay in zip(announced_x, announced_y)
            ]
        if not points:
            return None
        schema = self._schema(PlotType.SCATTER, points)
        name = self._series_label(renderer)
        if name:
            schema[MaidrKey.NAME] = name
        # A point cloud reports the points it is on as indices into ``data``,
        # not as a row and column; see ``NavigateCallback`` in grammar.ts.
        highlight = {"kind": "points", "points": [[renderer.id, i] for i in rows]}
        return BokehLayer(schema, self._plot, highlight)

    def _hexbin(self, renderers: list) -> BokehLayer | None:
        """
        A ``hex_tile`` lattice, its tiles coloured by count, read as a hexbin.

        The shape the matplotlib hexbin path emits: rows of ``{x, y,
        count}`` bins, bottom row first and left to right within a row,
        each bin carrying its own centre because a hex lattice staggers
        alternate rows. The centre is where Bokeh draws the tile, from its
        axial ``q``/``r`` through the glyph's ``size``, ``orientation`` and
        ``aspect_scale`` (:func:`bokeh.util.hex.axial_to_cartesian`, the
        inverse of the binning ``p.hexbin`` does). The count is the column
        the fill colour is mapped from -- ``counts`` for ``p.hexbin``.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The ``hex_tile`` renderer.

        Returns
        -------
        BokehLayer or None
            The ``hexbin`` layer, or ``None`` when no tile is drawn.

        Raises
        ------
        UnreadableSpec
            When no column gives the tiles a count.
        """
        from bokeh.util.hex import axial_to_cartesian

        renderer = renderers[0]
        glyph = renderer.glyph
        data = renderer.data_source.data
        mapper = _color_mapper(glyph)
        field = spec_field(glyph, "fill_color") if _is_continuous(mapper) else None
        counts = resolve_column(data, field)
        if counts is None:
            raise UnreadableSpec(
                "its tiles are not coloured through a colour mapper from a "
                "count column"
            )
        qs, rs = resolve(glyph, "q", data), resolve(glyph, "r", data)
        rows: dict = {}
        for index in visible_indices(renderer, source_length(data)):
            if is_missing(qs[index]) or is_missing(rs[index]):
                continue
            x, y = axial_to_cartesian(
                float(qs[index]), float(rs[index]),
                glyph.size, glyph.orientation, glyph.aspect_scale,
            )
            rows.setdefault(_clean(y), []).append((_clean(x), index))
        if not rows:
            return None

        data_rows, grid = [], []
        for y in sorted(rows):
            bins = sorted(rows[y])
            data_rows.append(
                [
                    {
                        MaidrKey.X: x,
                        MaidrKey.Y: y,
                        MaidrKey.COUNT: to_native(counts[index]),
                    }
                    for x, index in bins
                ]
            )
            grid.append([[renderer.id, index] for _, index in bins])
        # ``p.hexbin`` counts into a column it calls ``c``; that is the
        # matplotlib path's "count", not a name the author chose.
        z_label = _color_bar_title(self._plot, mapper) or (
            "count" if field == "c" else field
        )
        schema = self._schema(PlotType.HEXBIN, data_rows, z_label)
        return BokehLayer(schema, self._plot, {"kind": "select", "grid": grid})

    def _image(self, renderers: list) -> BokehLayer | None:
        """
        An ``image`` -- a 2-D array through a colour mapper -- as a heatmap.

        The array's cells are the heatmap's, placed as Bokeh places them:
        the image spans ``dw`` by ``dh`` from ``x``/``y`` read through its
        ``anchor``, and ``origin`` says which corner array row 0, column 0
        is drawn in (the bottom left by default, so row 0 is the *bottom*
        row). Rows are emitted top first, as every heat layer is; columns
        and rows are named by the centre coordinate of the cells in them.

        An image is a cursor highlight: its cells are no source rows to
        select, so the ring goes to the centre of the cell being read.

        Parameters
        ----------
        renderers : list of bokeh.models.GlyphRenderer
            The ``image`` renderer.

        Returns
        -------
        BokehLayer or None
            The ``heat`` layer, or ``None`` when no image is drawn.

        Raises
        ------
        UnreadableSpec
            For more than one image in the renderer, an array that is not
            2-D and numeric, or one of more than ``_IMAGE_CELL_LIMIT`` cells.
        """
        renderer = renderers[0]
        glyph = renderer.glyph
        data = renderer.data_source.data
        rows = visible_indices(renderer, source_length(data))
        if not rows:
            return None
        if len(rows) > 1:
            raise UnreadableSpec("it draws more than one image, which is not read yet")
        index = rows[0]
        array = np.asarray(resolve(glyph, "image", data)[index])
        if array.ndim != 2 or not np.issubdtype(array.dtype, np.number):
            raise UnreadableSpec("its image is not a 2-D array of numbers")
        height, width = array.shape
        if height * width > _IMAGE_CELL_LIMIT:
            raise UnreadableSpec(
                f"its image has {height * width} cells, more than the "
                f"{_IMAGE_CELL_LIMIT} maidr reads"
            )
        x, y, dw, dh = (
            to_coordinate(resolve(glyph, prop, data)[index])
            for prop in ("x", "y", "dw", "dh")
        )
        if not all(isinstance(v, (int, float)) for v in (x, y, dw, dh)):
            raise UnreadableSpec("its position or size is not a number")
        anchor = str(getattr(glyph, "anchor", "bottom_left"))
        origin = str(getattr(glyph, "origin", "bottom_left"))
        left = x - dw * next((f for k, f in _ANCHOR_X.items() if k in anchor), 0.5)
        bottom = y - dh * next((f for k, f in _ANCHOR_Y.items() if k in anchor), 0.5)
        cell_w, cell_h = dw / width, dh / height
        # Drawn row r (0 at the bottom) and column c (0 at the left) hold
        # array[row_at(r), col_at(c)], whichever corner ``origin`` names.
        row_at = (lambda r: height - 1 - r) if "top" in origin else (lambda r: r)
        col_at = (lambda c: width - 1 - c) if "right" in origin else (lambda c: c)

        centres_x = [_clean(left + (c + 0.5) * cell_w) for c in range(width)]
        centres_y = [_clean(bottom + (r + 0.5) * cell_h) for r in range(height)]
        bottom_up = [
            [to_native(array[row_at(r), col_at(c)]) for c in range(width)]
            for r in range(height)
        ]
        grid = [[[cx, cy] for cx in centres_x] for cy in centres_y]
        heat = {
            MaidrKey.X: [str(v) for v in centres_x],
            MaidrKey.Y: [str(v) for v in reversed(centres_y)],
            MaidrKey.POINTS: list(reversed(bottom_up)),
        }
        z_label = _color_bar_title(self._plot, glyph.color_mapper) or "Value"
        schema = self._schema(PlotType.HEAT, heat, z_label)
        return BokehLayer(schema, self._plot, {"kind": "cursor", "grid": grid})

    def _heat(self, renderers: list) -> BokehLayer | None:
        """
        A ``rect`` per cell, coloured through a colour mapper, read as a heatmap.

        The mapped ``fill_color`` field is the value. Rows and columns come
        from the plot's ``FactorRange`` s, so the grid is the one drawn:
        columns left to right, and rows emitted top first as the other paths
        emit them -- the core reverses them so that row 0 is the bottom one,
        which is also the order the highlight grid is keyed in.
        """
        renderer = renderers[0]
        glyph = renderer.glyph
        data = renderer.data_source.data
        value_field = spec_field(glyph, "fill_color")
        values = resolve_column(data, value_field)
        if values is None:
            raise UnreadableSpec(f"column {value_field!r} is not in the data source")
        xs, ys = resolve(glyph, "x", data), resolve(glyph, "y", data)
        rows = visible_indices(renderer, source_length(data))
        x_factors = _factors(self._plot.x_range, [xs[i] for i in rows])
        y_factors = _factors(self._plot.y_range, [ys[i] for i in rows])
        if not x_factors or not y_factors:
            return None
        x_at = {_factor_key(f): c for c, f in enumerate(x_factors)}
        y_at = {_factor_key(f): r for r, f in enumerate(y_factors)}

        cells: list[list] = [[None] * len(x_factors) for _ in y_factors]
        grid: list[list] = [[None] * len(x_factors) for _ in y_factors]
        for index in rows:
            r = y_at.get(_factor_key(ys[index]))
            c = x_at.get(_factor_key(xs[index]))
            if r is None or c is None:
                continue
            cells[r][c] = to_native(values[index])
            grid[r][c] = [renderer.id, index]

        heat = {
            MaidrKey.X: [factor_label(f) for f in x_factors],
            MaidrKey.Y: [factor_label(f) for f in reversed(y_factors)],
            MaidrKey.POINTS: list(reversed(cells)),
        }
        z_label = _color_bar_title(self._plot, _color_mapper(glyph)) or value_field
        schema = self._schema(PlotType.HEAT, heat, z_label)
        return BokehLayer(schema, self._plot, {"kind": "select", "grid": grid})


# ---------------------------------------------------------------------- #
#  Helpers                                                                #
# ---------------------------------------------------------------------- #


def resolve_column(data: dict, name: str | None) -> list | None:
    """
    A named source column as a list, or ``None`` when there is none.

    Parameters
    ----------
    data : dict
        A ``ColumnDataSource.data`` mapping.
    name : str or None
        The column's name.

    Returns
    -------
    list or None
        The column's values, or ``None`` for no name or a missing column.
    """
    if not name or name not in data:
        return None
    column = data[name]
    return list(column.to_numpy()) if hasattr(column, "to_numpy") else list(column)


def mark_anchor(
    renderer: Any, index: int, columns: dict | None = None
) -> list | None:
    """
    Where to put a cursor on one mark a selection highlight would pick out.

    Used when a layer's marks cannot be highlighted by selecting their
    source row; see ``BokehMaidr._retarget_shared_highlights``. A bar's
    cursor sits at the end of the bar, a bin's and a cell's at its centre,
    a point's on the point -- each in the axis's own units, a dodged bar's
    category carrying its offset the way Bokeh places it.

    Parameters
    ----------
    renderer : bokeh.models.GlyphRenderer
        A ``vbar``, ``hbar``, ``quad``, ``rect``, wedge or point renderer.
    index : int
        The source row of the mark.
    columns : dict, optional
        Resolved columns kept between calls, keyed by renderer id and
        property. A caller anchoring every mark of a layer passes one, so
        each column is resolved once rather than once per mark.

    Returns
    -------
    list or None
        ``[x, y]``, or ``None`` when the mark has no position to point at.
    """
    glyph = renderer.glyph
    data = renderer.data_source.data
    name = type(glyph).__name__
    cache = {} if columns is None else columns

    def at(prop: str) -> Any:
        """The mark's value of one glyph property."""
        key = (renderer.id, prop)
        if key not in cache:
            cache[key] = resolve(glyph, prop, data)
        return cache[key][index]

    if name in ("VBar", "HBar"):
        category_prop, end_prop = ("x", "top") if name == "VBar" else ("y", "right")
        category = _dodged(at(category_prop), spec_transform(glyph, category_prop))
        coords = [to_coordinate(category), to_coordinate(at(end_prop))]
        if name == "HBar":
            coords.reverse()
    elif name == "Quad":
        coords = [
            _middle(to_coordinate(at("left")), to_coordinate(at("right"))),
            _middle(to_coordinate(at("bottom")), to_coordinate(at("top"))),
        ]
    elif name in _WEDGE_GLYPHS:
        coords = _wedge_anchor(glyph, at)
    else:
        coords = [to_coordinate(at("x")), to_coordinate(at("y"))]
    return None if any(c is None for c in coords) else coords


def point_anchors(renderer: Any, rows: list[int], columns: dict | None = None) -> list:
    """
    :func:`mark_anchor` for many rows of one renderer.

    A point's cursor sits on the point: ``[to_coordinate(x),
    to_coordinate(y)]``, or ``None`` when either is ``None``. For columns of
    plain numbers that is read once for the whole column
    (:func:`_plain_numbers`), since :func:`to_coordinate` places a plain
    number where :func:`to_native` announces it, rather than once per row --
    a point cloud on a source a line also reads asked it of every point.
    Any other glyph or column is anchored row by row, as before.

    Parameters
    ----------
    renderer : bokeh.models.GlyphRenderer
        The renderer the rows belong to.
    rows : list of int
        The source rows of its marks.
    columns : dict, optional
        As for :func:`mark_anchor`.

    Returns
    -------
    list
        ``mark_anchor(renderer, row, columns)`` for each row.
    """
    glyph = renderer.glyph
    name = type(glyph).__name__
    if name not in ("VBar", "HBar", "Quad") and name not in _WEDGE_GLYPHS:
        data = renderer.data_source.data
        x = _plain_numbers(resolve(glyph, "x", data))
        y = _plain_numbers(resolve(glyph, "y", data))
        if x is not None and y is not None:
            xs, ys = x[1], y[1]
            return [
                None if xs[i] is None or ys[i] is None else [xs[i], ys[i]] for i in rows
            ]
    return [mark_anchor(renderer, i, columns) for i in rows]


def _wedge_anchor(glyph: Any, at: Callable[[str], Any]) -> list:
    """
    A point inside one wedge: part way out along its middle angle.

    Parameters
    ----------
    glyph : bokeh.models.Wedge or bokeh.models.AnnularWedge
        The wedge glyph.
    at : callable
        Reads the mark's value of one glyph property.

    Returns
    -------
    list
        ``[x, y]`` in data units; the centre when the radius is in screen
        units, which have no data coordinate.
    """
    x, y = to_coordinate(at("x")), to_coordinate(at("y"))
    prop = "radius" if type(glyph).__name__ == "Wedge" else "outer_radius"
    radius, start, end = at(prop), at("start_angle"), at("end_angle")
    if getattr(glyph, f"{prop}_units", "data") != "data" or any(
        is_missing(v) for v in (x, y, radius, start, end)
    ):
        return [x, y]
    if getattr(glyph, "start_angle_units", "rad") == "deg":
        start, end = math.radians(start), math.radians(end)
    clockwise = glyph.direction == "clock"
    sweep = _sweep(float(start), float(end), clockwise)
    middle = float(start) + (-sweep if clockwise else sweep) / 2
    reach = 0.6 * float(radius)
    return [x + reach * math.cos(middle), y + reach * math.sin(middle)]


def _dodged(position: Any, transform: Any) -> Any:
    """
    A category shifted by a ``dodge()`` transform, as BokehJS places it.

    Parameters
    ----------
    position : Any
        The coordinate read from the source.
    transform : Any
        The property's transform, if any.

    Returns
    -------
    Any
        A factor as ``[factor, offset]`` (nested levels first), a number
        moved by the offset, or ``position`` when there is no ``Dodge``.
    """
    from bokeh.models import Dodge

    if not isinstance(transform, Dodge) or is_missing(position):
        return position
    if isinstance(position, str):
        return [position, transform.value]
    if isinstance(position, (list, tuple)):
        return [*position, transform.value]
    try:
        return position + transform.value
    except TypeError:
        return position


def _middle(low: Any, high: Any) -> float | None:
    """
    Halfway between two coordinates, or ``None`` when either is missing.

    Parameters
    ----------
    low, high : Any
        Two coordinates, already in the axis's units (see
        :func:`~maidr.bokeh.data.to_coordinate`).

    Returns
    -------
    float or None
        Their mean.
    """
    if is_missing(low) or is_missing(high):
        return None
    return (float(low) + float(high)) / 2.0


def _is_axis(model: Any) -> bool:
    """Whether a model beside the plot is an axis, not a legend or colour bar."""
    from bokeh.models import Axis

    return isinstance(model, Axis)


def _axis_label(axis: Any, fallback: str) -> str:
    """An axis's label text, or the placeholder the Plotly path uses."""
    label = getattr(axis, "axis_label", None)
    label = getattr(label, "text", label)
    text = str(label or "").strip()
    return text or fallback


def _label(value: Any) -> str | None:
    """A series name as announced, or ``None`` for a missing or blank one."""
    if value is None or is_missing(value):
        return None
    text = str(to_native(value)).strip()
    return text or None


def _legend(plot: Any) -> tuple[dict, dict, dict, str | None]:
    """
    What the plot's legends call each renderer.

    Returns
    -------
    tuple of (dict, dict, dict, str or None)
        Renderer id to a fixed label (``legend_label=``); ``(renderer id,
        source row)`` to the label ``legend_group=`` gave that row's group;
        renderer id to the column ``legend_field=`` reads its labels from in
        the browser; and the first legend's title.
    """
    labels: dict = {}
    rows: dict = {}
    fields: dict = {}
    title = None
    for legend in plot.legend:
        if title is None and legend.title:
            title = str(legend.title).strip() or None
        for item in legend.items:
            spec = item.label
            text = getattr(spec, "value", None)
            column = getattr(spec, "field", None)
            if isinstance(spec, dict):
                text, column = spec.get("value"), spec.get("field")
            elif isinstance(spec, str):
                text = spec
            index = getattr(item, "index", None)
            for renderer in item.renderers:
                if text is not None and index is not None:
                    rows.setdefault((renderer.id, index), str(text))
                elif text is not None:
                    labels.setdefault(renderer.id, str(text))
                elif column is not None:
                    fields.setdefault(renderer.id, column)
    return labels, rows, fields, title


def _reason(error: Exception) -> str:
    """Why a glyph was left out, as the warning names it."""
    if isinstance(error, UnreadableSpec):
        return str(error)
    return f"{type(error).__name__}: {error}"


def _extent(low: Any, high: Any) -> Any:
    """``high - low``, or ``high`` alone when ``low`` is not a number."""
    if is_missing(high):
        return None
    if not is_missing(low) and is_temporal([low, high]):
        # A bar spanning two dates is a duration, which no bar point can
        # carry; announcing its end date as its size would be wrong without
        # saying so. An ``hbar`` doing it is a Gantt bar, and grouped as one
        # before it gets here; a ``vbar`` is not read.
        raise UnreadableSpec("a vertical bar spanning dates is not read yet")
    high = to_native(high)
    low = None if is_missing(low) else to_native(low)
    if not low:
        # From the baseline, the value is the one the author wrote -- an
        # integer count stays an integer rather than turning into ``2.0``.
        return high
    try:
        return high - low
    except TypeError:
        return high


def _plain_numbers(values: list) -> tuple[list[bool], list] | None:
    """
    A column of plain numbers, read at once: which values are missing, and each
    as :func:`to_native` announces it.

    For a column whose values are all exactly ``float``, all ``np.float64``,
    or all ``int`` or ``np.int64`` within ``int64``, every step of the
    per-value reading is known in advance. :func:`is_missing` is a NaN test,
    since none of them is ``None``, a date or ``NaT``; :func:`to_native` is
    the value as a Python number, ``None`` for a NaN or an infinity; and
    neither is a date, so :func:`_announced` would not spell the column as
    one off a numeric axis. ``tolist()`` hands over the same Python numbers
    ``.item()`` does, ``-0.0`` included.

    An integer beyond ``int64`` is left to the per-value reading, so it fails
    there exactly as it did: :func:`is_missing` cannot test one past the
    float range.

    Parameters
    ----------
    values : list
        One column, as :func:`resolve` reads it.

    Returns
    -------
    tuple of (list of bool, list) or None
        ``[is_missing(v) for v in values]`` and ``[to_native(v) for v in
        values]``, or ``None`` for any other column -- a ``bool``, a string,
        ``None``, a date, a mix of types, or nothing at all.
    """
    kinds = set(map(type, values))
    if kinds == {float} or kinds == {np.float64}:
        array = np.array(values, dtype=float)
        announced = array.tolist()
        for index in np.flatnonzero(~np.isfinite(array)).tolist():
            announced[index] = None
        return np.isnan(array).tolist(), announced
    if kinds == {int} or kinds == {np.int64}:
        try:
            array = np.array(values)
        except OverflowError:
            return None
        if array.dtype.kind != "i":
            return None
        return [False] * len(values), array.tolist()
    return None


def _announced(values: list, dates: bool) -> list:
    """
    A column of coordinates as announced.

    Dates are spelled ISO for the whole column at once, so a series of
    midnights and noons shares one unit. Plain numbers on a
    ``DatetimeAxis`` are the epoch milliseconds Bokeh stores time as.
    """
    present = [v for v in values if not is_missing(v)]
    if is_temporal(present):
        return dates_to_iso(values)
    if dates and present and all(isinstance(v, Number) for v in present):
        return epoch_ms_to_iso(values)
    return [to_native(v) for v in values]


def _factor_key(value: Any) -> Any:
    """A hashable key for a factor, which may be a list for a nested one."""
    if isinstance(value, (list, tuple)):
        return tuple(_factor_key(v) for v in value)
    return to_native(value)


def _factors(factor_range: Any, seen: list) -> list:
    """
    The rows or columns of a heatmap, in the order they are drawn.

    On a ``FactorRange`` that is the range's own factor order. On a numeric
    or datetime axis it is ascending coordinate -- bottom to top, left to
    right -- whatever order the source lists the cells in.

    Parameters
    ----------
    factor_range : bokeh.models.Range
        The plot's range along this axis.
    seen : list
        The coordinates the cells are drawn at, one per drawn row.

    Returns
    -------
    list
        Each distinct coordinate once, in drawn order.
    """
    from bokeh.models import FactorRange

    if isinstance(factor_range, FactorRange) and factor_range.factors:
        return list(factor_range.factors)
    ordered: list = []
    keys: set = set()
    for value in seen:
        key = _factor_key(value)
        if key is not None and key not in keys:
            keys.add(key)
            ordered.append(value)
    try:
        ordered.sort(key=to_coordinate)
    except TypeError:
        # Mixed kinds have no drawn order to recover; keep the source's.
        pass
    return ordered


def _in_drawn_order(items: list, category_range: Any) -> list:
    """
    Bars in the order they are drawn along their category axis.

    On a ``FactorRange`` that is the range's own factor order, which may
    differ from the source's row order. On a numeric axis it is ascending
    position. Either way, arrowing right moves one bar to the right.
    """
    from bokeh.models import FactorRange

    if isinstance(category_range, FactorRange) and category_range.factors:
        order = {_factor_key(f): i for i, f in enumerate(category_range.factors)}
        last = len(order)
        return sorted(items, key=lambda item: order.get(_factor_key(item[0]), last))
    try:
        return sorted(items, key=lambda item: item[0])
    except TypeError:
        return items


def _color_mapper(glyph: Any) -> Any:
    """The colour mapper a glyph's ``fill_color`` goes through, or ``None``."""
    from bokeh.models import ColorMapper

    transform = spec_transform(glyph, "fill_color")
    return transform if isinstance(transform, ColorMapper) else None


def _is_continuous(mapper: Any) -> bool:
    """
    Whether a colour mapper maps numbers, so its field is a heatmap's value.

    Parameters
    ----------
    mapper : bokeh.models.ColorMapper or None
        The mapper, from :func:`_color_mapper`.

    Returns
    -------
    bool
        True for a ``LinearColorMapper``, ``LogColorMapper`` or any other
        ``ContinuousColorMapper``; False for a categorical one or none.
    """
    from bokeh.models import ContinuousColorMapper

    return isinstance(mapper, ContinuousColorMapper)


def _split_offset(position: Any) -> tuple[Any, float | None]:
    """
    A bar's category, apart from the numeric offset Bokeh lets it carry.

    Bokeh places a mark off a factor's centre when its coordinate ends in a
    number: ``("a", -0.2)`` is ``a`` shifted left, and ``("a", "x", 0.1)``
    the nested factor ``("a", "x")`` shifted right. That offset is how the
    mark is placed, not part of what it is.

    Parameters
    ----------
    position : Any
        One coordinate read from the source.

    Returns
    -------
    tuple of (Any, float or None)
        The factor, and the offset, or ``None`` when there is none.
    """
    if isinstance(position, (list, tuple)) and len(position) > 1:
        last = position[-1]
        if isinstance(last, Number) and not isinstance(last, bool):
            rest = tuple(position[:-1])
            return (rest[0] if len(rest) == 1 else rest), float(last)
    return position, None


def _is_nested(position: Any) -> bool:
    """
    Whether a coordinate is a nested factor such as ``("Apples", "2015")``.

    Parameters
    ----------
    position : Any
        One coordinate, its offset already removed.

    Returns
    -------
    bool
        True for a tuple or list of more than one level.
    """
    return isinstance(position, (list, tuple)) and len(position) > 1


def _offset(renderer: Any, prop: str) -> float | None:
    """
    How far a bar renderer is shifted off its categories, if at all.

    Parameters
    ----------
    renderer : bokeh.models.GlyphRenderer
        A ``vbar`` or ``hbar`` renderer.
    prop : str
        Its category property, ``"x"`` or ``"y"``.

    Returns
    -------
    float or None
        The ``dodge()`` value, else the offset its first drawn coordinate
        carries, else ``None``.
    """
    from bokeh.models import Dodge

    transform = spec_transform(renderer.glyph, prop)
    if isinstance(transform, Dodge):
        return float(transform.value)
    try:
        positions = resolve(renderer.glyph, prop, renderer.data_source.data)
    except UnreadableSpec:
        return None
    for position in positions:
        if not is_missing(position):
            return _split_offset(position)[1]
    return None


def _color_bar_title(plot: Any, mapper: Any) -> str | None:
    """The title of the colour bar drawn for ``mapper``, if the plot has one."""
    from bokeh.models import ColorBar

    for side in (plot.right, plot.left, plot.above, plot.below, plot.center):
        for annotation in side:
            if isinstance(annotation, ColorBar) and annotation.color_mapper is mapper:
                title = str(annotation.title or "").strip()
                if title:
                    return title
    return None


def _lane_name(lane: Any) -> str | int | float:
    """
    What a Gantt lane is called: its factor, or its position.

    Parameters
    ----------
    lane : Any
        The lane's coordinate on the y axis.

    Returns
    -------
    str or int or float
        The factor's label, or the number a numeric lane sits at.
    """
    if isinstance(lane, (str, list, tuple)):
        return factor_label(lane)
    value = to_native(lane)
    return value if isinstance(value, (int, float)) else str(value)


def _constant_centre(renderer: Any) -> tuple | None:
    """
    The one centre every wedge of a renderer is drawn round, if they share one.

    Parameters
    ----------
    renderer : bokeh.models.GlyphRenderer
        A ``wedge`` or ``annular_wedge`` renderer.

    Returns
    -------
    tuple or None
        ``(x, y)`` as plain values, or ``None`` when the rows are centred
        in more than one place or the centre cannot be read.
    """
    data = renderer.data_source.data
    try:
        xs = resolve(renderer.glyph, "x", data)
        ys = resolve(renderer.glyph, "y", data)
    except UnreadableSpec:
        return None
    centres = {
        (_factor_key(xs[i]), _factor_key(ys[i]))
        for i in visible_indices(renderer, source_length(data))
    }
    return centres.pop() if len(centres) == 1 else None


def _radians(glyph: Any, prop: str, data: dict) -> list:
    """
    An angle property's values in radians, whichever units it was given in.

    Parameters
    ----------
    glyph : bokeh.models.Glyph
        A wedge glyph.
    prop : str
        ``"start_angle"`` or ``"end_angle"``.
    data : dict
        The renderer's ``ColumnDataSource.data``.

    Returns
    -------
    list
        One angle per source row, ``None`` where it is missing.
    """
    values = resolve(glyph, prop, data)
    degrees = getattr(glyph, f"{prop}_units", "rad") == "deg"
    out = []
    for value in values:
        if is_missing(value):
            out.append(None)
            continue
        number = float(value)
        out.append(math.radians(number) if degrees else number)
    return out


def _sweep(start: float, end: float, clockwise: bool) -> float:
    """
    How far round a wedge reaches, in radians, the way Bokeh draws it.

    Parameters
    ----------
    start, end : float
        The wedge's angles, in radians.
    clockwise : bool
        Whether Bokeh draws it from ``start`` clockwise to ``end``.

    Returns
    -------
    float
        The sweep, in ``[0, 2 pi]``; a whole turn is kept as one.
    """
    turn = 2 * math.pi
    span = (start - end) if clockwise else (end - start)
    if abs(span) >= turn - 1e-12:
        return turn
    return span % turn


def _dial(angle: float) -> float:
    """
    A Bokeh angle as MAIDR's ``startAngle`` measures one.

    Bokeh measures radians counterclockwise from 3 o'clock; MAIDR degrees
    clockwise from 12 o'clock.

    Parameters
    ----------
    angle : float
        Radians, counterclockwise from the positive x axis.

    Returns
    -------
    float
        Degrees clockwise from 12 o'clock, in ``[0, 360)``.
    """
    return _clean((90.0 - math.degrees(angle)) % 360.0) % 360.0


def _clean(value: float) -> float | int:
    """
    A float with the noise of a radian round trip taken off.

    Parameters
    ----------
    value : float
        A computed number.

    Returns
    -------
    float or int
        The number to 10 significant digits, as an ``int`` when whole.
    """
    rounded = float(f"{value:.10g}")
    return int(rounded) if rounded.is_integer() else rounded


def _numeric_column(column: list) -> np.ndarray | None:
    """
    A source column as floats, or ``None`` when it is not all numbers.

    Parameters
    ----------
    column : list
        One column of a ``ColumnDataSource``, from :func:`resolve_column`.

    Returns
    -------
    numpy.ndarray or None
        The column, or ``None`` for text, dates, booleans or nested values.
    """
    if not column or not all(
        isinstance(v, (int, float, np.integer, np.floating))
        and not isinstance(v, (bool, np.bool_))
        for v in column
    ):
        return None
    return np.array(column, dtype=float)


def _proportional(values: np.ndarray, target: np.ndarray) -> bool:
    """
    Whether ``target`` is ``values`` scaled by one positive factor.

    Parameters
    ----------
    values, target : numpy.ndarray
        Two columns over the same rows.

    Returns
    -------
    bool
        True when every value is finite and non-negative, their total is
        positive, and scaling them to ``target``'s total reproduces it.
    """
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        return False
    total, wanted = values.sum(), target.sum()
    if total <= 0 or wanted <= 0:
        return False
    return bool(np.allclose(values / total * wanted, target, rtol=1e-6, atol=1e-9))


def _only_name(names: list[str]) -> str | None:
    """
    The one column name every renderer of a layer agrees on, or ``None``.

    Parameters
    ----------
    names : list of str
        The name each renderer read its values from.

    Returns
    -------
    str or None
        The name, when there is exactly one distinct one.
    """
    distinct = set(names)
    return distinct.pop() if len(distinct) == 1 else None


def _open_close(bodies: list) -> dict | None:
    """
    Each body's open and close, when which end is which is certain.

    A ``vbar`` body is drawn between ``top`` and ``bottom`` whichever is
    larger, so its ends alone do not say which is the open. Two readings
    are certain enough to announce:

    * every body's source has ``open`` and ``close`` columns (any case)
      and they are the ends the body is drawn between -- a figure built on
      one ``ColumnDataSource(df)`` with views for rising and falling days;
    * some body is drawn upside down, ``top`` below ``bottom``, which only
      happens when the author passed the prices straight through, as
      Bokeh's own recipe does (``vbar(date, w, df.open[inc],
      df.close[inc])``): then ``top`` is the open and ``bottom`` the close
      for every body.

    Bodies drawn ``top >= bottom`` throughout with no price columns could be
    either way up, and are not guessed at -- fill colours are not read.

    Parameters
    ----------
    bodies : list of bokeh.models.GlyphRenderer
        The ``vbar`` renderers drawing the bodies.

    Returns
    -------
    dict or None
        Renderer id to ``{source row: (open, close)}``, or ``None``.
    """
    ends = {}
    for body in bodies:
        data = body.data_source.data
        rows = visible_indices(body, source_length(data))
        tops = resolve(body.glyph, "top", data)
        bottoms = resolve(body.glyph, "bottom", data)
        ends[body.id] = {
            i: (float(tops[i]), float(bottoms[i]))
            for i in rows
            if not is_missing(tops[i]) and not is_missing(bottoms[i])
        }

    columns = {}
    for body in bodies:
        data = body.data_source.data
        opens = resolve_column(data, _named(data, "open"))
        closes = resolve_column(data, _named(data, "close"))
        if opens is None or closes is None:
            break
        columns[body.id] = (opens, closes)
    if len(columns) == len(bodies):
        prices: dict = {}
        for body_id, rows in ends.items():
            opens, closes = columns[body_id]
            prices[body_id] = {}
            for i, (top, bottom) in rows.items():
                if is_missing(opens[i]) or is_missing(closes[i]):
                    return None
                pair = (float(opens[i]), float(closes[i]))
                if not np.allclose(sorted(pair), sorted((top, bottom))):
                    return None
                prices[body_id][i] = pair
        return prices

    if any(top < bottom for rows in ends.values() for top, bottom in rows.values()):
        return {body_id: dict(rows) for body_id, rows in ends.items()}
    return None


def _named(data: dict, word: str) -> str | None:
    """
    The source column called ``word``, in any case.

    Parameters
    ----------
    data : dict
        A ``ColumnDataSource.data`` mapping.
    word : str
        The lower-case name.

    Returns
    -------
    str or None
        The column's own name, or ``None`` when there is none.
    """
    return next((name for name in data if str(name).lower() == word), None)


def _volume(renderer: Any, index: int) -> float | None:
    """
    A candle's volume, from a ``volume`` column of its source, if any.

    Parameters
    ----------
    renderer : bokeh.models.GlyphRenderer
        A wick or body renderer.
    index : int
        The candle's source row.

    Returns
    -------
    float or None
        The volume, or ``None`` when the source has no volume for it.
    """
    data = renderer.data_source.data
    column = resolve_column(data, _named(data, "volume"))
    if column is None or is_missing(column[index]):
        return None
    try:
        return float(column[index])
    except (TypeError, ValueError):
        return None
