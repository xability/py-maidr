"""What an Excel 2016 chart part says.

Excel 2016 added eight chart types -- histogram, Pareto, box and whisker,
waterfall, funnel, treemap, sunburst and map -- and writes them in parts of
their own, ``xl/charts/chartExN.xml`` in the ``cx`` namespace, rather than as
DrawingML. A series there does not hold its values: it names a data block of
the part's ``chartData``, which keeps the cached values in dimensions -- the
categories, with one level per tier of a hierarchy, and the numbers. As with
DrawingML, the cache is what is read, and cells only for what it leaves out.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterator

from maidr.excel.chartxml import (
    _MAX_POINTS,
    _MAX_UNCACHED,
    A,
    Axis,
    Binning,
    Cells,
    ChartSpec,
    Group,
    Range,
    Series,
    _category_label,
    _color,
    _default_color,
    _number,
    _text_value,
    parse_range,
    sums_categories,
)

NS_CX = "http://schemas.microsoft.com/office/drawing/2014/chartex"
CX = f"{{{NS_CX}}}"

#: The chart type each series layout is, by ``layoutId``.
_LAYOUTS = {
    "clusteredColumn": "histogram",
    "paretoLine": "pareto",
    "boxWhisker": "box",
    "waterfall": "waterfall",
    "funnel": "funnel",
    "treemap": "treemap",
    "sunburst": "sunburst",
    "regionMap": "region",
}

#: The dimension types that hold a series' numbers, by chart type.
_VALUES = ("val", "size", "colorVal")

#: The most levels of a hierarchy read; a part claiming more is damaged.
_MAX_LEVELS = 32
#: The most points read across all the levels of one dimension.
_MAX_CELLS = 4 * _MAX_POINTS


def layout_name(root: Any) -> str | None:
    """
    The chart type an Excel 2016 chart part draws.

    Parameters
    ----------
    root : lxml.etree._Element
        The part's root element, ``cx:chartSpace``.

    Returns
    -------
    str or None
        ``"histogram"``, ``"pareto"``, ``"box"``, ``"waterfall"``,
        ``"funnel"``, ``"treemap"``, ``"sunburst"`` or ``"region"``, or
        ``None`` for a layout maidr does not know.
    """
    layouts = [s.get("layoutId", "") for s in root.iter(f"{CX}series")]
    if "paretoLine" in layouts:
        return "pareto"
    return next((_LAYOUTS[x] for x in layouts if x in _LAYOUTS), None)


def wanted_cells(root: Any, names: dict[str, str]) -> Iterator[tuple[str, int, int]]:
    """
    The cells an Excel 2016 chart part needs read from the sheet.

    Parameters
    ----------
    root : lxml.etree._Element
        The part's root element.
    names : dict
        The workbook's defined names, which the part's formulas go through.

    Yields
    ------
    tuple
        ``(sheet, row, column)`` of the header cell above the category range,
        which names the categories, and of every cell of a range the part
        keeps no copy of.
    """
    for dimension in _dimensions(root):
        area = _area(dimension, names)
        if area is None:
            continue
        if dimension.get("type") == "cat":
            header = area.header()
            if header is not None:
                yield (area.sheet, *header)
        if dimension.find(f"{CX}lvl") is None and area.size() <= _MAX_UNCACHED:
            yield from ((area.sheet, r, c) for r, c in area.positions())


def read_chartex(
    root: Any,
    *,
    cells: Cells,
    theme: dict[str, str],
    date1904: bool,
    names: dict[str, str],
) -> ChartSpec:
    """
    Read an Excel 2016 chart part.

    Parameters
    ----------
    root : lxml.etree._Element
        The part's root element, ``cx:chartSpace``.
    cells : callable
        ``cells(sheet, row, column)`` returns the cell there, for the cells
        :func:`wanted_cells` named, or ``None``.
    theme : dict
        The workbook's theme colors.
    date1904 : bool
        Whether the workbook counts dates from 1904 rather than 1900.
    names : dict
        The workbook's defined names.

    Returns
    -------
    ChartSpec
        The chart as one group of its type, or with no group and the type
        named in ``unread`` when maidr does not know the layout.
    """
    chart = root.find(f"{CX}chart")
    kind = layout_name(root)
    if chart is None:
        return ChartSpec(None, (), None, ())
    if kind is None:
        layouts = {s.get("layoutId", "") for s in root.iter(f"{CX}series")}
        return ChartSpec(None, (), None, tuple(sorted(layouts - {""})))
    blocks = {
        data.get("id", ""): data for data in root.iterfind(f"{CX}chartData/{CX}data")
    }
    axes = {axis.get("id", ""): axis for axis in chart.iter(f"{CX}axis")}
    elements = [
        s
        for s in chart.iterfind(f"{CX}plotArea/{CX}plotAreaRegion/{CX}series")
        if s.get("layoutId") != "paretoLine" and s.get("hidden") not in ("1", "true")
    ]

    series = []
    layout = None
    header = None
    value_format = None
    for index, element in enumerate(elements):
        block = blocks.get(_child_val(element, "dataId") or "")
        if block is None:
            continue
        categories = _find_dimension(block, ("cat",))
        values = _find_dimension(block, _VALUES)
        paths = _paths(categories, cells, names, date1904)
        numbers = [_number(v) for v in _numbers(values, cells, names)]
        count = max(len(paths), len(numbers))
        if categories is None and kind in ("waterfall", "funnel"):
            # Excel numbers the steps of a chart that names none.
            paths = [(str(i + 1),) for i in range(count)]
        paths += [()] * (count - len(paths))
        numbers += [None] * (count - len(numbers))
        if header is None and categories is not None:
            area = _area(categories, names)
            # A range of several columns holds the levels of a hierarchy, and
            # the header above the innermost does not name the outer ones.
            flat = area is not None and (
                area.first_row == area.last_row or area.first_column == area.last_column
            )
            spot = area.header() if flat else None
            cell = cells(area.sheet, *spot) if spot is not None else None
            header = _text_value(cell.value) if cell is not None else None
        if layout is None:
            layout = element.find(f"{CX}layoutPr")
        if value_format is None and values is not None:
            value_format = _level_format(values)
        colors = dict(_default_point_colors(kind, paths, numbers, layout, theme))
        colors.update(_point_colors(element, theme))
        series.append(
            Series(
                name=_series_name(element),
                categories=tuple(" / ".join(path) or None for path in paths),
                values=tuple(numbers),
                color=_color(element.find(f"{CX}spPr/{A}solidFill"), theme)
                or _default_color(index, theme),
                point_colors=tuple(sorted(colors.items())),
                line=False,
                marker=False,
                paths=tuple(paths),
            )
        )
    if not series:
        return ChartSpec(_title(chart), (), _legend(chart), ())
    if kind == "pareto":
        # The running share is worked out from the columns; only the line's
        # color is the part's, the second accent unless it says otherwise.
        line = next(
            (s for s in chart.iter(f"{CX}series") if s.get("layoutId") == "paretoLine"),
            None,
        )
        fill = line.find(f"{CX}spPr/{A}ln/{A}solidFill") if line is not None else None
        series.append(
            Series(
                name=None,
                categories=(),
                values=(),
                color=_color(fill, theme) or _default_color(1, theme),
                point_colors=(),
                line=True,
                marker=False,
            )
        )

    first = elements[0]
    binning = _binning(layout) if kind in ("histogram", "pareto") else None
    x_element, y_element = _series_axes(first, axes)
    x_axis = _axis(x_element, header, "b") if x_element is not None else None
    if y_element is not None:
        y_axis = _axis(y_element, None, "l")
        if y_axis.number_format is None and not _counted(kind, binning, series[0]):
            y_axis = replace(y_axis, number_format=value_format)
    else:
        # A funnel, a treemap, a sunburst or a map draws no value axis; its
        # values are written as their cells are.
        y_axis = Axis(None, None, True, "l", None, None, False, value_format)
    group = Group(
        kind=kind,
        horizontal=False,
        grouping="clustered",
        series=tuple(series),
        x_axis=x_axis,
        y_axis=y_axis,
        category_name=x_axis.label if x_axis is not None else header,
        secondary=False,
        first_slice_angle=0.0,
        hole_size=None,
        binning=binning,
        quartiles=_attribute(layout, "statistics", "quartileMethod", "exclusive"),
        mean_marker=_attribute(layout, "visibility", "meanMarker", "1")
        in ("1", "true"),
        totals=_totals(layout),
    )
    return ChartSpec(_title(chart), (group,), _legend(chart), ())


def _counted(kind: str, binning: Binning | None, series: Series) -> bool:
    """
    Whether a chart's value axis counts values rather than adding them up: a
    histogram's or a Pareto chart's bins, but not its categories, whose values
    are summed and keep their format.
    """
    return kind in ("histogram", "pareto") and not sums_categories(binning, series)


def _dimensions(root: Any) -> Iterator[Any]:
    for data in root.iterfind(f"{CX}chartData/{CX}data"):
        for dimension in data:
            if dimension.tag in (f"{CX}strDim", f"{CX}numDim"):
                yield dimension


def _find_dimension(block: Any, types: tuple[str, ...]) -> Any:
    for dimension in block:
        if (
            dimension.tag in (f"{CX}strDim", f"{CX}numDim")
            and dimension.get("type") in types
        ):
            return dimension
    return None


def _area(dimension: Any, names: dict[str, str]) -> Range | None:
    """The range a dimension's formula names, through a defined name if need be."""
    formula = (dimension.findtext(f"{CX}f") or "").strip()
    return parse_range(names.get(formula, formula))


def _levels(dimension: Any, cells: Cells, names: dict[str, str]) -> list[list[Any]]:
    """
    A dimension's levels, innermost first, one entry per point, ``None`` for
    a gap: its cached copy, or the cells of its range, a column per level.
    """
    if dimension is None:
        return []
    cached = dimension.findall(f"{CX}lvl")[:_MAX_LEVELS]
    if cached:
        budget = _MAX_CELLS // len(cached)
        out = []
        for level in cached:
            # An index and its value are read together, so a point whose
            # index is damaged costs that point and moves no other.
            pairs = [
                (int(pt.get("idx", "")), pt.text)
                for pt in level.findall(f"{CX}pt")
                if pt.get("idx", "").isdigit()
            ]
            count = min(max((i for i, _ in pairs), default=-1) + 1, _MAX_POINTS, budget)
            values: list[Any] = [None] * count
            for index, text in pairs:
                if index < count:
                    values[index] = text
            out.append(values)
        return out
    area = _area(dimension, names)
    if area is None or area.size() > _MAX_UNCACHED:
        return []
    # Laid out down the sheet, each column is a level, the rightmost the
    # innermost; across it, each row is.
    down = area.last_row - area.first_row >= area.last_column - area.first_column
    if down:
        lines = [
            [(r, c) for r in range(area.first_row, area.last_row + 1)]
            for c in range(area.last_column, area.first_column - 1, -1)
        ]
    else:
        lines = [
            [(r, c) for c in range(area.first_column, area.last_column + 1)]
            for r in range(area.last_row, area.first_row - 1, -1)
        ]
    out = []
    for line in lines[:_MAX_LEVELS]:
        values = []
        for r, c in line:
            cell = cells(area.sheet, r, c)
            values.append(cell.value if cell is not None else None)
        out.append(values)
    return out


def _paths(
    dimension: Any, cells: Cells, names: dict[str, str], date1904: bool
) -> list[tuple[str, ...]]:
    """Each point's category, as its levels outermost first, blanks left out."""
    levels = _levels(dimension, cells, names)
    if not levels:
        return []
    numeric = dimension.tag == f"{CX}numDim"
    first = dimension.find(f"{CX}lvl")
    code = first.get("formatCode") if first is not None else None
    count = max(len(level) for level in levels)
    paths = []
    for index in range(count):
        parts = []
        for level in reversed(levels):
            value = level[index] if index < len(level) else None
            if numeric and isinstance(value, str):
                value = _number(value)
            label = _category_label(value, code, False, date1904)
            if label is not None and label.strip():
                parts.append(label)
        paths.append(tuple(parts))
    return paths


def _numbers(dimension: Any, cells: Cells, names: dict[str, str]) -> list[Any]:
    levels = _levels(dimension, cells, names)
    return levels[0] if levels else []


def _level_format(dimension: Any) -> str | None:
    """The number format a numeric dimension's cached copy records."""
    level = dimension.find(f"{CX}lvl")
    code = level.get("formatCode") if level is not None else None
    return None if not code or code.lower() == "general" else code


def _default_point_colors(
    kind: str,
    paths: list[tuple[str, ...]],
    numbers: list[float | None],
    layout: Any,
    theme: dict[str, str],
) -> Iterator[tuple[int, str]]:
    """
    The colors Excel's default style gives each point, where it colors points
    rather than series: a waterfall's increases, decreases and totals in the
    first three accents, and a treemap's or a sunburst's points in the accent
    of the branch they are on.
    """
    if kind == "waterfall":
        totals = set(_totals(layout))
        for index, value in enumerate(numbers):
            if value is None:
                continue
            accent = 2 if index in totals else (1 if value < 0 else 0)
            color = _default_color(accent, theme)
            if color is not None:
                yield index, color
    elif kind in ("treemap", "sunburst"):
        branches: dict[str, int] = {}
        for index, path in enumerate(paths):
            if not path:
                continue
            branch = branches.setdefault(path[0], len(branches))
            color = _default_color(branch, theme)
            if color is not None:
                yield index, color


def _series_name(element: Any) -> str | None:
    text = element.findtext(f"{CX}tx/{CX}txData/{CX}v")
    return text.strip() or None if text else None


def _point_colors(element: Any, theme: dict[str, str]) -> Iterator[tuple[int, str]]:
    for point in element.iterfind(f"{CX}dataPt"):
        color = _color(point.find(f"{CX}spPr/{A}solidFill"), theme)
        index = point.get("idx", "")
        if color is not None and index.isdigit():
            yield int(index), color


def _series_axes(element: Any, axes: dict[str, Any]) -> tuple[Any, Any]:
    """The category axis and the value axis a series is drawn against."""
    own = [axes[v] for v in _child_vals(element, "axisId") if v in axes] or list(
        axes.values()
    )
    x = next((a for a in own if a.find(f"{CX}catScaling") is not None), None)
    y = next((a for a in own if a.find(f"{CX}valScaling") is not None), None)
    return x, y


def _axis(element: Any, fallback: str | None, position: str) -> Axis:
    title = _text(element.find(f"{CX}title"))
    scaling = element.find(f"{CX}valScaling")
    fmt = element.find(f"{CX}numFmt")
    code = None
    if fmt is not None and fmt.get("sourceLinked") not in ("1", "true"):
        code = fmt.get("formatCode")
    return Axis(
        title=title,
        label=title or fallback,
        hidden=element.get("hidden") in ("1", "true"),
        position=position,
        minimum=_limit(scaling, "min"),
        maximum=_limit(scaling, "max"),
        reversed=False,
        number_format=None if not code or code.lower() == "general" else code,
    )


def _limit(scaling: Any, name: str) -> float | None:
    if scaling is None:
        return None
    value = scaling.get(name, "auto")
    return None if value == "auto" else _number(value)


def _binning(layout: Any) -> Binning | None:
    if layout is None:
        return None
    if layout.find(f"{CX}aggregation") is not None:
        return Binning(by_category=True)
    binning = layout.find(f"{CX}binning")
    if binning is None:
        # The part says nothing of its bins: Excel decides by the categories.
        return None
    count = _number(_child_val(binning, "binCount"))
    return Binning(
        size=_positive(_number(_child_val(binning, "binSize"))),
        count=int(count) if count is not None and count >= 1 else None,
        underflow=_number(binning.get("underflow", "auto")),
        overflow=_number(binning.get("overflow", "auto")),
        closed=binning.get("intervalClosed", "r"),
    )


def _totals(layout: Any) -> tuple[int, ...]:
    """The points of a waterfall set as totals, by index."""
    if layout is None:
        return ()
    found = (idx.get("val", "") for idx in layout.iterfind(f"{CX}subtotals/{CX}idx"))
    return tuple(sorted({int(v) for v in found if v.isdigit()}))


def _positive(value: float | None) -> float | None:
    return value if value is not None and value > 0 else None


def _attribute(layout: Any, child: str, name: str, default: str) -> str:
    element = layout.find(f"{CX}{child}") if layout is not None else None
    return element.get(name, default) if element is not None else default


def _title(chart: Any) -> str | None:
    return _text(chart.find(f"{CX}title"))


def _text(element: Any) -> str | None:
    """The text of a title, from its cached value or its rich text."""
    if element is None:
        return None
    cached = element.findtext(f"{CX}tx/{CX}txData/{CX}v")
    if cached and cached.strip():
        return cached.strip()
    rich = element.find(f"{CX}tx/{CX}rich")
    if rich is None:
        return None
    lines = ["".join(t.text or "" for t in p.iter(f"{A}t")) for p in rich.iter(f"{A}p")]
    text = " ".join(line.strip() for line in lines if line.strip())
    return text or None


def _legend(chart: Any) -> str | None:
    legend = chart.find(f"{CX}legend")
    return None if legend is None else legend.get("pos", "t")


def _child_val(element: Any, name: str) -> str | None:
    child = element.find(f"{CX}{name}") if element is not None else None
    return child.get("val") if child is not None else None


def _child_vals(element: Any, name: str) -> list[str]:
    return [child.get("val", "") for child in element.iterfind(f"{CX}{name}")]
