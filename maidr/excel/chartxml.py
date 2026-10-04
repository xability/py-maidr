"""What a chart part says: its type, its series, its axes and its title.

A chart part (``xl/charts/chartN.xml``) is DrawingML, the chart format Word
and PowerPoint share with Excel. Its plot area holds one chart group per chart
type -- a combo chart has a bar group and a line group -- and each group holds
its series. A series names its data with a formula such as
``Sales!$B$2:$B$5`` and, in every file Excel saves, also carries a copy of the
values as they were at that save: the cache. The cache is what this module
reads, because it is what Excel drew. Cells are read only for what the part
leaves out: the cache of a file another program wrote without one, and the
header cell that names a category range when the axis has no title.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterator

from maidr.excel.cells import MAX_POINTS, MAX_UNCACHED, Cells, parse_range
from maidr.excel.colors import default_color, fill_color
from maidr.excel.formats import as_number, as_text, category_label
from maidr.excel.package import NS_A
from maidr.excel.spec import Axis, ChartSpec, Group, Series

NS_C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
C = f"{{{NS_C}}}"
A = f"{{{NS_A}}}"

#: Chart groups maidr reads, by element name, and the kind each is drawn as.
#: The 3-D groups read as their flat counterparts.
_KINDS = {
    "barChart": "bar",
    "bar3DChart": "bar",
    "lineChart": "line",
    "line3DChart": "line",
    "pieChart": "pie",
    "pie3DChart": "pie",
    "doughnutChart": "doughnut",
    "ofPieChart": "ofpie",
    "scatterChart": "scatter",
    "bubbleChart": "bubble",
    "areaChart": "area",
    "area3DChart": "area",
    "radarChart": "radar",
    "stockChart": "stock",
    "surfaceChart": "surface",
    "surface3DChart": "surface",
}

#: The kinds whose x values are numbers, read from ``c:xVal``.
_XY_KINDS = ("scatter", "bubble")

#: How many points a pie-of-pie moves to its second plot when the part does
#: not say: Excel's default, the last three.
_SECOND_PLOT_POINTS = 3


def wanted_cells(root: Any) -> Iterator[tuple[str, int, int]]:
    """
    The cells a chart part needs read from the sheet.

    Parameters
    ----------
    root : lxml.etree._Element
        The chart part's root element.

    Yields
    ------
    tuple
        ``(sheet, row, column)`` of each header cell naming a category range,
        of every cell of a series range that has no cached copy, and of the
        first cell of a numeric range whose copy does not say how its numbers
        are formatted -- as programs other than Excel write it -- because the
        cell's own format says whether they are dates, percentages or money.
    """
    for ser in root.iter(f"{C}ser"):
        for tag in ("tx", "cat", "val", "xVal", "yVal", "bubbleSize"):
            source = ser.find(f"{C}{tag}")
            if source is None:
                continue
            area = parse_range(source.findtext(f".//{C}f"))
            if area is None:
                continue
            if tag in ("cat", "xVal", "bubbleSize"):
                header = area.header()
                if header is not None:
                    yield (area.sheet, *header)
            if _cache(source) is None:
                if area.size() <= MAX_UNCACHED:
                    yield from ((area.sheet, r, c) for r, c in area.positions())
            elif (
                _cached_format(source) is None and source.find(f"{C}numRef") is not None
            ):
                yield area.sheet, area.first_row, area.first_column


def read_chart(
    root: Any,
    *,
    cells: Cells,
    theme: dict[str, str],
    date1904: bool,
) -> ChartSpec:
    """
    Read a chart part.

    Parameters
    ----------
    root : lxml.etree._Element
        The chart part's root element, ``c:chartSpace``.
    cells : callable
        ``cells(sheet, row, column)`` returns the :class:`Cell` there, for the
        cells :func:`wanted_cells` named, or ``None``.
    theme : dict
        The theme colors, from :meth:`OpcPackage.theme_colors`.
    date1904 : bool
        Whether the workbook counts dates from 1904 rather than 1900.

    Returns
    -------
    ChartSpec
        The chart, with every group maidr reads and the names of those it
        does not.
    """
    chart = root.find(f"{C}chart")
    if chart is None:
        return ChartSpec(None, (), None, ())
    own_1904 = root.find(f"{C}date1904")
    if own_1904 is not None:
        date1904 = own_1904.get("val", "1") in ("1", "true")
    plot_area = chart.find(f"{C}plotArea")
    blanks = _val(chart, "dispBlanksAs", "gap")
    axes = {}
    if plot_area is not None:
        for element in plot_area:
            if element.tag in (f"{C}catAx", f"{C}valAx", f"{C}dateAx", f"{C}serAx"):
                axes[_val(element, "axId")] = element

    groups: list[Group] = []
    unread: list[str] = []
    for element in plot_area if plot_area is not None else ():
        if not isinstance(element.tag, str) or not element.tag.startswith(C):
            continue
        name = element.tag[len(C) :]
        if not name.endswith("Chart"):
            continue
        kind = _KINDS.get(name)
        if kind is None:
            unread.append(name)
            continue
        grouping = _val(element, "grouping", "standard")
        group = _read_group(
            element, kind, grouping, axes, cells, theme, date1904, blanks
        )
        if group.series:
            groups.append(group)

    if groups and all(group.secondary for group in groups):
        groups = [replace(group, secondary=False) for group in groups]
    series = [s for group in groups for s in group.series]
    return ChartSpec(
        title=_chart_title(chart, series),
        groups=tuple(groups),
        legend=_legend(chart),
        unread=tuple(unread),
    )


def _read_group(
    element: Any,
    kind: str,
    grouping: str,
    axes: dict[str, Any],
    cells: Cells,
    theme: dict[str, str],
    date1904: bool,
    blanks: str,
) -> Group:
    horizontal = kind == "bar" and _val(element, "barDir", "col") == "bar"
    group_axes = [axes[a] for a in _vals(element, "axId") if a in axes]
    if kind in _XY_KINDS:
        x_element = next(
            (a for a in group_axes if _val(a, "axPos") in ("b", "t")), None
        )
        y_element = next((a for a in group_axes if a is not x_element), None)
    else:
        x_element = next(
            (a for a in group_axes if a.tag in (f"{C}catAx", f"{C}dateAx")), None
        )
        y_element = next((a for a in group_axes if a.tag == f"{C}valAx"), None)
    depth_element = next((a for a in group_axes if a.tag == f"{C}serAx"), None)
    dates = x_element is not None and x_element.tag == f"{C}dateAx"

    raw = sorted(
        element.findall(f"{C}ser"),
        key=lambda ser: int(_val(ser, "order", _val(ser, "idx", "0"))),
    )
    scatter_style = _val(element, "scatterStyle", "lineMarker")
    radar_style = _val(element, "radarStyle", "marker")
    group_markers = _val(element, "marker", "1") in ("1", "true")
    vary_colors = _val(element, "varyColors", "0") in ("1", "true")
    series = []
    for ser in raw:
        index = int(_val(ser, "idx", "0"))
        name = _series_name(ser, cells)
        if kind in _XY_KINDS:
            x_source, y_source = ser.find(f"{C}xVal"), ser.find(f"{C}yVal")
        else:
            x_source, y_source = ser.find(f"{C}cat"), ser.find(f"{C}val")
        values = [as_number(v) for v in _points(y_source, cells)]
        if blanks == "zero" and kind in ("line", "scatter", "area", "radar"):
            values = [0.0 if v is None else v for v in values]
        x_points = _points(x_source, cells)
        x_format = _explicit_format(x_element) or _format_code(x_source, cells)
        if kind in _XY_KINDS:
            # Excel plots a scatter series against 1, 2, 3, ... when its x
            # values are missing or are text.
            numbers = [as_number(v) for v in x_points]
            if not x_points or any(
                isinstance(v, str) and n is None for v, n in zip(x_points, numbers)
            ):
                numbers = [float(i + 1) for i in range(len(values))]
            categories = numbers
        else:
            categories = [
                category_label(v, x_format, dates, date1904) for v in x_points
            ] or [str(i + 1) for i in range(len(values))]
        sizes = (
            [as_number(v) for v in _points(ser.find(f"{C}bubbleSize"), cells)]
            if kind == "bubble"
            else []
        )
        count = max(len(categories), len(values))
        categories += [None] * (count - len(categories))
        values += [None] * (count - len(values))
        if sizes:
            sizes += [None] * (count - len(sizes))
        line = kind in ("line", "scatter", "radar") and not _no_line(ser)
        if kind == "scatter" and scatter_style in ("marker", "none"):
            line = False
        symbol = ser.find(f"{C}marker/{C}symbol")
        shown = symbol is None or symbol.get("val") != "none"
        if kind == "radar":
            marker = shown and radar_style == "marker"
        else:
            marker = shown and (kind == "scatter" or group_markers)
        point_colors = dict(_point_colors(ser, theme))
        if kind in ("pie", "doughnut", "ofpie") and vary_colors:
            # A pie's slices take the theme accents in turn, as series do.
            for point in range(count):
                color = default_color(point, theme)
                if color is not None:
                    point_colors.setdefault(point, color)
        series.append(
            Series(
                name=name,
                categories=tuple(categories),
                values=tuple(values),
                color=_series_color(ser, kind, theme) or default_color(index, theme),
                point_colors=tuple(sorted(point_colors.items())),
                line=line,
                marker=marker,
                sizes=tuple(sizes),
            )
        )

    header = _header_text(raw, "xVal" if kind in _XY_KINDS else "cat", cells)
    x_axis = (
        _axis(x_element, raw, "x", header, cells) if x_element is not None else None
    )
    y_axis = _axis(y_element, raw, "y", None, cells) if y_element is not None else None
    position = y_axis.position if y_axis is not None else ""
    style = None
    if kind == "radar":
        style = radar_style
    elif kind == "ofpie":
        style = _val(element, "ofPieType", "pie")
    elif kind == "stock" and element.find(f"{C}upDownBars") is not None:
        style = "updown"
    elif kind == "bubble":
        style = _val(element, "sizeRepresents", "area")
    return Group(
        kind=kind,
        horizontal=horizontal,
        grouping="clustered" if grouping == "standard" and kind == "bar" else grouping,
        series=tuple(series),
        x_axis=x_axis,
        y_axis=y_axis,
        category_name=x_axis.label if x_axis is not None else header,
        secondary=position in (("t",) if horizontal else ("r",)),
        first_slice_angle=float(_val(element, "firstSliceAng", "0")),
        hole_size=float(_val(element, "holeSize", "50"))
        if kind == "doughnut"
        else None,
        style=style,
        second_plot=_second_plot(element, series[0].values)
        if kind == "ofpie" and series
        else (),
        bubble_scale=as_number(_val(element, "bubbleScale")) or 100.0,
        series_name=_title_text(depth_element.find(f"{C}title"))
        if depth_element is not None
        else None,
        size_name=_header_text(raw, "bubbleSize", cells) if kind == "bubble" else None,
    )


def _second_plot(element: Any, values: tuple[float | None, ...]) -> tuple[int, ...]:
    """
    The points a pie-of-pie or bar-of-pie moves to its second plot.

    By position, the last ones; by value or by percentage, those below the
    split; by a custom split, those the part lists. A split that would leave
    the first pie empty keeps its first point there.
    """
    split = _val(element, "splitType", "auto")
    threshold = as_number(_val(element, "splitPos"))
    sized = [(i, v) for i, v in enumerate(values) if v is not None and v > 0]
    if split == "cust":
        custom = element.find(f"{C}custSplit")
        listed = (
            {int(v) for v in _vals(custom, "secondPiePt") if v.isdigit()}
            if custom is not None
            else set()
        )
        chosen = [i for i, _ in sized if i in listed]
    elif split == "val":
        chosen = [i for i, v in sized if threshold is not None and v < threshold]
    elif split == "percent":
        total = sum(v for _, v in sized)
        chosen = [
            i for i, v in sized if threshold is not None and 100 * v / total < threshold
        ]
    else:
        # "pos", and "auto", which is Excel's default split: by position.
        last = int(threshold) if threshold is not None else _SECOND_PLOT_POINTS
        first = len(values) - max(0, last)
        chosen = [i for i, _ in sized if i >= first]
    if sized and len(chosen) == len(sized):
        chosen = chosen[1:]
    return tuple(chosen)


def _axis(
    element: Any, series: list[Any], role: str, fallback: str | None, cells: Cells
) -> Axis:
    title = _title_text(element.find(f"{C}title"))
    scaling = element.find(f"{C}scaling")
    # Only a value axis has number labels to format; a category axis' labels
    # are already written out as Excel shows them.
    number_format = None
    if element.tag == f"{C}valAx":
        number_format = _explicit_format(element)
        if number_format is None and series:
            tags = ("xVal",) if role == "x" else ("val", "yVal")
            source = next(
                (s for s in (series[0].find(f"{C}{t}") for t in tags) if s is not None),
                None,
            )
            number_format = _format_code(source, cells)
    return Axis(
        title=title,
        label=title or fallback,
        hidden=_val(element, "delete", "0") in ("1", "true"),
        position=_val(element, "axPos", "b"),
        minimum=as_number(_val(scaling, "min")) if scaling is not None else None,
        maximum=as_number(_val(scaling, "max")) if scaling is not None else None,
        reversed=scaling is not None and _val(scaling, "orientation") == "maxMin",
        number_format=number_format,
    )


def _header_text(series: list[Any], tag: str, cells: Cells) -> str | None:
    """
    The header cell above (or left of) the first series' range of ``tag``:
    its categories, or a bubble chart's sizes.
    """
    if not series:
        return None
    area = parse_range(series[0].findtext(f"{C}{tag}//{C}f"))
    header = area.header() if area is not None else None
    if header is None:
        return None
    cell = cells(area.sheet, *header)
    return as_text(cell.value) if cell is not None else None


def _chart_title(chart: Any, series: list[Series]) -> str | None:
    """
    The title Excel shows on the chart.

    A chart with one named series and no title of its own is titled with the
    series' name, unless the title was deleted; a title element with no text
    is Excel's placeholder, which a reader has no use for.
    """
    element = chart.find(f"{C}title")
    if element is not None:
        text = _title_text(element)
        if text is not None:
            return text
    if _val(chart, "autoTitleDeleted", "0") in ("1", "true"):
        return None
    if len(series) == 1 and series[0].name:
        return series[0].name
    return None


def _legend(chart: Any) -> str | None:
    legend = chart.find(f"{C}legend")
    if legend is None:
        return None
    return _val(legend, "legendPos", "r")


def _title_text(title: Any) -> str | None:
    if title is None:
        return None
    tx = title.find(f"{C}tx")
    if tx is None:
        return None
    rich = tx.find(f"{C}rich")
    if rich is not None:
        lines = [
            "".join(t.text or "" for t in p.iter(f"{A}t")) for p in rich.iter(f"{A}p")
        ]
        text = " ".join(line.strip() for line in lines if line.strip())
        return text or None
    cached = _points(tx.find(f"{C}strRef"), None)
    return as_text(cached[0]) if cached else None


def _series_name(ser: Any, cells: Cells) -> str | None:
    tx = ser.find(f"{C}tx")
    if tx is None:
        return None
    literal = tx.findtext(f"{C}v")
    if literal:
        return literal
    points = _points(tx, cells)
    return as_text(points[0]) if points else None


def _cache(source: Any) -> Any:
    """The cached or literal values a data source carries, if any."""
    for tag in ("numCache", "strCache", "multiLvlStrCache"):
        found = source.find(f".//{C}{tag}")
        if found is not None:
            return found
    for tag in ("numLit", "strLit"):
        found = source.find(f"{C}{tag}")
        if found is not None:
            return found
    return None


def _points(source: Any, cells: Cells | None) -> list[Any]:
    """
    The points of a data source, one entry per point, ``None`` for a gap.

    Cached values first; the cells of the referenced range when there is no
    cache. A multi-level category reads each label with the levels above it,
    outermost first: ``"2024 / Q1"``.
    """
    if source is None:
        return []
    cache = _cache(source)
    if cache is None:
        area = parse_range(source.findtext(f".//{C}f"))
        if area is None or cells is None or area.size() > MAX_UNCACHED:
            return []
        return [
            cell.value if cell is not None else None
            for cell in (cells(area.sheet, r, c) for r, c in area.positions())
        ]
    # As many points as the highest index cached, not as many as `ptCount`
    # claims: a gap at the end is restored by the other dimension's length, and
    # a damaged count cannot make a series of a million blanks.
    indices = [
        int(pt.get("idx", "0"))
        for pt in cache.iter(f"{C}pt")
        if pt.get("idx", "0").isdigit()
    ]
    count = min(max(indices, default=-1) + 1, MAX_POINTS)
    if cache.tag == f"{C}multiLvlStrCache":
        levels = [_level(level, count) for level in cache.findall(f"{C}lvl")]
        labels = []
        for index in range(count):
            parts = [level[index] for level in reversed(levels) if level[index]]
            labels.append(" / ".join(parts) if parts else None)
        return labels
    numeric = cache.tag in (f"{C}numCache", f"{C}numLit")
    out: list[Any] = [None] * count
    for pt in cache.findall(f"{C}pt"):
        index = pt.get("idx", "0")
        if index.isdigit() and int(index) < count:
            text = pt.findtext(f"{C}v")
            out[int(index)] = as_number(text) if numeric else text
    return out


def _level(level: Any, count: int) -> list[str | None]:
    """One level of a multi-level category, each label carried forward."""
    out: list[str | None] = [None] * count
    for pt in level.findall(f"{C}pt"):
        index = pt.get("idx", "0")
        if index.isdigit() and int(index) < count:
            out[int(index)] = pt.findtext(f"{C}v")
    current = None
    for index, value in enumerate(out):
        if value:
            current = value
        out[index] = current
    return out


def _cached_format(source: Any) -> str | None:
    """The number format a cached copy records, unless it is ``General``."""
    code = source.findtext(f".//{C}formatCode") if source is not None else None
    if not code or code.lower() == "general":
        return None
    return code


def _format_code(source: Any, cells: Cells) -> str | None:
    """
    How a data source's numbers are formatted: as the cached copy records it,
    or, when the copy says only ``General``, as the first cell of the range is.
    """
    if source is None:
        return None
    code = _cached_format(source)
    if code is not None or source.find(f"{C}numRef") is None:
        return code
    area = parse_range(source.findtext(f".//{C}f"))
    if area is None:
        return None
    cell = cells(area.sheet, area.first_row, area.first_column)
    if cell is None or not cell.number_format:
        return None
    return None if cell.number_format.lower() == "general" else cell.number_format


def _explicit_format(axis: Any) -> str | None:
    """An axis' own number format, when it is not the one its data has."""
    fmt = axis.find(f"{C}numFmt") if axis is not None else None
    if fmt is None or fmt.get("sourceLinked") in ("1", "true"):
        return None
    code = fmt.get("formatCode")
    return None if not code or code.lower() == "general" else code


def _no_line(ser: Any) -> bool:
    line = ser.find(f"{C}spPr/{A}ln")
    return line is not None and line.find(f"{A}noFill") is not None


def _series_color(ser: Any, kind: str, theme: dict[str, str]) -> str | None:
    shape = ser.find(f"{C}spPr")
    if shape is None:
        return None
    if kind in ("line", "scatter", "radar"):
        fill = shape.find(f"{A}ln/{A}solidFill")
        if fill is None:
            fill = ser.find(f"{C}marker/{C}spPr/{A}solidFill")
        if fill is None and kind == "radar":
            # A filled radar's color is its area's.
            fill = shape.find(f"{A}solidFill")
    else:
        fill = shape.find(f"{A}solidFill")
    return fill_color(fill, theme)


def _point_colors(ser: Any, theme: dict[str, str]) -> Iterator[tuple[int, str]]:
    for point in ser.findall(f"{C}dPt"):
        color = fill_color(point.find(f"{C}spPr/{A}solidFill"), theme)
        if color is not None:
            yield int(_val(point, "idx", "0")), color


def _val(element: Any, tag: str, default: str | None = None) -> Any:
    if element is None:
        return default
    found = element.find(f"{C}{tag}")
    if found is None:
        return default
    return found.get("val", default)


def _vals(element: Any, tag: str) -> list[str]:
    return [e.get("val", "") for e in element.findall(f"{C}{tag}")]
