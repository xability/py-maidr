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

from maidr.excel import chartex
from maidr.excel.chartxml import wanted_cells
from maidr.excel.figure import chart_figure
from maidr.excel.package import Cell, DamagedPartError, NotAWorkbookError, Package
from maidr.util.caller_warning import warn_at_caller

__all__ = ["ExcelChart", "NotAWorkbookError", "read_excel_charts"]


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
    Every chart type Excel draws is read. Column and bar charts (clustered,
    stacked and 100% stacked), line charts (plain, stacked and 100% stacked),
    pie, doughnut, pie-of-pie and bar-of-pie charts, scatter and bubble
    charts, area charts, radar charts, stock charts, surface charts, and
    combinations of them, including a second value axis; and the chart types
    Excel 2016 added: histogram, Pareto, box and whisker, waterfall, funnel,
    treemap, sunburst and map. 3-D variants read as their flat counterparts.

    Where matplotlib has a call for a chart it is drawn with it, and read as
    that call is; where it has none -- a radar, a bubble chart's sizes, a
    stock chart's candles, a waterfall, a funnel, a treemap, a sunburst and a
    map -- maidr draws the marks itself and reads the chart's own values. A
    histogram's bins and a box's quartiles are worked out as Excel works them
    out, from the values the chart keeps. A map is read as the list of its
    regions and drawn as bars, since the shapes of its regions are not read.

    An axis with no title is named after the header cell above its category
    range, which the reader hears and the drawing leaves out, as Excel does.
    A category with no label reads ``(blank)``, and a blank value is a gap,
    never a zero. What a chart cannot show, such as the negative values of a
    pie, and any chart part maidr cannot read, is left out with a
    ``UserWarning`` naming the chart and its sheet.

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
        names = package.defined_names
        parts = {}
        damaged: dict[str, str] = {}
        wanted: dict[str, set[tuple[int, int]]] = {}
        for placement in placements:
            if not package.has(placement.part) or placement.part in parts:
                continue
            try:
                root = package.xml(placement.part)
            except DamagedPartError as reason:
                damaged[placement.part] = str(reason)
                continue
            parts[placement.part] = root
            found = (
                chartex.wanted_cells(root, names)
                if placement.is_chartex
                else wanted_cells(root)
            )
            for sheet, row, column in found:
                wanted.setdefault(sheet, set()).add((row, column))
        notes = list(package.problems)
        sheets = {sheet.name: sheet for sheet in package.sheets()}
        values = {}
        for name, positions in wanted.items():
            if name not in sheets:
                continue
            try:
                found_cells = package.read_cells(sheets[name], positions)
            except DamagedPartError as reason:
                # Each chart keeps its own copy of the values it drew, so a
                # damaged sheet costs only the header names and formats.
                notes.append(
                    f"maidr cannot read the cells of sheet '{name}' ({reason}); "
                    "the charts that refer to it are read without them."
                )
                continue
            for (row, column), cell in found_cells.items():
                values[(name, row, column)] = cell
        theme = package.theme_colors(package.workbook)
        date1904 = package.date1904

    def cells(sheet: str, row: int, column: int) -> Cell | None:
        return values.get((sheet, row, column))

    for note in notes:
        warn_at_caller(note)
    charts = []
    for placement in placements:
        where = f"'{placement.name}' on sheet '{placement.sheet.name}'"
        if placement.part in damaged:
            reason = damaged[placement.part]
            warn_at_caller(f"maidr cannot read {where} ({reason}); it is left out.")
            continue
        if placement.part not in parts:
            continue
        drawn = chart_figure(
            parts[placement.part],
            is_chartex=placement.is_chartex,
            cells=cells,
            theme=theme,
            date1904=date1904,
            names=names,
            aspect=placement.aspect,
            where=where,
        )
        if drawn is not None:
            title, figure = drawn
            charts.append(
                ExcelChart(placement.sheet.name, placement.name, title, figure)
            )
    return charts
