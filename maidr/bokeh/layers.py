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

import uuid
from dataclasses import dataclass, field
from numbers import Number
from typing import Any, Callable

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
        cursor glyph instead.
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

        groups: dict[tuple, list] = {}
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
            key = self._group_key(renderer)
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
        }
        layers: list[BokehLayer] = []
        for key, renderers in groups.items():
            try:
                layer = builders[key[0]](renderers)
            except UnreadableSpec as reason:
                names = sorted({type(r.glyph).__name__ for r in renderers})
                warn(
                    f"maidr cannot read the Bokeh {', '.join(names)} glyph "
                    f"({reason}); it is left out of the accessible chart."
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
        if name == "VArea":
            if isinstance(spec_expression(glyph, "y2"), (Stack, CumSum)):
                return ("stacked_area", renderer.x_range_name, renderer.y_range_name)
            return ("area", renderer.id)
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
                by_category.setdefault(key, (position, value, index))
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
        horizontal = len({to_native(left[i]) for i in rows}) == 1 and len(
            {to_native(bottom[i]) for i in rows}
        ) > 1
        bins = []
        for index in rows:
            start, end = (bottom, top) if horizontal else (left, right)
            low, high = (left, right) if horizontal else (bottom, top)
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

    # ------------------------------------------------------------------ #
    #  Lines, steps and areas                                              #
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

    def _line(self, renderers: list) -> BokehLayer | None:
        rows, grid = self._line_like(renderers)
        if not rows:
            return None
        schema = self._schema(PlotType.LINE, rows, self._legend_title)
        return BokehLayer(schema, self._plot, {"kind": "cursor", "grid": grid})

    def _step(self, renderers: list) -> BokehLayer | None:
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
        """
        rows, grid = [], []
        for renderer in renderers:
            glyph = renderer.glyph
            data = renderer.data_source.data
            xs = resolve(glyph, "x", data)
            lows, highs = resolve(glyph, "y1", data), resolve(glyph, "y2", data)
            label = self._series_label(renderer)
            announced_x = self._x_native(xs)
            row, coords = [], []
            for x, ax, low, high in zip(xs, announced_x, lows, highs):
                if is_missing(x):
                    continue
                point = {MaidrKey.X: ax, MaidrKey.Y: to_native(_extent(low, high))}
                if label:
                    point[MaidrKey.Z] = label
                row.append(point)
                top = None if is_missing(high) else to_coordinate(high)
                coords.append(None if top is None else [to_coordinate(x), top])
            if row:
                rows.append(row)
                grid.append(coords)
        return rows, grid

    def _area(self, renderers: list) -> BokehLayer | None:
        rows, grid = self._bands(renderers)
        if not rows:
            return None
        schema = self._schema(PlotType.AREA, rows)
        return BokehLayer(schema, self._plot, {"kind": "cursor", "grid": grid})

    def _stacked_area(self, renderers: list) -> BokehLayer | None:
        rows, grid = self._bands(renderers)
        if not rows:
            return None
        plot_type = PlotType.STACKED_AREA if len(rows) > 1 else PlotType.AREA
        schema = self._schema(plot_type, rows, self._legend_title)
        return BokehLayer(schema, self._plot, {"kind": "cursor", "grid": grid})

    # ------------------------------------------------------------------ #
    #  Scatter and heatmap                                                 #
    # ------------------------------------------------------------------ #

    def _scatter(self, renderers: list) -> BokehLayer | None:
        renderer = renderers[0]
        glyph = renderer.glyph
        data = renderer.data_source.data
        xs, ys = resolve(glyph, "x", data), resolve(glyph, "y", data)
        rows = [
            i
            for i in visible_indices(renderer, source_length(data))
            if not is_missing(xs[i]) and not is_missing(ys[i])
        ]
        announced_x = self._x_native([xs[i] for i in rows])
        announced_y = self._y_native([ys[i] for i in rows])
        points = [
            {MaidrKey.X: ax, MaidrKey.Y: ay} for ax, ay in zip(announced_x, announced_y)
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
    """A named source column as a list, or ``None`` when there is none."""
    if not name or name not in data:
        return None
    column = data[name]
    return list(column.to_numpy()) if hasattr(column, "to_numpy") else list(column)


def mark_anchor(renderer: Any, index: int) -> list | None:
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
        A ``vbar``, ``hbar``, ``quad``, ``rect`` or point renderer.
    index : int
        The source row of the mark.

    Returns
    -------
    list or None
        ``[x, y]``, or ``None`` when the mark has no position to point at.
    """
    glyph = renderer.glyph
    data = renderer.data_source.data
    name = type(glyph).__name__

    def at(prop: str) -> Any:
        return resolve(glyph, prop, data)[index]

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
    else:
        coords = [to_coordinate(at("x")), to_coordinate(at("y"))]
    return None if any(c is None for c in coords) else coords


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
    from bokeh.models import Axis

    return isinstance(model, Axis)


def _axis_label(axis: Any, fallback: str) -> str:
    """An axis's label text, or the placeholder the Plotly path uses."""
    label = getattr(axis, "axis_label", None)
    label = getattr(label, "text", label)
    text = str(label or "").strip()
    return text or fallback


def _label(value: Any) -> str | None:
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


def _extent(low: Any, high: Any) -> Any:
    """``high - low``, or ``high`` alone when ``low`` is not a number."""
    if is_missing(high):
        return None
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
