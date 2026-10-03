"""Where a workbook keeps its charts: the parts of an Office Open XML package.

An ``.xlsx`` file is a zip of XML parts tied together by relationship files.
A chart is reached in three steps: a sheet's relationships name its drawing,
the drawing anchors each chart on the sheet, and the drawing's relationships
name the chart part. This module walks that path, and reads the two other
things a chart needs from the workbook: the theme, which holds the colors
Excel draws series in, and sheet cells, for the header that names a range and
for a chart part that carries no copy of its values.

Everything is read with lxml, which ``maidr`` already depends on. openpyxl
would read the same parts, but it loads charts only when it loads every cell
of every sheet, which took over nine seconds on a 200,000-row sheet that this
module reads the charts of in a few milliseconds.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from lxml import etree

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"

#: The namespaces of the "Strict" flavour of the format, which Excel writes
#: only when asked to save as Strict Open XML.
_STRICT_PREFIX = "http://purl.oclc.org/ooxml/"

#: Pixels per inch and EMUs (the format's length unit) per pixel.
_EMU_PER_PIXEL = 9525
#: Excel's default column width and row height, in pixels, for sizing a chart
#: anchored between two cells. Sheets that set their own widths draw the chart
#: a little differently; only the chart's proportions are taken from this.
_DEFAULT_COLUMN_PX = 64
_DEFAULT_ROW_PX = 20

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, remove_comments=True)

_CELL_REF = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d+)$")


class NotAWorkbookError(ValueError):
    """The file is not an Office Open XML workbook maidr can read."""


def column_index(letters: str) -> int:
    """
    Zero-based index of a column named by letters.

    Parameters
    ----------
    letters : str
        The column's letters, such as ``"A"`` or ``"AB"``.

    Returns
    -------
    int
        ``0`` for ``A``, ``27`` for ``AB``.
    """
    index = 0
    for letter in letters.upper():
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return index - 1


def parse_cell(ref: str) -> tuple[int, int] | None:
    """
    The zero-based ``(row, column)`` of an ``A1``-style cell reference.

    Parameters
    ----------
    ref : str
        A reference such as ``"B3"`` or ``"$B$3"``.

    Returns
    -------
    tuple of int or None
        ``(2, 1)`` for ``B3``; ``None`` when ``ref`` is not a single cell.
    """
    match = _CELL_REF.match(ref.strip())
    if match is None:
        return None
    return int(match.group(2)) - 1, column_index(match.group(1))


#: Excel's built-in number formats, by id, as an English-language Excel writes
#: them. A style names one of these by id instead of spelling it out.
_BUILTIN_FORMATS = {
    0: "General",
    1: "0",
    2: "0.00",
    3: "#,##0",
    4: "#,##0.00",
    9: "0%",
    10: "0.00%",
    11: "0.00E+00",
    12: "# ?/?",
    13: "# ??/??",
    14: "m/d/yyyy",
    15: "d-mmm-yy",
    16: "d-mmm",
    17: "mmm-yy",
    18: "h:mm AM/PM",
    19: "h:mm:ss AM/PM",
    20: "h:mm",
    21: "h:mm:ss",
    22: "m/d/yyyy h:mm",
    37: "#,##0 ;(#,##0)",
    38: "#,##0 ;[Red](#,##0)",
    39: "#,##0.00;(#,##0.00)",
    40: "#,##0.00;[Red](#,##0.00)",
    45: "mm:ss",
    46: "[h]:mm:ss",
    47: "mmss.0",
    48: "##0.0E+0",
    49: "@",
}


@dataclass(frozen=True)
class Cell:
    """A cell's value, and the number format the sheet shows it in."""

    #: A ``float`` for a number, a ``str`` for text, ``"TRUE"`` or ``"FALSE"``
    #: for a boolean, and ``None`` for an error value such as ``#N/A``.
    value: str | float | None
    number_format: str | None


@dataclass(frozen=True)
class Sheet:
    """A worksheet or chart sheet, as the workbook lists it."""

    name: str
    part: str
    is_chartsheet: bool


@dataclass(frozen=True)
class ChartPlacement:
    """Where a chart is drawn: its sheet, its name, and its anchor."""

    sheet: Sheet
    name: str
    part: str
    is_chartex: bool
    row: int
    column: int
    aspect: float | None


class Package:
    """
    An open ``.xlsx`` package.

    Parameters
    ----------
    archive : zipfile.ZipFile
        The open zip archive.

    Raises
    ------
    NotAWorkbookError
        If the archive holds no workbook, or a Strict Open XML one.
    """

    def __init__(self, archive: zipfile.ZipFile) -> None:
        self._zip = archive
        self._names = set(archive.namelist())
        self.workbook = next(
            (
                target
                for rel_type, target in self.rels("").values()
                if rel_type == "officeDocument" and target in self._names
            ),
            "",
        )
        root = self.xml(self.workbook) if self.workbook else None
        if root is not None and root.tag.startswith("{" + _STRICT_PREFIX):
            raise NotAWorkbookError(
                "maidr reads Excel workbooks saved in the default .xlsx format; "
                "this one is Strict Open XML. Save it as 'Excel Workbook "
                "(.xlsx)' and read that copy."
            )
        if root is None or root.tag != f"{{{NS_MAIN}}}workbook":
            raise NotAWorkbookError(
                "maidr found no Excel workbook in this file. It reads .xlsx and "
                ".xlsm files; an older .xls workbook can be saved as .xlsx first."
            )
        pr = root.find(f"{{{NS_MAIN}}}workbookPr")
        self.date1904 = pr is not None and pr.get("date1904") in ("1", "true")
        self._shared_strings: dict[int, str] = {}
        self._formats: list[str | None] | None = None

    def has(self, part: str) -> bool:
        """Whether the package holds ``part``."""
        return part in self._names

    def xml(self, part: str) -> Any:
        """
        Parse one part.

        Parameters
        ----------
        part : str
            The part's path inside the package.

        Returns
        -------
        lxml.etree._Element
            The part's root element.
        """
        return etree.fromstring(self._zip.read(part), _PARSER)

    def rels(self, part: str) -> dict[str, tuple[str, str]]:
        """
        A part's relationships.

        Parameters
        ----------
        part : str
            The source part's path, or ``""`` for the package itself.

        Returns
        -------
        dict
            Relationship id to ``(type, target part path)``, where the type is
            the last segment of the relationship type URI (``"chart"``,
            ``"drawing"``, ...), so the Transitional and Strict spellings and
            Microsoft's own extensions (``"chartEx"``) compare alike. Links
            outside the package are left out.
        """
        folder, name = posixpath.split(part)
        rels_part = posixpath.join(folder, "_rels", name + ".rels")
        if rels_part not in self._names:
            return {}
        out = {}
        for rel in self.xml(rels_part).iter(f"{{{NS_PKG_REL}}}Relationship"):
            if rel.get("TargetMode") == "External":
                continue
            target = rel.get("Target", "")
            if target.startswith("/"):
                resolved = target.lstrip("/")
            else:
                resolved = posixpath.normpath(posixpath.join(folder, target))
            out[rel.get("Id")] = (rel.get("Type", "").rsplit("/", 1)[-1], resolved)
        return out

    def sheets(self) -> list[Sheet]:
        """
        The workbook's sheets, in tab order.

        Returns
        -------
        list of Sheet
            Worksheets and chart sheets; dialog and macro sheets hold no
            charts and are left out.
        """
        rels = self.rels(self.workbook)
        out = []
        for sheet in self.xml(self.workbook).iter(f"{{{NS_MAIN}}}sheet"):
            rel = rels.get(sheet.get(f"{{{NS_REL}}}id", ""))
            if rel is None or rel[0] not in ("worksheet", "chartsheet"):
                continue
            out.append(Sheet(sheet.get("name", ""), rel[1], rel[0] == "chartsheet"))
        return out

    def charts(self) -> list[ChartPlacement]:
        """
        Every chart in the workbook, sheet by sheet in tab order, and within a
        sheet top to bottom and left to right by where it is anchored.

        Returns
        -------
        list of ChartPlacement
            One per chart object, including the Excel 2016 chart types, which
            are kept in their own ``chartEx`` parts.
        """
        out = []
        for sheet in self.sheets():
            if not self.has(sheet.part):
                continue
            placements = []
            for rel_type, drawing in self.rels(sheet.part).values():
                if rel_type == "drawing" and self.has(drawing):
                    placements.extend(self._drawing_charts(sheet, drawing))
            placements.sort(key=lambda p: (p.row, p.column))
            out.extend(placements)
        return out

    def _drawing_charts(self, sheet: Sheet, drawing: str) -> Iterator[ChartPlacement]:
        rels = self.rels(drawing)
        for anchor in self.xml(drawing):
            if not isinstance(anchor.tag, str):
                continue
            row, column, aspect = _anchor_geometry(anchor)
            for frame in anchor.iter(f"{{{NS_XDR}}}graphicFrame"):
                if _in_fallback(frame, anchor):
                    continue
                props = frame.find(f"{{{NS_XDR}}}nvGraphicFramePr/{{{NS_XDR}}}cNvPr")
                data = frame.find(f"{{{NS_A}}}graphic/{{{NS_A}}}graphicData")
                if data is None:
                    continue
                for chart in data:
                    rel = rels.get(chart.get(f"{{{NS_REL}}}id", ""))
                    if rel is None or rel[0] not in ("chart", "chartEx"):
                        continue
                    yield ChartPlacement(
                        sheet=sheet,
                        name=props.get("name", "") if props is not None else "",
                        part=rel[1],
                        is_chartex=rel[0] == "chartEx",
                        row=row,
                        column=column,
                        aspect=aspect,
                    )

    def theme_colors(self) -> dict[str, str]:
        """
        The theme's color scheme.

        Returns
        -------
        dict
            Scheme name (``"accent1"``, ``"dk1"``, ...) to ``"#RRGGBB"``,
            with the aliases charts use (``"tx1"`` for ``"dk1"``, ``"bg1"``
            for ``"lt1"``, and so on). Empty when the workbook has no theme.
        """
        for rel_type, part in self.rels(self.workbook).values():
            if rel_type == "theme" and self.has(part):
                scheme = self.xml(part).find(f".//{{{NS_A}}}clrScheme")
                break
        else:
            return {}
        if scheme is None:
            return {}
        out = {}
        for entry in scheme:
            if not isinstance(entry.tag, str):
                continue
            name = etree.QName(entry).localname
            for color in entry:
                value = color.get("val") if color.tag.endswith("srgbClr") else None
                value = value or color.get("lastClr")
                if value and len(value) == 6:
                    out[name] = "#" + value.upper()
        for alias, name in (
            ("tx1", "dk1"),
            ("bg1", "lt1"),
            ("tx2", "dk2"),
            ("bg2", "lt2"),
        ):
            if name in out:
                out[alias] = out[name]
        return out

    def read_cells(
        self, sheet: Sheet, cells: Iterable[tuple[int, int]]
    ) -> dict[tuple[int, int], Cell]:
        """
        Read some cells of one sheet, in a single streaming pass.

        The sheet is never loaded whole: rows are read in order and the pass
        stops after the last row asked for.

        Parameters
        ----------
        sheet : Sheet
            The worksheet.
        cells : iterable of tuple of int
            Zero-based ``(row, column)`` positions.

        Returns
        -------
        dict
            Position to :class:`Cell`. A cell the sheet does not store, an
            empty one, is absent.
        """
        wanted = set(cells)
        if not wanted or sheet.is_chartsheet or not self.has(sheet.part):
            return {}
        last_row = max(row for row, _ in wanted)
        raw: dict[tuple[int, int], tuple[str, str, str | None]] = {}
        row_index = -1
        with self._zip.open(sheet.part) as stream:
            for _, row in etree.iterparse(
                stream, tag=f"{{{NS_MAIN}}}row", resolve_entities=False
            ):
                row_index = int(row.get("r", row_index + 2)) - 1
                if row_index > last_row:
                    break
                column = -1
                for cell in row.iterchildren(f"{{{NS_MAIN}}}c"):
                    position = parse_cell(cell.get("r", ""))
                    column = position[1] if position else column + 1
                    if (row_index, column) in wanted:
                        raw[(row_index, column)] = _cell_text(cell)
                row.clear()
                while row.getprevious() is not None:
                    del row.getparent()[0]
        strings = self._strings(
            int(text) for kind, text, _ in raw.values() if kind == "s" and text
        )
        formats = self._cell_formats() if raw else []
        out: dict[tuple[int, int], Cell] = {}
        for position, (kind, text, style) in raw.items():
            index = int(style) if style and style.isdigit() else 0
            number_format = formats[index] if index < len(formats) else None
            out[position] = Cell(_cell_value(kind, text, strings), number_format)
        return out

    def _cell_formats(self) -> list[str | None]:
        """The number format of each cell style, by style index."""
        if self._formats is None:
            self._formats = []
            part = next(
                (
                    t
                    for kind, t in self.rels(self.workbook).values()
                    if kind == "styles"
                ),
                None,
            )
            if part is not None and self.has(part):
                root = self.xml(part)
                listed = root.find(f"{{{NS_MAIN}}}numFmts")
                custom = {
                    int(f.get("numFmtId", "-1")): f.get("formatCode")
                    for f in (listed if listed is not None else ())
                    if isinstance(f.tag, str)
                }
                styles = root.find(f"{{{NS_MAIN}}}cellXfs")
                for xf in styles if styles is not None else ():
                    if not isinstance(xf.tag, str):
                        continue
                    number = int(xf.get("numFmtId", "0"))
                    self._formats.append(
                        custom.get(number) or _BUILTIN_FORMATS.get(number)
                    )
        return self._formats

    def _strings(self, indices: Iterable[int]) -> dict[int, str]:
        """The shared strings at ``indices``, read up to the last one needed."""
        missing = {i for i in indices if i not in self._shared_strings}
        if missing:
            part = next(
                (
                    t
                    for kind, t in self.rels(self.workbook).values()
                    if kind == "sharedStrings"
                ),
                None,
            )
            if part is not None and self.has(part):
                last = max(missing)
                with self._zip.open(part) as stream:
                    for index, (_, item) in enumerate(
                        etree.iterparse(
                            stream, tag=f"{{{NS_MAIN}}}si", resolve_entities=False
                        )
                    ):
                        if index in missing:
                            self._shared_strings[index] = _rich_text(item)
                        item.clear()
                        if index >= last:
                            break
        return self._shared_strings


def _cell_text(cell: Any) -> tuple[str, str, str | None]:
    """A cell's type, its raw text and its style, as the sheet stores them."""
    kind = cell.get("t", "n")
    style = cell.get("s")
    if kind == "inlineStr":
        inline = cell.find(f"{{{NS_MAIN}}}is")
        return "str", _rich_text(inline) if inline is not None else "", style
    return kind, cell.findtext(f"{{{NS_MAIN}}}v") or "", style


def _cell_value(kind: str, text: str, strings: dict[int, str]) -> str | float | None:
    if kind == "s":
        return strings.get(int(text)) if text else None
    if kind in ("str", "d"):
        return text
    if kind == "b":
        return "TRUE" if text == "1" else "FALSE"
    if kind == "e":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _rich_text(item: Any) -> str:
    """The text of a string item, without its phonetic (furigana) runs."""
    return "".join(
        t.text or ""
        for t in item.iter(f"{{{NS_MAIN}}}t")
        if t.getparent() is not None and etree.QName(t.getparent()).localname != "rPh"
    )


def _in_fallback(element: Any, stop: Any) -> bool:
    """Whether ``element`` sits in the fallback half of an alternate content."""
    parent = element.getparent()
    while parent is not None and parent is not stop:
        if parent.tag == f"{{{NS_MC}}}Fallback":
            return True
        parent = parent.getparent()
    return False


def _anchor_geometry(anchor: Any) -> tuple[int, int, float | None]:
    """The top-left cell of an anchor, and its height over its width."""
    start = anchor.find(f"{{{NS_XDR}}}from")
    row = int(start.findtext(f"{{{NS_XDR}}}row") or 0) if start is not None else 0
    column = int(start.findtext(f"{{{NS_XDR}}}col") or 0) if start is not None else 0
    width = height = None
    extent = anchor.find(f"{{{NS_XDR}}}ext")
    end = anchor.find(f"{{{NS_XDR}}}to")
    if extent is not None:
        width = int(extent.get("cx", 0)) / _EMU_PER_PIXEL
        height = int(extent.get("cy", 0)) / _EMU_PER_PIXEL
    elif start is not None and end is not None:
        width = _span(start, end, "col", _DEFAULT_COLUMN_PX)
        height = _span(start, end, "row", _DEFAULT_ROW_PX)
    aspect = height / width if width and height and width > 0 and height > 0 else None
    return row, column, aspect


def _span(start: Any, end: Any, axis: str, cell_px: int) -> float:
    cells = int(end.findtext(f"{{{NS_XDR}}}{axis}") or 0) - int(
        start.findtext(f"{{{NS_XDR}}}{axis}") or 0
    )
    offset = int(end.findtext(f"{{{NS_XDR}}}{axis}Off") or 0) - int(
        start.findtext(f"{{{NS_XDR}}}{axis}Off") or 0
    )
    return cells * cell_px + offset / _EMU_PER_PIXEL
