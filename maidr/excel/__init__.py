"""Read the charts of an Excel workbook into maidr.

>>> import maidr
>>> charts = maidr.read_excel_charts("sales.xlsx")
>>> maidr.show(charts[0])

Each chart is read from the workbook file itself, so Excel does not need to be
installed: from its chart part, which keeps a copy of the values Excel drew,
and from the sheet cells only for what that part leaves out. It is then drawn
with matplotlib in the workbook's theme colors, and py-maidr reads the drawing
like any other matplotlib figure.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass, field
from typing import IO

from matplotlib.figure import Figure

from maidr.core.figure_manager import FigureManager
from maidr.excel.chartxml import read_chart, wanted_cells
from maidr.excel.draw import draw
from maidr.excel.package import Cell, DamagedPartError, NotAWorkbookError, Package
from maidr.util.caller_warning import warn_at_caller

__all__ = ["ExcelChart", "NotAWorkbookError", "read_excel_charts"]

NS_CX = "http://schemas.microsoft.com/office/drawing/2014/chartex"

#: The Excel 2016 chart types, by the layout their series name.
_CHARTEX_KINDS = {
    "clusteredColumn": "histogram",
    "paretoLine": "Pareto",
    "boxWhisker": "box and whisker",
    "waterfall": "waterfall",
    "funnel": "funnel",
    "treemap": "treemap",
    "sunburst": "sunburst",
    "regionMap": "map",
}


@dataclass(frozen=True, eq=False)
class ExcelChart:
    """
    One chart of an Excel workbook, drawn and ready for maidr.

    Pass it to :func:`maidr.show`, :func:`maidr.render`,
    :func:`maidr.save_html` or :func:`maidr.close` as you would a matplotlib
    figure.

    Attributes
    ----------
    sheet : str
        The name of the sheet the chart is on.
    name : str
        The chart's name in Excel, such as ``"Chart 1"``.
    title : str or None
        The title Excel shows on the chart, or ``None`` when it shows none.
    figure : matplotlib.figure.Figure
        The chart drawn with matplotlib. It is not managed by pyplot, so
        ``plt.show()`` does not show it.
    """

    sheet: str
    name: str
    title: str | None
    figure: Figure = field(repr=False)


def read_excel_charts(
    path: str | os.PathLike | IO[bytes],
) -> list[ExcelChart]:
    """
    Read every chart in an Excel workbook.

    Parameters
    ----------
    path : str, os.PathLike or binary file object
        An ``.xlsx`` or ``.xlsm`` workbook, or an open binary stream of one,
        such as an uploaded file.

    Returns
    -------
    list of ExcelChart
        One per chart maidr can read, sheet by sheet in tab order and, within
        a sheet, top to bottom and left to right. Pass one to
        :func:`maidr.show`, :func:`maidr.render` or :func:`maidr.save_html`.

    Raises
    ------
    NotAWorkbookError
        If the file is not an ``.xlsx`` workbook: an older ``.xls`` file, a
        CSV file, or a Strict Open XML workbook. A ``ValueError``.

    Notes
    -----
    Read: column and bar charts (clustered, stacked and 100% stacked),
    line charts, pie and doughnut charts, scatter charts with or without
    lines, area charts (plain, stacked and 100% stacked), and combinations of
    them, including a second value axis. 3-D variants read as their flat
    counterparts.

    Not read yet: stacked line, radar, bubble, stock, surface, pie-of-pie,
    and the chart types Excel 2016 added -- histogram, Pareto, box and
    whisker, waterfall, funnel, treemap, sunburst and map. Each such chart,
    or part of a combo chart, is left out with a ``UserWarning`` naming the
    chart, its sheet and its type, as are values a chart cannot show, such
    as the negative values of a pie.

    An axis with no title is named after the header cell above its category
    range, which the reader hears and the drawing leaves out, as Excel does.
    A category with no label reads ``(blank)``, and a blank value is a gap,
    never a zero.

    Examples
    --------
    >>> import maidr
    >>> for chart in maidr.read_excel_charts("sales.xlsx"):
    ...     maidr.save_html(chart, f"{chart.name}.html")
    """
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise NotAWorkbookError(
            "maidr reads Excel workbooks saved as .xlsx or .xlsm, and this file "
            "is not one. An older .xls workbook can be saved as .xlsx first."
        ) from error

    with archive:
        package = Package(archive)
        placements = package.charts()
        parts = {}
        damaged: dict[str, str] = {}
        wanted: dict[str, set[tuple[int, int]]] = {}
        for placement in placements:
            if placement.is_chartex or not package.has(placement.part):
                continue
            try:
                root = package.xml(placement.part)
            except DamagedPartError as reason:
                damaged[placement.part] = str(reason)
                continue
            parts[placement.part] = root
            for sheet, row, column in wanted_cells(root):
                wanted.setdefault(sheet, set()).add((row, column))
        notes = list(package.problems)
        sheets = {sheet.name: sheet for sheet in package.sheets()}
        values = {}
        for name, positions in wanted.items():
            if name not in sheets:
                continue
            try:
                found = package.read_cells(sheets[name], positions)
            except DamagedPartError as reason:
                # Each chart keeps its own copy of the values it drew, so a
                # damaged sheet costs only the header names and formats.
                notes.append(
                    f"maidr cannot read the cells of sheet '{name}' ({reason}); "
                    "the charts that refer to it are read without them."
                )
                continue
            for (row, column), cell in found.items():
                values[(name, row, column)] = cell
        kinds = {
            placement.part: _chartex_kind(package, placement.part)
            for placement in placements
            if placement.is_chartex and package.has(placement.part)
        }
        theme = package.theme_colors()
        date1904 = package.date1904

    def cells(sheet: str, row: int, column: int) -> Cell | None:
        return values.get((sheet, row, column))

    for note in notes:
        warn_at_caller(note)
    charts = []
    for placement in placements:
        where = f"'{placement.name}' on sheet '{placement.sheet.name}'"
        if placement.is_chartex:
            kind = kinds.get(placement.part) or "Excel 2016"
            warn_at_caller(
                f"maidr does not read {kind} charts yet; {where} is left out."
            )
            continue
        if placement.part in damaged:
            reason = damaged[placement.part]
            warn_at_caller(f"maidr cannot read {where} ({reason}); it is left out.")
            continue
        if placement.part not in parts:
            continue
        try:
            spec = read_chart(
                parts[placement.part], cells=cells, theme=theme, date1904=date1904
            )
        except (ValueError, TypeError, IndexError) as reason:
            # A damaged chart part costs that chart, never the whole workbook.
            warn_at_caller(f"maidr cannot read {where} ({reason}); it is left out.")
            continue
        for kind in spec.unread:
            what = "is left out" if not spec.groups else "is read without them"
            warn_at_caller(f"maidr does not read {kind} charts yet; {where} {what}.")
        if not spec.groups:
            if not spec.unread:
                warn_at_caller(f"{where} has no data maidr can read; it is left out.")
            continue
        figure = draw(spec, aspect=placement.aspect, where=where)
        try:
            FigureManager.get_maidr(figure)
        except KeyError:
            # Every point was blank, or a pie had no slice with a size.
            warn_at_caller(f"{where} has no data maidr can read; it is left out.")
            continue
        charts.append(
            ExcelChart(placement.sheet.name, placement.name, spec.title, figure)
        )
    return charts


def _chartex_kind(package: Package, part: str) -> str | None:
    """The type of an Excel 2016 chart, named the way Excel's menu names it."""
    try:
        root = package.xml(part)
    except DamagedPartError:
        return None
    series = root.find(f".//{{{NS_CX}}}series")
    if series is None:
        return None
    return _CHARTEX_KINDS.get(series.get("layoutId", ""))
