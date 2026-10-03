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

import colorsys
import math
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable, Iterator

from lxml import etree

from maidr.excel.package import NS_A, Cell, column_index

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
    "scatterChart": "scatter",
    "areaChart": "area",
    "area3DChart": "area",
}

#: What the reader is told a group it cannot read is called.
_UNREAD = {
    "ofPieChart": "pie-of-pie and bar-of-pie",
    "radarChart": "radar",
    "bubbleChart": "bubble",
    "stockChart": "stock",
    "surfaceChart": "surface",
    "surface3DChart": "surface",
}

_REFERENCE = re.compile(
    r"^(?:'(?P<quoted>(?:[^']|'')+)'|(?P<plain>[^'!\[\]]+))!"
    r"\$?(?P<c1>[A-Za-z]{1,3})\$?(?P<r1>\d+)"
    r"(?::\$?(?P<c2>[A-Za-z]{1,3})\$?(?P<r2>\d+))?$"
)

_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)  # fmt: skip
_DAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)  # fmt: skip
_DATE_TOKEN = re.compile(
    r'"[^"]*"|\\.|\[[^\]]*\]|yyyy|yy|e|mmmmm|mmmm|mmm|mm|m|dddd|ddd|dd|d'
    r"|hh|h|ss|s|am/pm|a/p|.",
    re.IGNORECASE,
)
_NOT_A_TOKEN = re.compile(r'"[^"]*"|\\.|\[[^\]]*\]')

#: The most points a series is read with: a sheet's row count. A part that
#: claims more is damaged, and is not allowed to ask for that much memory.
_MAX_POINTS = 1_048_576
#: The most cells read for a series range the part has no copy of. Excel always
#: writes the copy; a larger uncached range reads as empty rather than scanning
#: the sheet for it.
_MAX_UNCACHED = 100_000

#: ``(sheet, row, column)`` to the cell there, or ``None`` for an empty one.
Cells = Callable[[str, int, int], "Cell | None"]


@dataclass(frozen=True)
class Range:
    """A rectangular cell range on one sheet, zero-based and inclusive."""

    sheet: str
    first_row: int
    first_column: int
    last_row: int
    last_column: int

    def size(self) -> int:
        """How many cells the range holds."""
        rows = self.last_row - self.first_row + 1
        return rows * (self.last_column - self.first_column + 1)

    def positions(self) -> Iterator[tuple[int, int]]:
        """Each cell, row by row."""
        for row in range(self.first_row, self.last_row + 1):
            for column in range(self.first_column, self.last_column + 1):
                yield row, column

    def header(self) -> tuple[int, int] | None:
        """
        The cell that names this range: above a column of values, left of a
        row of them.
        """
        if self.first_row == self.last_row and self.last_column > self.first_column:
            if self.first_column == 0:
                return None
            return self.first_row, self.first_column - 1
        if self.first_row == 0:
            return None
        return self.first_row - 1, self.last_column


def parse_range(formula: str | None) -> Range | None:
    """
    The range a series formula names.

    Parameters
    ----------
    formula : str or None
        A formula such as ``Sales!$B$2:$B$5`` or ``'Q1 data'!$A$1``.

    Returns
    -------
    Range or None
        ``None`` for anything else: a defined name, a reference to another
        workbook, or several areas joined in parentheses.
    """
    if not formula:
        return None
    match = _REFERENCE.match(formula.strip())
    if match is None:
        return None
    sheet = match.group("plain") or match.group("quoted").replace("''", "'")
    r1, c1 = int(match.group("r1")) - 1, column_index(match.group("c1"))
    r2 = int(match.group("r2")) - 1 if match.group("r2") else r1
    c2 = column_index(match.group("c2")) if match.group("c2") else c1
    return Range(sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))


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
        for tag in ("tx", "cat", "val", "xVal", "yVal"):
            source = ser.find(f"{C}{tag}")
            if source is None:
                continue
            area = parse_range(source.findtext(f".//{C}f"))
            if area is None:
                continue
            if tag == "cat":
                header = area.header()
                if header is not None:
                    yield (area.sheet, *header)
            if _cache(source) is None:
                if area.size() <= _MAX_UNCACHED:
                    yield from ((area.sheet, r, c) for r, c in area.positions())
            elif (
                _cached_format(source) is None and source.find(f"{C}numRef") is not None
            ):
                yield area.sheet, area.first_row, area.first_column


@dataclass(frozen=True)
class Axis:
    """One axis of a chart group, as drawn and as announced."""

    #: The title Excel draws on the axis, or ``None`` when it draws none.
    title: str | None
    #: What the reader hears the axis called: the title, or a name found for
    #: an untitled axis.
    label: str | None
    hidden: bool
    position: str
    minimum: float | None
    maximum: float | None
    reversed: bool
    #: The number format of the axis labels, as an Excel format code.
    number_format: str | None


@dataclass(frozen=True)
class Series:
    """One series: its name, its points and how it is drawn."""

    name: str | None
    #: Category labels, or the x values of a scatter series.
    categories: tuple[Any, ...]
    values: tuple[float | None, ...]
    color: str | None
    #: Per-point colors -- a pie's slices -- as ``(index, "#RRGGBB")`` pairs.
    point_colors: tuple[tuple[int, str], ...]
    line: bool
    marker: bool


@dataclass(frozen=True)
class Group:
    """One chart group: series of one chart type that share axes."""

    #: ``"bar"``, ``"line"``, ``"pie"``, ``"doughnut"``, ``"scatter"`` or
    #: ``"area"``.
    kind: str
    horizontal: bool
    #: ``"standard"``, ``"clustered"``, ``"stacked"`` or ``"percentStacked"``.
    grouping: str
    series: tuple[Series, ...]
    #: The category axis, or the x axis of a scatter group.
    x_axis: Axis | None
    #: The value axis, or the y axis of a scatter group.
    y_axis: Axis | None
    #: What the categories are called: the category axis' title, or the
    #: header above their range, which also names a pie's slices.
    category_name: str | None
    secondary: bool
    first_slice_angle: float
    hole_size: float | None


@dataclass(frozen=True)
class ChartSpec:
    """Everything maidr needs from one chart part to draw it."""

    title: str | None
    groups: tuple[Group, ...]
    #: Where the legend sits (``"r"``, ``"b"``, ``"t"``, ``"l"``, ``"tr"``),
    #: or ``None`` when the chart has no legend.
    legend: str | None
    #: The chart types in the part that maidr does not read, by name.
    unread: tuple[str, ...]


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
        The workbook's theme colors, from :meth:`Package.theme_colors`.
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
        grouping = _val(element, "grouping", "standard")
        if kind == "line" and grouping != "standard":
            unread.append("stacked line")
            continue
        if kind is None:
            unread.append(_UNREAD.get(name, name))
            continue
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
    if kind == "scatter":
        x_element = next(
            (a for a in group_axes if _val(a, "axPos") in ("b", "t")), None
        )
        y_element = next((a for a in group_axes if a is not x_element), None)
    else:
        x_element = next((a for a in group_axes if a.tag != f"{C}valAx"), None)
        y_element = next((a for a in group_axes if a.tag == f"{C}valAx"), None)
    dates = x_element is not None and x_element.tag == f"{C}dateAx"

    raw = sorted(
        element.findall(f"{C}ser"),
        key=lambda ser: int(_val(ser, "order", _val(ser, "idx", "0"))),
    )
    scatter_style = _val(element, "scatterStyle", "lineMarker")
    group_markers = _val(element, "marker", "1") in ("1", "true")
    vary_colors = _val(element, "varyColors", "0") in ("1", "true")
    series = []
    for ser in raw:
        index = int(_val(ser, "idx", "0"))
        name = _series_name(ser, cells)
        if kind == "scatter":
            x_source, y_source = ser.find(f"{C}xVal"), ser.find(f"{C}yVal")
        else:
            x_source, y_source = ser.find(f"{C}cat"), ser.find(f"{C}val")
        values = [_number(v) for v in _points(y_source, cells)]
        if blanks == "zero" and kind in ("line", "scatter", "area"):
            values = [0.0 if v is None else v for v in values]
        x_points = _points(x_source, cells)
        x_format = _explicit_format(x_element) or _format_code(x_source, cells)
        if kind == "scatter":
            # Excel plots a scatter series against 1, 2, 3, ... when its x
            # values are missing or are text.
            numbers = [_number(v) for v in x_points]
            if not x_points or any(
                isinstance(v, str) and n is None for v, n in zip(x_points, numbers)
            ):
                numbers = [float(i + 1) for i in range(len(values))]
            categories = numbers
        else:
            categories = [
                _category_label(v, x_format, dates, date1904) for v in x_points
            ] or [str(i + 1) for i in range(len(values))]
        count = max(len(categories), len(values))
        categories += [None] * (count - len(categories))
        values += [None] * (count - len(values))
        line = kind in ("line", "scatter") and not _no_line(ser)
        if kind == "scatter" and scatter_style in ("marker", "none"):
            line = False
        symbol = ser.find(f"{C}marker/{C}symbol")
        marker = (symbol is None or symbol.get("val") != "none") and (
            kind == "scatter" or group_markers
        )
        point_colors = dict(_point_colors(ser, theme))
        if kind in ("pie", "doughnut") and vary_colors:
            # A pie's slices take the theme accents in turn, as series do.
            for point in range(count):
                color = _default_color(point, theme)
                if color is not None:
                    point_colors.setdefault(point, color)
        series.append(
            Series(
                name=name,
                categories=tuple(categories),
                values=tuple(values),
                color=_series_color(ser, kind, theme) or _default_color(index, theme),
                point_colors=tuple(sorted(point_colors.items())),
                line=line,
                marker=marker,
            )
        )

    header = _category_header(raw, cells) if kind != "scatter" else None
    x_axis = (
        _axis(x_element, raw, "x", header, cells) if x_element is not None else None
    )
    y_axis = _axis(y_element, raw, "y", None, cells) if y_element is not None else None
    position = y_axis.position if y_axis is not None else ""
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
    )


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
        minimum=_float(_val(scaling, "min")) if scaling is not None else None,
        maximum=_float(_val(scaling, "max")) if scaling is not None else None,
        reversed=scaling is not None and _val(scaling, "orientation") == "maxMin",
        number_format=number_format,
    )


def _category_header(series: list[Any], cells: Cells) -> str | None:
    """The header cell above (or left of) the first series' category range."""
    if not series:
        return None
    area = parse_range(series[0].findtext(f"{C}cat//{C}f"))
    header = area.header() if area is not None else None
    if header is None:
        return None
    cell = cells(area.sheet, *header)
    return _text_value(cell.value) if cell is not None else None


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
    return _text_value(cached[0]) if cached else None


def _series_name(ser: Any, cells: Cells) -> str | None:
    tx = ser.find(f"{C}tx")
    if tx is None:
        return None
    literal = tx.findtext(f"{C}v")
    if literal:
        return literal
    points = _points(tx, cells)
    return _text_value(points[0]) if points else None


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
        if area is None or cells is None or area.size() > _MAX_UNCACHED:
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
    count = min(max(indices, default=-1) + 1, _MAX_POINTS)
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
            out[int(index)] = _number(text) if numeric else text
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


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _float(value: str | None) -> float | None:
    return _number(value)


def _text_value(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, float):
        return _number_label(value)
    return str(value)


def _number_label(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.10g}"


def _category_label(
    value: Any, code: str | None, dates: bool, date1904: bool
) -> str | None:
    """A category as Excel labels it: text as it is, a date as the axis shows it."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    number = _number(value)
    if number is None:
        return None
    if is_date_format(code):
        return format_date(serial_to_datetime(number, date1904), code)
    if dates:
        return format_date(serial_to_datetime(number, date1904), None)
    return _number_label(number)


def is_date_format(code: str | None) -> bool:
    """
    Whether an Excel number format shows a date or a time.

    Parameters
    ----------
    code : str or None
        The format code, such as ``"mmm-yy"`` or ``"0.0%"``.

    Returns
    -------
    bool
        ``True`` for a code with date or time parts and no digit placeholders.
    """
    if not code or code.lower() == "general":
        return False
    bare = _NOT_A_TOKEN.sub("", code.split(";")[0]).lower()
    return any(c in bare for c in "ymdhs") and not re.search(r"[0#?]", bare)


def serial_to_datetime(serial: float, date1904: bool = False) -> datetime:
    """
    The date an Excel serial number stands for.

    Parameters
    ----------
    serial : float
        Days since the workbook's epoch, with the time of day as a fraction.
    date1904 : bool, default False
        Whether the workbook counts from 1904-01-01 rather than 1900.

    Returns
    -------
    datetime
        The date and time, to the nearest second. In the 1900 system serial
        60 is Excel's 1900-02-29, which never was; it reads as 1900-02-28.
    """
    if date1904:
        base = datetime(1904, 1, 1)
    elif serial >= 61:
        base = datetime(1899, 12, 30)
    else:
        base = datetime(1899, 12, 31)
        if serial >= 60:
            serial -= 1
    return base + timedelta(seconds=round(serial * 86400))


def format_date(moment: datetime, code: str | None) -> str:
    """
    A date written the way an Excel format code writes it.

    Parameters
    ----------
    moment : datetime
        The date.
    code : str or None
        An Excel date format code such as ``"mmm-yy"``. Without one, the date
        is written ISO 8601 style, with the time only when there is one.

    Returns
    -------
    str
        ``"Jan-24"`` for ``mmm-yy``. Names are in English.
    """
    if not code or not is_date_format(code):
        if moment.hour or moment.minute or moment.second:
            return moment.strftime("%Y-%m-%d %H:%M:%S").removesuffix(":00")
        return moment.strftime("%Y-%m-%d")
    tokens = _DATE_TOKEN.findall(code.split(";")[0])
    twelve_hour = any(t.lower() in ("am/pm", "a/p") for t in tokens)
    out = []
    for i, token in enumerate(tokens):
        lower = token.lower()
        if lower in ("m", "mm") and _is_minute(tokens, i):
            out.append(f"{moment.minute:02d}" if lower == "mm" else str(moment.minute))
        else:
            out.append(_date_part(token, lower, moment, twelve_hour))
    return "".join(out).strip()


def _is_minute(tokens: list[str], index: int) -> bool:
    """Whether an ``m`` token means minutes: after hours, or before seconds."""

    def letters(seq: Iterator[str]) -> str | None:
        for token in seq:
            lower = token.lower()
            if lower[:1] in "ymdhs" and not lower.startswith(("[", '"', "\\")):
                return lower
        return None

    before = letters(reversed(tokens[:index]))
    after = letters(iter(tokens[index + 1 :]))
    return (before or "").startswith("h") or (after or "").startswith("s")


def _date_part(token: str, lower: str, moment: datetime, twelve_hour: bool) -> str:
    hour = moment.hour % 12 or 12 if twelve_hour else moment.hour
    parts = {
        "yyyy": f"{moment.year:04d}",
        "e": f"{moment.year:04d}",
        "yy": f"{moment.year % 100:02d}",
        "mmmmm": _MONTHS[moment.month - 1][0],
        "mmmm": _MONTHS[moment.month - 1],
        "mmm": _MONTHS[moment.month - 1][:3],
        "mm": f"{moment.month:02d}",
        "m": str(moment.month),
        "dddd": _DAYS[moment.weekday()],
        "ddd": _DAYS[moment.weekday()][:3],
        "dd": f"{moment.day:02d}",
        "d": str(moment.day),
        "hh": f"{hour:02d}",
        "h": str(hour),
        "ss": f"{moment.second:02d}",
        "s": str(moment.second),
        "am/pm": "AM" if moment.hour < 12 else "PM",
        "a/p": "A" if moment.hour < 12 else "P",
    }
    if lower in parts:
        return parts[lower]
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    if token.startswith("\\"):
        return token[1:]
    if token.startswith("["):
        return ""
    return token


def _no_line(ser: Any) -> bool:
    line = ser.find(f"{C}spPr/{A}ln")
    return line is not None and line.find(f"{A}noFill") is not None


def _series_color(ser: Any, kind: str, theme: dict[str, str]) -> str | None:
    shape = ser.find(f"{C}spPr")
    if shape is None:
        return None
    if kind in ("line", "scatter"):
        fill = shape.find(f"{A}ln/{A}solidFill")
        if fill is None:
            fill = ser.find(f"{C}marker/{C}spPr/{A}solidFill")
    else:
        fill = shape.find(f"{A}solidFill")
    return _color(fill, theme)


def _point_colors(ser: Any, theme: dict[str, str]) -> Iterator[tuple[int, str]]:
    for point in ser.findall(f"{C}dPt"):
        color = _color(point.find(f"{C}spPr/{A}solidFill"), theme)
        if color is not None:
            yield int(_val(point, "idx", "0")), color


def _color(fill: Any, theme: dict[str, str]) -> str | None:
    """A solid fill's color, with its luminance modifiers applied."""
    if fill is None:
        return None
    for color in fill:
        if not isinstance(color.tag, str):
            continue
        name = etree.QName(color).localname
        if name == "srgbClr":
            base = "#" + (color.get("val") or "").upper()
        elif name == "schemeClr":
            base = theme.get(color.get("val", ""))
        elif name == "sysClr":
            base = "#" + (color.get("lastClr") or "").upper()
        else:
            base = None
        if base is None or len(base) != 7:
            return None
        mod = _float(_child_val(color, "lumMod"))
        off = _float(_child_val(color, "lumOff"))
        return _luminance(base, (mod or 100000) / 100000, (off or 0) / 100000)
    return None


def _child_val(element: Any, name: str) -> str | None:
    child = element.find(f"{A}{name}")
    return child.get("val") if child is not None else None


def _luminance(color: str, mod: float, off: float) -> str:
    if mod == 1 and off == 0:
        return color
    r, g, b = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, lum, s = colorsys.rgb_to_hls(r, g, b)
    lum = min(1.0, max(0.0, lum * mod + off))
    r, g, b = colorsys.hls_to_rgb(h, lum, s)
    return "#{:02X}{:02X}{:02X}".format(*(round(v * 255) for v in (r, g, b)))


def _default_color(index: int, theme: dict[str, str]) -> str | None:
    """
    The color Excel's default style gives series ``index``: the six theme
    accents in turn, then the six again darker, then lighter.
    """
    base = theme.get(f"accent{index % 6 + 1}")
    if base is None:
        return None
    cycle = (index // 6) % 3
    if cycle == 1:
        return _luminance(base, 0.6, 0)
    if cycle == 2:
        return _luminance(base, 0.6, 0.4)
    return base


def _val(element: Any, tag: str, default: str | None = None) -> Any:
    if element is None:
        return default
    found = element.find(f"{C}{tag}")
    if found is None:
        return default
    return found.get("val", default)


def _vals(element: Any, tag: str) -> list[str]:
    return [e.get("val", "") for e in element.findall(f"{C}{tag}")]
