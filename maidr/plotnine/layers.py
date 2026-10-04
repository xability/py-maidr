"""Read the layers of a drawn ``ggplot`` into MAIDR layers.

What is read is plotnine's own layer data -- the frame each geom was handed to
draw, after the stat, the position adjustment and the scales have run -- and
not the matplotlib artists it became. That is the reading r-maidr makes of a
built ggplot2 object, and it is exact where reading the artists would be a
reconstruction: a stacked segment's own value, a dodged bar's category and a
box's whiskers are all columns of that frame, while the drawn rectangles only
say where they ended up.

The artists are still needed, for the highlight. :func:`draw` records, for
every call a geom makes to its ``draw_group``, the frame it was handed and the
artists that call added to the axes, so each row of data is paired with the
element that drew it without inferring anything from the SVG.

A geom, stat, position or coordinate system not listed here is declined with
a warning rather than read as the nearest thing it resembles: a jittered point
has lost its true position, a stacked area is not a stacked bar, and a reading
that is plausible but wrong is worse than none.
"""

from __future__ import annotations

import copy
import types
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PathCollection, PolyCollection
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot.maidr_plot import MaidrPlot

#: Prefix of the columns that carry an aesthetic's value from before its scale
#: mapped it: ``fill`` is a colour by the time it is drawn, and a heatmap cell
#: or a series is announced by the value the colour stands for.
RAW = "__maidr_raw_"

#: The columns plotnine's facet layout table carries besides the facet
#: variables themselves.
_LAYOUT_COLUMNS = {"PANEL", "ROW", "COL", "SCALE_X", "SCALE_Y", "AXIS_X", "AXIS_Y"}

#: Coordinate systems whose drawing is the data's own positions. ``coord_flip``
#: swaps the axes and ``coord_trans`` bends them, and neither is read yet.
_COORDS = {"coord_cartesian", "coord_fixed", "coord_equal"}


class Unreadable(Exception):
    """A layer maidr declines; the message is the reason the warning gives."""


@dataclass
class DrawnGroup:
    """One ``draw_group`` call: the axes, the frame it was handed, what it drew."""

    ax: Axes
    data: Any
    artists: list


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------


def draw(plot: Any) -> tuple[Any, Any, list[list[DrawnGroup]]]:
    """
    Draw a copy of ``plot``, recording what each of its layers drew.

    The caller's ``ggplot`` is left untouched: drawing a ``ggplot`` builds it
    in place, and the recording is installed on the copy's own layers.

    Parameters
    ----------
    plot : plotnine.ggplot
        The plot to draw.

    Returns
    -------
    tuple
        The plot as built and drawn, its matplotlib figure, and per layer the
        :class:`DrawnGroup` s its geom drew.
    """
    built = copy.deepcopy(plot)
    drawn: list[list[DrawnGroup]] = [[] for _ in built.layers]
    for layer, sink in zip(built.layers, drawn):
        # `draw_group` is a static method that `draw_panel` reaches through
        # `self`, so an attribute on this copy's geom intercepts exactly this
        # layer's calls. Nested calls -- a boxplot's whiskers drawn through
        # `geom_segment.draw_group` -- go through the class and are part of
        # the outer call's record.
        layer.geom.draw_group = _recording(layer.geom.draw_group, sink)
    # Bound, so that a deep copy of the layers is bound to the copy: plotnine
    # before 0.15 draws a copy of the plot it is asked to draw.
    built.layers.map = types.MethodType(_map_keeping_raw_values, built.layers)

    # The internal context keeps maidr's own patches out of it: `geom_point`
    # draws through `Axes.scatter`, which would otherwise register a second,
    # partial reading of the same figure.
    with ContextManager.set_internal_context():
        figure = built.draw()
    # 0.15 builds the plot it was handed, older releases a copy; the figure's
    # layout engine holds whichever was built.
    built = getattr(figure.get_layout_engine(), "plot", built)
    return built, figure, drawn


def _recording(draw_group: Callable, sink: list[DrawnGroup]) -> Callable:
    """Wrap a geom's ``draw_group`` so every call is recorded in ``sink``."""

    def record(data: Any, panel_params: Any, coord: Any, ax: Axes, *args, **kwargs):
        before = {id(artist) for artist in ax.get_children()}
        # Copied before the call: some geoms write into the frame they are
        # handed (`geom_smooth` sets `alpha`).
        handed = data.copy()
        result = draw_group(data, panel_params, coord, ax, *args, **kwargs)
        added = [artist for artist in ax.get_children() if id(artist) not in before]
        sink.append(DrawnGroup(ax, handed, added))
        return result

    return record


def _map_keeping_raw_values(layers: Any, scales: Any) -> Any:
    """
    ``Layers.map`` that keeps a copy of each column a scale is about to map.

    Mapping replaces ``fill`` with colours, and a colour cannot be read back
    into the value it stands for. The copy rides in the same frame, so it
    survives every later step -- stacking, dropping missing rows, splitting by
    panel and group -- aligned with the row it belongs to.
    """
    aesthetics = {ae for scale in scales for ae in scale.aesthetics}
    for layer in layers:
        for ae in sorted(aesthetics & set(layer.data.columns)):
            layer.data[RAW + ae] = layer.data[ae]
    return type(layers).map(layers, scales)


# --------------------------------------------------------------------------
# Panels and positions
# --------------------------------------------------------------------------


class Position:
    """One panel's x or y scale: turns a plotnine position into a value.

    A discrete position is the category drawn there, named by the tick label
    the reader would see; a continuous one is taken back through the scale's
    transform, so a ``scale_x_log10`` axis announces 100 rather than 2.
    """

    def __init__(self, scale: Any, view: Any) -> None:
        from plotnine.scales.scale_discrete import scale_discrete

        self._scale = scale
        self.discrete = isinstance(scale, scale_discrete)
        self._names: dict[int, str] = {}
        if self.discrete:
            limits = getattr(scale, "final_limits", None) or []
            self._names = {i + 1: str(level) for i, level in enumerate(limits)}
            for brk, label in zip(view.breaks, view.labels):
                if _finite(brk):
                    self._names[int(round(float(brk)))] = str(label)

    def category(self, position: float) -> str:
        """The name of the category at, or nearest to, ``position``."""
        index = int(round(float(position)))
        return self._names.get(index, str(index))

    def values(self, positions: Any) -> list:
        """What each position is announced as, in order."""
        positions = np.asarray(positions, dtype=float)
        if self.discrete:
            return [self.category(p) for p in positions]
        return [_native(v) for v in self._scale.inverse(positions)]

    @property
    def linear(self) -> bool:
        """Whether a difference of positions is a difference of values."""
        if self.discrete:
            return False
        probe = np.array([-2.0, 0.0, 1.0, 10.0])
        try:
            back = np.asarray(self._scale.inverse(probe), dtype=float)
        except (TypeError, ValueError):
            return False
        return bool(np.allclose(back, probe))


@dataclass
class Panel:
    """One facet panel: where it sits on the grid and how to read its scales."""

    ax: Axes
    row: int
    col: int
    title: str
    x: Position
    y: Position


def read_panels(built: Any) -> dict[int, Panel]:
    """
    Every panel of a drawn ``ggplot``, keyed by plotnine's ``PANEL`` number.

    ``ROW`` and ``COL`` of the layout table are the panel's cell, so a
    ``facet_wrap`` or ``facet_grid`` becomes MAIDR's subplot grid as drawn --
    an empty cell of a ``facet_grid`` included. A faceted panel is titled with
    its facet variables, in the ``var = value`` form a seaborn ``FacetGrid``
    titles its panels with.
    """
    layout = built.layout
    table = layout.layout
    facet_vars = [c for c in table.columns if c not in _LAYOUT_COLUMNS]
    panels: dict[int, Panel] = {}
    for _, entry in table.iterrows():
        number = int(entry["PANEL"])
        index = number - 1
        view = layout.panel_params[index]
        title = " | ".join(f"{var} = {entry[var]}" for var in facet_vars)
        panels[number] = Panel(
            ax=layout.axs[index],
            row=int(entry["ROW"]) - 1,
            col=int(entry["COL"]) - 1,
            title=title,
            x=Position(layout.panel_scales_x[int(entry["SCALE_X"]) - 1], view.x),
            y=Position(layout.panel_scales_y[int(entry["SCALE_Y"]) - 1], view.y),
        )
    return panels


def unreadable_coord(built: Any) -> str | None:
    """The coordinate system's name when it is not one read here, else None."""
    name = type(built.coordinates).__name__
    return None if name in _COORDS else name


# --------------------------------------------------------------------------
# The layer
# --------------------------------------------------------------------------


class PlotnineLayer(MaidrPlot):
    """
    A MAIDR layer whose schema was read from plotnine's layer data.

    Everything the matplotlib layers read off their axes -- labels, title,
    grid cell -- is plotnine's to say here: plotnine draws its axis titles as
    figure text and nests its panels in a gridspec of its own, so the axes
    would answer ``""`` and ``(0, 0)`` for every one of them.
    """

    def __init__(
        self,
        ax: Axes,
        plot_type: PlotType,
        *,
        panel: Panel,
        title: str,
        axes: dict,
        data: Any,
        selectors: Any = None,
        extra: dict | None = None,
    ) -> None:
        super().__init__(ax, plot_type)
        self.row_index = panel.row
        self.col_index = panel.col
        self._title = title
        self._axes = axes
        self._data = data
        self._selectors = selectors
        self._extra = extra or {}
        self._support_highlighting = selectors is not None

    def render(self) -> dict:
        """The layer's schema, with a fresh id as every layer's render has."""
        schema = {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: self.type,
            MaidrKey.TITLE: self._title,
            MaidrKey.AXES: copy.deepcopy(self._axes),
            MaidrKey.DATA: copy.deepcopy(self._data),
        }
        if self._support_highlighting:
            schema[MaidrKey.SELECTOR] = copy.deepcopy(self._selectors)
        schema.update(copy.deepcopy(self._extra))
        return schema

    def _extract_plot_data(self) -> Any:
        return copy.deepcopy(self._data)


# --------------------------------------------------------------------------
# Reading one layer
# --------------------------------------------------------------------------


@dataclass
class _Context:
    """What every reader needs besides the layer: panels, labels, titles."""

    panels: dict[int, Panel]
    labels: Any
    single_panel_title: str | None

    def title(self, panel: Panel) -> str:
        if self.single_panel_title is not None:
            return self.single_panel_title
        return panel.title

    def label(self, name: str, fallback: str = "") -> str:
        value = self.labels.get(name, None)
        return fallback if value is None or str(value) == "" else str(value)

    def axes(self, z: str | None = None) -> dict:
        axes = {
            MaidrKey.X: MaidrPlot._axis_config(label=self.label("x", "X")),
            MaidrKey.Y: MaidrPlot._axis_config(label=self.label("y", "Y")),
        }
        if z:
            axes[MaidrKey.Z] = MaidrPlot._axis_config(label=z)
        return axes


def read_layer(
    layer: Any, drawn: list[DrawnGroup], panels: dict[int, Panel], labels: Any
) -> list[PlotnineLayer]:
    """
    One MAIDR layer per panel the ``ggplot`` layer drew on.

    Parameters
    ----------
    layer : plotnine.layer.layer
        A layer of the drawn plot.
    drawn : list of DrawnGroup
        What its geom drew, as :func:`draw` recorded it.
    panels : dict
        :func:`read_panels` of the drawn plot.
    labels : plotnine.labels_view
        The drawn plot's labels.

    Returns
    -------
    list of PlotnineLayer
        In panel order. Empty for a layer that drew nothing.

    Raises
    ------
    Unreadable
        When the geom, its stat or its position is not one read here, or it
        was not drawn the way the reader expects to find it.
    """
    geom = type(layer.geom).__name__
    stat = type(layer.stat).__name__
    position = type(layer.position).__name__

    if geom == "geom_blank":
        return []
    if geom in ("geom_bar", "geom_col", "geom_histogram"):
        reader = _hist if stat == "stat_bin" else _bars
    else:
        reader = _READERS.get(geom)
    if reader is None:
        raise Unreadable(f"{geom} is not one of the geoms maidr reads")

    single = len(panels) == 1
    title = labels.get("title", None) if single else None
    context = _Context(panels, labels, (title or "") if single else None)

    by_panel: dict[int, list[DrawnGroup]] = {}
    for group in drawn:
        if len(group.data) == 0:
            continue
        by_panel.setdefault(int(group.data["PANEL"].iloc[0]), []).append(group)

    return [
        reader(by_panel[number], context.panels[number], context, position)
        for number in sorted(by_panel)
    ]


# --------------------------------------------------------------------------
# Readers, one per geom family
# --------------------------------------------------------------------------


def _bars(
    groups: list[DrawnGroup], panel: Panel, context: _Context, position: str
) -> PlotnineLayer:
    """``geom_bar`` and ``geom_col``: a bar, stacked, dodged or filled chart.

    One bar per category is a bar chart, whatever its colours: a fill mapped
    to the same variable as ``x`` colours the bars without splitting them.
    More than one bar at a category is a segmented chart, whose series are
    told apart by the aesthetics mapped to them, and whose kind the position
    adjustment says.
    """
    segmented = {
        "position_stack": PlotType.STACKED,
        "position_fill": PlotType.NORMALIZED,
        "position_dodge": PlotType.DODGED,
        "position_dodge2": PlotType.DODGED,
    }
    if position not in segmented and position != "position_identity":
        raise Unreadable(f"bars placed with {position} are not read")
    rows = _collection_rows(groups, PolyCollection, "bars")
    stacked = position in ("position_stack", "position_fill")
    linear = panel.y.linear
    if not panel.x.discrete and position in ("position_dodge", "position_dodge2"):
        raise Unreadable("dodged bars on a continuous x scale are not read")

    bars = []
    for data, selector in rows:
        for i in range(len(data)):
            row = data.iloc[i]
            if stacked and linear:
                # A stacked segment's own value is its height, signed: `y` is
                # moved to the top of the stack, and to 0 for a bar below it.
                low, high = float(row["ymin"]), float(row["ymax"])
                value = high - low if low >= 0 else low - high
            else:
                # Taken back through the scale. A stack on a transformed scale
                # has only its top to go by, which is a bar's own value only
                # when nothing is stacked under it -- checked below.
                (value,) = panel.y.values([row["ymax" if stacked else "y"]])
            x = float(row["x"])
            bars.append(
                {
                    "position": round(x) if panel.x.discrete else x,
                    "offset": x - round(x),
                    "floor": float(row["ymin"]),
                    "value": _native(value),
                    "series": _series_key(data, i),
                    "selector": selector(i),
                }
            )

    positions = sorted({bar["position"] for bar in bars})
    labels = dict(zip(positions, panel.x.values(positions)))
    per_position: dict[Any, int] = {}
    for bar in bars:
        per_position[bar["position"]] = per_position.get(bar["position"], 0) + 1

    if all(count == 1 for count in per_position.values()):
        ordered = sorted(bars, key=lambda bar: bar["position"])
        return PlotnineLayer(
            panel.ax,
            PlotType.BAR,
            panel=panel,
            title=context.title(panel),
            axes=context.axes(),
            data=[{MaidrKey.X: labels[b["position"]], MaidrKey.Y: b["value"]}
                  for b in ordered],
            selectors=[b["selector"] for b in ordered],
            extra={MaidrKey.ORIENTATION: "vert"},
        )

    if position == "position_identity":
        raise Unreadable("overlapping bars (position='identity') are not read")
    if stacked and not linear:
        raise Unreadable("a stack on a transformed y scale is not read")

    series: dict[tuple, dict[Any, dict]] = {}
    for bar in bars:
        cells = series.setdefault(bar["series"], {})
        if bar["position"] in cells:
            raise Unreadable(
                "more than one bar of one series at one category; map what "
                "tells them apart to fill or colour"
            )
        cells[bar["position"]] = bar

    def order(key: tuple) -> float:
        # Bottom first for a stack, as matplotlib's stacked bars are listed;
        # left to right for a dodge. Either way, the order the eye meets them.
        cells = series[key].values()
        field = "floor" if stacked else "offset"
        return float(np.mean([cell[field] for cell in cells]))

    keys = sorted(series, key=order)
    data, grid = [], []
    for key in keys:
        name = _series_name(key)
        data.append(
            [
                {
                    MaidrKey.X: labels[p],
                    MaidrKey.Y: series[key][p]["value"] if p in series[key] else None,
                    MaidrKey.Z: name,
                }
                for p in positions
            ]
        )
        grid.append(
            [series[key][p]["selector"] if p in series[key] else None
             for p in positions]
        )
    return PlotnineLayer(
        panel.ax,
        segmented[position],
        panel=panel,
        title=context.title(panel),
        axes=context.axes(_series_label(context, groups)),
        data=data,
        selectors=grid,
        extra={MaidrKey.ORIENTATION: "vert"},
    )


def _hist(
    groups: list[DrawnGroup], panel: Panel, context: _Context, position: str
) -> PlotnineLayer:
    """``geom_histogram``: one series of bins, each with its edges."""
    if position not in ("position_stack", "position_identity"):
        raise Unreadable(f"a histogram placed with {position} is not read")
    if not panel.y.linear:
        raise Unreadable("a histogram on a transformed y scale is not read")
    rows = _collection_rows(groups, PolyCollection, "bins")
    bins = []
    for data, selector in rows:
        if len({_series_key(data, i) for i in range(len(data))}) > 1:
            raise Unreadable(
                "a histogram of several groups is not read; facet it instead"
            )
        for i in range(len(data)):
            row = data.iloc[i]
            bins.append((float(row["xmin"]), row, selector(i)))
    bins.sort(key=lambda b: b[0])

    points = []
    for _, row, _ in bins:
        x, low, high = panel.x.values([row["x"], row["xmin"], row["xmax"]])
        height = _native(float(row["ymax"]) - float(row["ymin"]))
        points.append(
            {
                MaidrKey.X: x,
                MaidrKey.Y: height,
                MaidrKey.X_MIN: low,
                MaidrKey.X_MAX: high,
                MaidrKey.Y_MIN: 0,
                MaidrKey.Y_MAX: height,
            }
        )
    return PlotnineLayer(
        panel.ax,
        PlotType.HIST,
        panel=panel,
        title=context.title(panel),
        axes=context.axes(),
        data=points,
        selectors=[b[2] for b in bins],
        extra={MaidrKey.ORIENTATION: "vert"},
    )


def _points(
    groups: list[DrawnGroup], panel: Panel, context: _Context, position: str
) -> PlotnineLayer:
    """``geom_point``: every point of the panel, one scatter layer.

    A discrete axis keeps ``x`` (or ``y``) as the numeric position the core
    does arithmetic on, and names the category in ``xLabel`` (``yLabel``), as
    the strip plot path does.
    """
    if position != "position_identity":
        # A jitter moves each point off its value, by a random amount.
        raise Unreadable(f"points placed with {position} are not read")
    points, gids = [], []
    for group in groups:
        collections = [a for a in group.artists if isinstance(a, PathCollection)]
        if not collections:
            raise Unreadable("the points were not drawn as a scatter")
        gids.extend(_gid(c) for c in collections)
        data = group.data
        xs, ys = data["x"].to_numpy(float), data["y"].to_numpy(float)
        x_values = panel.x.values(xs)
        y_values = panel.y.values(ys)
        for i in range(len(data)):
            point = {
                MaidrKey.X: float(xs[i]) if panel.x.discrete else x_values[i],
                MaidrKey.Y: float(ys[i]) if panel.y.discrete else y_values[i],
            }
            if panel.x.discrete:
                point[MaidrKey.X_LABEL] = x_values[i]
            if panel.y.discrete:
                point[MaidrKey.Y_LABEL] = y_values[i]
            points.append(point)
    selector = ", ".join(
        f"g[id='{gid}'] > path, g[id='{gid}'] > g > use" for gid in gids
    )
    return PlotnineLayer(
        panel.ax,
        PlotType.SCATTER,
        panel=panel,
        title=context.title(panel),
        axes=context.axes(),
        data=points,
        selectors=selector,
    )


def _lines(
    groups: list[DrawnGroup], panel: Panel, context: _Context, position: str
) -> PlotnineLayer:
    """``geom_line``: one series per group, in the order of ``x``."""
    if position != "position_identity":
        raise Unreadable(f"lines placed with {position} are not read")
    return _series_layer(groups, panel, context, PlotType.LINE, band=False)


def _smooth(
    groups: list[DrawnGroup], panel: Panel, context: _Context, position: str
) -> PlotnineLayer:
    """``geom_smooth``: the fitted curve per group, with its band when drawn."""
    if position != "position_identity":
        raise Unreadable(f"a smooth placed with {position} is not read")
    return _series_layer(groups, panel, context, PlotType.SMOOTH, band=True)


def _series_layer(
    groups: list[DrawnGroup],
    panel: Panel,
    context: _Context,
    plot_type: PlotType,
    *,
    band: bool,
) -> PlotnineLayer:
    """A line-like layer: one series per drawn group.

    A path of constant colour and width is one ``Line2D`` per group, and each
    series is highlighted through it. A path whose colour or width varies
    along it is one ``LineCollection`` of segments for every group; it is
    read all the same, without a highlight, since no element is one series.
    """
    series, selectors = [], []
    highlight = True
    for group in groups:
        lines = [a for a in group.artists if isinstance(a, Line2D)]
        for _, data in group.data.groupby("group", sort=True):
            series.append(data)
            if len(lines) == 1 and group.data["group"].nunique() == 1:
                selectors.append(f"g[id='{_gid(lines[0])}'] path")
            else:
                highlight = False

    names = [_series_key(data, 0) for data in series]
    named = len(series) > 1
    rows = []
    for data, key in zip(series, names):
        xs = panel.x.values(data["x"].to_numpy(float))
        ys = panel.y.values(data["y"].to_numpy(float))
        lows = highs = None
        if band and "ymin" in data and "ymax" in data:
            lows = panel.y.values(data["ymin"].to_numpy(float))
            highs = panel.y.values(data["ymax"].to_numpy(float))
        points = []
        for i, (x, y) in enumerate(zip(xs, ys)):
            point = {MaidrKey.X: x, MaidrKey.Y: y}
            if lows is not None and highs is not None:
                point[MaidrKey.Y_MIN] = lows[i]
                point[MaidrKey.Y_MAX] = highs[i]
            if named and key:
                point[MaidrKey.Z] = _series_name(key)
            points.append(point)
        rows.append(points)

    z = _series_label(context, groups) if named else None
    return PlotnineLayer(
        panel.ax,
        plot_type,
        panel=panel,
        title=context.title(panel),
        axes=context.axes(z),
        data=rows,
        selectors=selectors if highlight else None,
    )


def _boxes(
    groups: list[DrawnGroup], panel: Panel, context: _Context, position: str
) -> PlotnineLayer:
    """``geom_boxplot``: one box per group, from ``stat_boxplot``'s columns.

    plotnine draws each box as its outliers, one collection holding the upper
    and then the lower whisker, the box body and the median line; each part
    is named to the core through the element that drew it.
    """
    if panel.y.discrete:
        raise Unreadable("boxes on a discrete y scale are not read")
    boxes = []
    for group in groups:
        if len(group.data) != 1:
            raise Unreadable("a box was drawn from more than one row")
        outliers = [a for a in group.artists if isinstance(a, PathCollection)]
        lines = [a for a in group.artists if type(a) is LineCollection]
        bodies = [a for a in group.artists if type(a) is PolyCollection]
        if (
            len(lines) != 2
            or len(bodies) != 1
            or len(outliers) > 1
            or len(lines[0].get_paths()) != 2
        ):
            raise Unreadable("the boxes were not drawn as maidr expects")
        whiskers, median = (_gid(line) for line in lines)
        body = _gid(bodies[0])
        row = group.data.iloc[0]

        low, q1, q2, q3, high = panel.y.values(
            [row["ymin"], row["lower"], row["middle"], row["upper"], row["ymax"]]
        )
        values = np.asarray(row["outliers"], dtype=float)
        announced = panel.y.values(values) if len(values) else []
        # Ascending, and the selectors in the same order as the values.
        ascending = sorted(range(len(values)), key=lambda i: values[i])
        lower = [i for i in ascending if values[i] < float(row["ymin"])]
        upper = [i for i in ascending if values[i] > float(row["ymax"])]
        # Drawn in the order of the `outliers` list, one marker each; none at
        # all when the outliers are hidden (`outlier_shape=""`).
        marks = _gid(outliers[0]) if outliers else None

        def marker(index: int, gid: str | None = marks) -> list[str]:
            if gid is None:
                return []
            n = index + 1
            return [
                f"g[id='{gid}'] > path:nth-of-type({n}), "
                f"g[id='{gid}'] > g > use:nth-of-type({n})"
            ]

        (category,) = panel.x.values([row["x"]])
        key = _series_key(group.data, 0)
        boxes.append(
            (
                float(row["x"]),
                {
                    MaidrKey.Z: str(category),
                    MaidrKey.LOWER_OUTLIER: [announced[i] for i in lower],
                    MaidrKey.MIN: low,
                    MaidrKey.Q1: q1,
                    MaidrKey.Q2: q2,
                    MaidrKey.Q3: q3,
                    MaidrKey.MAX: high,
                    MaidrKey.UPPER_OUTLIER: [announced[i] for i in upper],
                },
                key,
                {
                    MaidrKey.LOWER_OUTLIER: [s for i in lower for s in marker(i)],
                    MaidrKey.MIN: f"g[id='{whiskers}'] > path:nth-of-type(2)",
                    MaidrKey.IQ: f"g[id='{body}'] > g > use, g[id='{body}'] > path",
                    MaidrKey.Q2: f"g[id='{median}'] > path",
                    MaidrKey.MAX: f"g[id='{whiskers}'] > path:nth-of-type(1)",
                    MaidrKey.UPPER_OUTLIER: [s for i in upper for s in marker(i)],
                },
            )
        )

    boxes.sort(key=lambda box: box[0])
    # Dodged boxes share a category; the group they stand for is named with it.
    shared = len({box[1][MaidrKey.Z] for box in boxes}) < len(boxes)
    if shared:
        for _, point, key, _ in boxes:
            if key:
                point[MaidrKey.Z] = f"{point[MaidrKey.Z]}, {_series_name(key)}"
    return PlotnineLayer(
        panel.ax,
        PlotType.BOX,
        panel=panel,
        title=context.title(panel),
        axes=context.axes(),
        data=[box[1] for box in boxes],
        selectors=[box[3] for box in boxes],
        extra={MaidrKey.ORIENTATION: "vert"},
    )


def _tiles(
    groups: list[DrawnGroup], panel: Panel, context: _Context, position: str
) -> PlotnineLayer:
    """``geom_tile``: a heatmap whose cells are the values ``fill`` maps.

    Rows are emitted top first, as the other heatmap paths emit them. The
    core reverses them so that its row 0 is the bottom one, and reads the
    selector grid in that order -- so the grid is written bottom first.
    """
    if position != "position_identity":
        raise Unreadable(f"tiles placed with {position} are not read")
    rows = _collection_rows(groups, PolyCollection, "tiles")
    cells: dict[tuple[float, float], tuple[Any, str]] = {}
    for data, selector in rows:
        if RAW + "fill" not in data:
            raise Unreadable("tiles without a fill mapping are not a heatmap")
        values = data[RAW + "fill"]
        if not np.issubdtype(np.asarray(values).dtype, np.number):
            raise Unreadable("tiles filled by a discrete variable are not read")
        for i in range(len(data)):
            at = (float(data["x"].iloc[i]), float(data["y"].iloc[i]))
            if at in cells:
                raise Unreadable("two tiles at one cell are not read")
            cells[at] = (_native(values.iloc[i]), selector(i))

    xs = sorted({x for x, _ in cells})
    ys = sorted({y for _, y in cells}, reverse=True)
    points = [[cells[(x, y)][0] if (x, y) in cells else None for x in xs] for y in ys]
    grid = [
        [cells[(x, y)][1] if (x, y) in cells else None for x in xs]
        for y in reversed(ys)
    ]
    return PlotnineLayer(
        panel.ax,
        PlotType.HEAT,
        panel=panel,
        title=context.title(panel),
        axes=context.axes(context.label("fill", "Z")),
        data={
            MaidrKey.X: panel.x.values(xs),
            MaidrKey.Y: panel.y.values(ys),
            MaidrKey.POINTS: points,
        },
        selectors=grid,
    )


_READERS: dict[str, Callable[..., PlotnineLayer]] = {
    "geom_point": _points,
    "geom_line": _lines,
    "geom_boxplot": _boxes,
    "geom_tile": _tiles,
    "geom_smooth": _smooth,
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _collection_rows(
    groups: list[DrawnGroup], kind: type, what: str
) -> list[tuple[Any, Callable[[int], str]]]:
    """
    Each drawn frame with a selector for the element that drew its row ``i``.

    A rectangle geom draws every row of a panel into one collection, one path
    per row in the frame's order, so row ``i`` is the collection's ``i+1``-th
    path.
    """
    rows = []
    for group in groups:
        collections = [a for a in group.artists if type(a) is kind]
        if len(collections) != 1 or len(collections[0].get_paths()) != len(
            group.data
        ):
            raise Unreadable(f"the {what} were not drawn as maidr expects")
        gid = _gid(collections[0])

        def selector(i: int, gid: str = gid) -> str:
            return f"g[id='{gid}'] > path:nth-of-type({i + 1})"

        rows.append((group.data.reset_index(drop=True), selector))
    return rows


def _gid(artist: Any) -> str:
    """The artist's gid, minting one; matplotlib writes it as its ``<g id>``."""
    gid = artist.get_gid()
    if gid is None:
        gid = f"maidr-{uuid.uuid4()}"
        artist.set_gid(gid)
    return str(gid)


def _raw_columns(data: Any) -> list[str]:
    return sorted(c for c in data.columns if isinstance(c, str) and c.startswith(RAW))


def _series_key(data: Any, i: int) -> tuple:
    """What tells row ``i`` 's series apart: its mapped aesthetics' values."""
    return tuple(str(data[column].iloc[i]) for column in _raw_columns(data))


def _series_name(key: tuple) -> str:
    """A series' name: its aesthetics' values, each once (``fill`` and
    ``colour`` mapped to one variable name it the same way twice)."""
    return ", ".join(dict.fromkeys(key))


def _series_label(context: _Context, groups: list[DrawnGroup]) -> str | None:
    """The legend title(s) of the aesthetics that name the series."""
    columns = _raw_columns(groups[0].data) if groups else []
    names = [context.label(column[len(RAW):]) for column in columns]
    names = [name for name in names if name]
    return ", ".join(dict.fromkeys(names)) or None


def _finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _native(value: Any) -> Any:
    """A JSON-ready value: a float, an ISO date or time, a string, or None."""
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return number if np.isfinite(number) else None
    if hasattr(value, "isoformat"):
        import pandas as pd

        stamp = pd.Timestamp(value)
        if stamp.tzinfo is not None:
            stamp = stamp.tz_localize(None)
        if stamp == stamp.normalize():
            return stamp.date().isoformat()
        return stamp.isoformat()
    return str(value)
