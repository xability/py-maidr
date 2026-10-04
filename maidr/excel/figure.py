"""Read one chart part and draw it, or say why it cannot be.

A chart part is the same DrawingML (or, for the chart types Excel 2016 added,
``chartEx``) whether it sits in a workbook, a presentation or a document, so
:func:`maidr.read_excel_charts`, :func:`maidr.read_powerpoint_charts` and
:func:`maidr.read_word_charts` each find their charts and hand every part
here.
"""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure

from maidr.core.figure_manager import FigureManager
from maidr.excel import chartex
from maidr.excel.cells import Cells
from maidr.excel.chartxml import read_chart
from maidr.excel.draw import draw_chart
from maidr.util.caller_warning import warn_at_caller

#: What a chart part holding values it never should raises while it is read
#: or drawn. Each costs that chart alone, never the file.
_DAMAGED_CHART = (
    ValueError,
    TypeError,
    IndexError,
    KeyError,
    ArithmeticError,
    RecursionError,
)


def chart_figure(
    root: Any,
    *,
    is_chartex: bool,
    cells: Cells,
    theme: dict[str, str],
    date1904: bool,
    names: dict[str, str],
    aspect: float | None,
    where: str,
) -> tuple[str | None, Figure] | None:
    """
    Read a chart part and draw it.

    Parameters
    ----------
    root : lxml.etree._Element
        The part's root element: ``c:chartSpace``, or ``cx:chartSpace`` for
        an Excel 2016 chart.
    is_chartex : bool
        Whether the part is an Excel 2016 chart.
    cells : callable
        ``cells(sheet, row, column)`` returns the cell there, for the cells
        the part's ``wanted_cells`` named, or ``None``.
    theme : dict
        The theme colors the chart is drawn in.
    date1904 : bool
        Whether the chart's workbook counts dates from 1904 rather than 1900.
    names : dict
        The workbook's defined names, which an Excel 2016 chart's formulas go
        through.
    aspect : float or None
        The chart's height over its width where it is placed.
    where : str
        Where the chart is, for the warnings: ``"'Chart 1' on sheet
        'Sales'"``.

    Returns
    -------
    tuple or None
        The chart's title and its drawing, or ``None`` when it has nothing
        maidr can read, after a ``UserWarning`` saying why.
    """
    try:
        if is_chartex:
            spec = chartex.read_chartex(
                root, cells=cells, theme=theme, date1904=date1904, names=names
            )
        else:
            spec = read_chart(root, cells=cells, theme=theme, date1904=date1904)
    except _DAMAGED_CHART as reason:
        # A damaged chart part costs that chart, never the whole file.
        warn_at_caller(f"maidr cannot read {where} ({reason}); it is left out.")
        return None
    for kind in spec.unread:
        what = "is left out" if not spec.groups else "is read without them"
        warn_at_caller(f"maidr does not read {kind} charts; {where} {what}.")
    if not spec.groups:
        if not spec.unread:
            warn_at_caller(f"{where} has no data maidr can read; it is left out.")
        return None
    try:
        figure = draw_chart(spec, aspect=aspect, where=where)
    except _DAMAGED_CHART as reason:
        # Values a chart part should never hold cost that chart alone.
        warn_at_caller(f"maidr cannot draw {where} ({reason}); it is left out.")
        return None
    try:
        FigureManager.get_maidr(figure)
    except KeyError:
        # Every point was blank, or a pie had no slice with a size.
        warn_at_caller(f"{where} has no data maidr can read; it is left out.")
        return None
    return spec.title, figure
