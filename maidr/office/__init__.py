"""Read the charts of a PowerPoint presentation or a Word document into maidr.

>>> import maidr
>>> charts = maidr.read_powerpoint_charts("deck.pptx")
>>> maidr.show(charts[0])

A chart on a slide or in a document is the same chart part an Excel workbook
keeps, with the same copy of the values it shows, and with its data in a
workbook embedded beside it. Each is read as :func:`maidr.read_excel_charts`
reads a workbook's charts, so none of PowerPoint, Word or Excel needs to be
installed.
"""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass, field
from typing import IO, Callable, TypeVar

from matplotlib.figure import Figure

from maidr.excel import chartex
from maidr.excel.cells import Cells
from maidr.excel.chartxml import wanted_cells
from maidr.excel.figure import chart_figure
from maidr.excel.package import Cell, DamagedPartError, Package
from maidr.office.package import (
    Document,
    NotADocumentError,
    NotAPresentationError,
    OfficePlacement,
    Presentation,
)
from maidr.util.caller_warning import warn_at_caller

__all__ = [
    "NotADocumentError",
    "NotAPresentationError",
    "PowerPointChart",
    "WordChart",
    "read_powerpoint_charts",
    "read_word_charts",
]


@dataclass(frozen=True, eq=False)
class PowerPointChart:
    """
    One chart of a PowerPoint presentation, drawn and ready for maidr.

    Pass it to :func:`maidr.show`, :func:`maidr.render`,
    :func:`maidr.save_html` or :func:`maidr.close` as you would a matplotlib
    figure.

    Attributes
    ----------
    slide : int
        The number of the slide the chart is on, counting from 1 in slide
        show order.
    hidden : bool
        Whether that slide is hidden in the slide show.
    name : str
        The chart's name in PowerPoint, such as ``"Chart 3"``.
    title : str or None
        The title PowerPoint shows on the chart, or ``None`` when it shows
        none.
    figure : matplotlib.figure.Figure
        The chart drawn with matplotlib. It is not managed by pyplot, so
        ``plt.show()`` does not show it.
    """

    slide: int
    hidden: bool
    name: str
    title: str | None
    figure: Figure = field(repr=False)


@dataclass(frozen=True, eq=False)
class WordChart:
    """
    One chart of a Word document, drawn and ready for maidr.

    Pass it to :func:`maidr.show`, :func:`maidr.render`,
    :func:`maidr.save_html` or :func:`maidr.close` as you would a matplotlib
    figure.

    Attributes
    ----------
    number : int
        The chart's place among the document's charts, counting from 1 in
        reading order.
    name : str
        The chart's name in Word, such as ``"Chart 1"``.
    title : str or None
        The title Word shows on the chart, or ``None`` when it shows none.
    figure : matplotlib.figure.Figure
        The chart drawn with matplotlib. It is not managed by pyplot, so
        ``plt.show()`` does not show it.
    """

    number: int
    name: str
    title: str | None
    figure: Figure = field(repr=False)


def read_powerpoint_charts(
    path: str | os.PathLike | IO[bytes],
) -> list[PowerPointChart]:
    """
    Read every chart in a PowerPoint presentation.

    Parameters
    ----------
    path : str, os.PathLike or binary file object
        A ``.pptx`` or ``.pptm`` presentation, or a ``.ppsx`` or ``.potx``
        one, or an open binary stream of one, such as an uploaded file.

    Returns
    -------
    list of PowerPointChart
        One per chart maidr can read, slide by slide in slide show order and,
        on a slide, in the order of its shapes. Charts on hidden slides are
        included and say so. Pass one to :func:`maidr.show`,
        :func:`maidr.render` or :func:`maidr.save_html`.

    Raises
    ------
    NotAPresentationError
        If the file is not a ``.pptx`` presentation: an older ``.ppt`` file,
        an Excel workbook or a Word document, or a Strict Open XML
        presentation. A ``ValueError``.

    Notes
    -----
    Every chart type :func:`maidr.read_excel_charts` reads is read, and read
    the same way: a chart on a slide is the same chart part, with the copy of
    its values PowerPoint drew and its data in a workbook embedded in the
    presentation. That workbook is read only for what the copy leaves out,
    such as the header cell that names a category axis with no title. Each
    chart is drawn in the colors of its slide's theme.

    Examples
    --------
    >>> import maidr
    >>> for chart in maidr.read_powerpoint_charts("deck.pptx"):
    ...     maidr.save_html(chart, f"slide-{chart.slide}-{chart.name}.html")
    """
    archive = _open(
        path,
        NotAPresentationError,
        "maidr reads PowerPoint presentations saved as .pptx or .pptm, and this "
        "file is not one. An older .ppt presentation can be saved as .pptx first.",
    )
    with archive:
        package = Presentation(archive)
        read = _read(package, lambda p: f"'{p.name}' on slide {p.number}")
    return [
        PowerPointChart(p.number, p.hidden, p.name, title, figure)
        for p, title, figure in read
    ]


def read_word_charts(
    path: str | os.PathLike | IO[bytes],
) -> list[WordChart]:
    """
    Read every chart in a Word document.

    Parameters
    ----------
    path : str, os.PathLike or binary file object
        A ``.docx`` or ``.docm`` document, or a ``.dotx`` template, or an
        open binary stream of one, such as an uploaded file.

    Returns
    -------
    list of WordChart
        One per chart maidr can read in the document's body, in reading
        order: inline and floating charts, and charts in tables and text
        boxes. Pass one to :func:`maidr.show`, :func:`maidr.render` or
        :func:`maidr.save_html`.

    Raises
    ------
    NotADocumentError
        If the file is not a ``.docx`` document: an older ``.doc`` file, an
        Excel workbook or a PowerPoint presentation, or a Strict Open XML
        document. A ``ValueError``.

    Notes
    -----
    Every chart type :func:`maidr.read_excel_charts` reads is read, and read
    the same way: a chart in a document is the same chart part, with the
    copy of its values Word drew and its data in a workbook embedded in the
    document. That workbook is read only for what the copy leaves out, such
    as the header cell that names a category axis with no title. Each chart
    is drawn in the colors of the document's theme. Charts in headers,
    footers, footnotes and comments are not read.

    Examples
    --------
    >>> import maidr
    >>> for chart in maidr.read_word_charts("report.docx"):
    ...     maidr.save_html(chart, f"chart-{chart.number}.html")
    """
    archive = _open(
        path,
        NotADocumentError,
        "maidr reads Word documents saved as .docx or .docm, and this file is "
        "not one. An older .doc document can be saved as .docx first.",
    )
    with archive:
        package = Document(archive)
        read = _read(
            package, lambda p: f"'{p.name}' (chart {p.number} of the document)"
        )
    return [WordChart(p.number, p.name, title, figure) for p, title, figure in read]


_Error = TypeVar("_Error", bound=ValueError)


def _open(
    path: str | os.PathLike | IO[bytes], error: type[_Error], message: str
) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path)
    except zipfile.BadZipFile as reason:
        raise error(message) from reason


def _read(
    package: Presentation | Document, where: Callable[[OfficePlacement], str]
) -> list[tuple[OfficePlacement, str | None, Figure]]:
    """
    Read and draw every chart a presentation or a document holds.

    Everything a chart needs from the file -- its part, its embedded
    workbook's cells, its theme -- is read first, while the file is open;
    the charts are then drawn from those alone.
    """
    placements = package.charts()
    notes = list(package.problems)
    parts = {}
    damaged: dict[str, str] = {}
    data: dict[str, tuple[Cells, dict[str, str], bool]] = {}
    for placement in placements:
        if not package.has(placement.part) or placement.part in parts:
            continue
        try:
            parts[placement.part] = package.xml(placement.part)
        except DamagedPartError as reason:
            damaged[placement.part] = str(reason)
            continue
        data[placement.part], problem = _workbook_data(
            package, placement, parts[placement.part]
        )
        if problem is not None:
            notes.append(
                f"maidr cannot read the workbook {where(placement)} keeps its data "
                f"in ({problem}); it is read from the copy of its values the "
                "chart keeps."
            )
    themes = {
        owner: package.theme_colors(owner)
        for owner in {p.theme_owner for p in placements}
    }

    for note in notes:
        warn_at_caller(note)
    out = []
    for placement in placements:
        if placement.part in damaged:
            reason = damaged[placement.part]
            warn_at_caller(
                f"maidr cannot read {where(placement)} ({reason}); it is left out."
            )
            continue
        if placement.part not in parts:
            continue
        cells, names, date1904 = data[placement.part]
        drawn = chart_figure(
            parts[placement.part],
            is_chartex=placement.is_chartex,
            cells=cells,
            theme=themes[placement.theme_owner],
            date1904=date1904,
            names=names,
            aspect=placement.aspect,
            where=where(placement),
        )
        if drawn is not None:
            out.append((placement, *drawn))
    return out


def _no_cells(sheet: str, row: int, column: int) -> Cell | None:
    return None


def _workbook_data(
    package: Presentation | Document, placement: OfficePlacement, root: object
) -> tuple[tuple[Cells, dict[str, str], bool], str | None]:
    """
    What a chart reads from the workbook embedded with it.

    Returns
    -------
    tuple
        ``(cells, names, date1904)``: the cells the chart part names that it
        keeps no copy of, the workbook's defined names, and whether the
        workbook counts dates from 1904; with why the workbook could not be
        read, or ``None``. A chart with no embedded workbook reads nothing
        from one, and that is not a problem: its copy of its values is what
        it drew.
    """
    target = package.embedded_workbook(placement.part)
    if target is None:
        return (_no_cells, {}, False), None
    try:
        with zipfile.ZipFile(io.BytesIO(package.read(target))) as archive:
            book = Package(archive)
            names = book.defined_names
            found = (
                chartex.wanted_cells(root, names)
                if placement.is_chartex
                else wanted_cells(root)
            )
            wanted: dict[str, set[tuple[int, int]]] = {}
            for sheet, row, column in found:
                wanted.setdefault(sheet, set()).add((row, column))
            sheets = {sheet.name: sheet for sheet in book.sheets()}
            values: dict[tuple[str, int, int], Cell] = {}
            for name, positions in wanted.items():
                if name in sheets:
                    for (row, column), cell in book.read_cells(
                        sheets[name], positions
                    ).items():
                        values[(name, row, column)] = cell
            date1904 = book.date1904
    except (zipfile.BadZipFile, ValueError) as reason:
        # A damaged or unreadable embedded workbook, or an older .xls one:
        # the chart still has the copy of its values it drew.
        return (_no_cells, {}, False), str(reason)

    def cells(sheet: str, row: int, column: int) -> Cell | None:
        return values.get((sheet, row, column))

    return (cells, names, date1904), None
