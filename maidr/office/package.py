"""Where a presentation or a document keeps its charts.

A ``.pptx`` or ``.docx`` file is the same kind of package as an ``.xlsx``
workbook, and a chart in it is the same chart part. Only the way to it
differs:

* a presentation lists its slides in slide show order, a slide's shape tree
  holds a graphic frame for each chart, and the slide's relationships name
  the chart part;
* a document's body holds an inline or floating drawing for each chart, in
  reading order, and the document's relationships name the chart part.

Each chart keeps its data in a workbook embedded beside it, which its own
relationships name. That workbook is read only for the cells the chart part
leaves out, as a workbook's sheets are for :func:`maidr.read_excel_charts`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from maidr.excel.package import NS_A, NS_REL, DamagedPartError, OpcPackage, in_fallback

NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS_SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

P = f"{{{NS_P}}}"
W = f"{{{NS_W}}}"
WP = f"{{{NS_WP}}}"
A = f"{{{NS_A}}}"
R_ID = f"{{{NS_REL}}}id"

#: The namespaces of the "Strict" flavour of the format, which Office writes
#: only when asked to save as Strict Open XML.
_STRICT_PREFIX = "http://purl.oclc.org/ooxml/"

#: The relationship types that lead to a chart part: DrawingML, and the
#: chart types Excel 2016 added.
_CHART_TYPES = ("chart", "chartEx")

#: What each kind of main part is, to say which reader a file is for.
_KINDS = {
    f"{{{NS_SPREADSHEET}}}workbook": (
        "an Excel workbook",
        "maidr.read_excel_charts()",
    ),
    f"{P}presentation": (
        "a PowerPoint presentation",
        "maidr.read_powerpoint_charts()",
    ),
    f"{W}document": ("a Word document", "maidr.read_word_charts()"),
}


class NotAPresentationError(ValueError):
    """The file is not a PowerPoint presentation maidr can read."""


class NotADocumentError(ValueError):
    """The file is not a Word document maidr can read."""


@dataclass(frozen=True)
class OfficePlacement:
    """Where a chart is in a presentation or a document."""

    #: In a presentation, the number of the slide the chart is on; in a
    #: document, the chart's place among the document's charts. Both count
    #: from 1.
    number: int
    #: Whether the slide the chart is on is hidden in the slide show.
    hidden: bool
    name: str
    part: str
    is_chartex: bool
    aspect: float | None
    #: The part whose theme the chart is drawn in: a slide master, or the
    #: document.
    theme_owner: str


class _OfficePackage(OpcPackage):
    """A presentation or a document: its main part, checked to be one."""

    #: The main part's element, and what the package is called in messages.
    _ROOT = ""
    _WHAT = ""
    _SAVE_AS = ""
    _ERROR: type[ValueError] = ValueError

    def __init__(self, archive: Any) -> None:
        super().__init__(archive)
        try:
            self.main = self.main_part()
            root = self.xml(self.main) if self.main else None
        except DamagedPartError as error:
            raise self._ERROR(
                f"maidr cannot read this {self._WHAT}, which is damaged ({error})."
            ) from error
        if root is not None and root.tag.startswith("{" + _STRICT_PREFIX):
            raise self._ERROR(
                f"maidr reads {self._WHAT}s saved in the default format; this one "
                f"is Strict Open XML. Save it as '{self._SAVE_AS}' and read that "
                "copy."
            )
        if root is None or root.tag != self._ROOT:
            kind = _KINDS.get(root.tag) if root is not None else None
            if kind is not None:
                raise self._ERROR(
                    f"maidr found no {self._WHAT} in this file, which is {kind[0]}: "
                    f"read its charts with {kind[1]}."
                )
            raise self._ERROR(f"maidr found no {self._WHAT} in this file.")
        self.root = root
        #: What could not be read while finding the charts, said once each by
        #: the caller.
        self.problems: list[str] = []

    def embedded_workbook(self, chart_part: str) -> str | None:
        """
        The workbook a chart keeps its data in.

        Parameters
        ----------
        chart_part : str
            The chart part's path.

        Returns
        -------
        str or None
            The path of the workbook embedded in the package, or ``None`` when
            the chart has none: it was pasted as a picture of its values, or
            its data lives in a workbook outside the file.
        """
        try:
            rels = self.rels(chart_part)
        except DamagedPartError:
            return None
        return next(
            (
                target
                for rel_type, target in rels.values()
                if rel_type == "package" and self.has(target)
            ),
            None,
        )

    def _main_rels(self) -> dict[str, tuple[str, str]] | None:
        """The main part's relationships, or ``None``, noted, when they are
        damaged."""
        try:
            return self.rels(self.main)
        except DamagedPartError as error:
            self.problems.append(
                f"maidr cannot read the {self._WHAT}'s relationships ({error}); "
                "its charts are left out."
            )
            return None


def _charts_in(
    data: Any, rels: dict[str, tuple[str, str]]
) -> Iterator[tuple[str, bool]]:
    """The chart parts a ``graphicData`` names, and whether each is an Excel
    2016 chart."""
    for chart in data:
        if not isinstance(chart.tag, str):
            continue
        rel = rels.get(chart.get(R_ID, ""))
        if rel is not None and rel[0] in _CHART_TYPES:
            yield rel[1], rel[0] == "chartEx"


class Presentation(_OfficePackage):
    """
    An open ``.pptx`` package.

    Parameters
    ----------
    archive : zipfile.ZipFile
        The open zip archive.

    Raises
    ------
    NotAPresentationError
        If the archive holds no presentation, or a Strict Open XML one.
    """

    _ROOT = f"{P}presentation"
    _WHAT = "PowerPoint presentation"
    _SAVE_AS = "PowerPoint Presentation (.pptx)"
    _ERROR = NotAPresentationError

    def charts(self) -> list[OfficePlacement]:
        """
        Every chart in the presentation, slide by slide in slide show order,
        and on a slide in the order of its shapes, groups included.

        Returns
        -------
        list of OfficePlacement
            One per chart, hidden slides included.
        """
        rels = self._main_rels()
        if rels is None:
            return []
        masters = [t for kind, t in rels.values() if kind == "slideMaster"]
        listed = self.root.find(f"{P}sldIdLst")
        entries = (
            [e for e in listed if isinstance(e.tag, str)] if listed is not None else []
        )
        out = []
        for number, entry in enumerate(entries, 1):
            rel = rels.get(entry.get(R_ID, ""))
            if rel is None or rel[0] != "slide" or not self.has(rel[1]):
                continue
            try:
                charts = list(self._slide_charts(number, rel[1], masters))
            except DamagedPartError as error:
                self.problems.append(
                    f"maidr cannot read slide {number} ({error}); the charts on "
                    "it are left out."
                )
                continue
            out.extend(charts)
        return out

    def _slide_charts(
        self, number: int, part: str, masters: list[str]
    ) -> Iterator[OfficePlacement]:
        slide = self.xml(part)
        rels = self.rels(part)
        hidden = slide.get("show") in ("0", "false")
        owner = self._master(rels) or (masters[0] if masters else self.main)
        for frame in slide.iter(f"{P}graphicFrame"):
            data = frame.find(f"{A}graphic/{A}graphicData")
            if data is None or in_fallback(frame, slide):
                continue
            props = frame.find(f"{P}nvGraphicFramePr/{P}cNvPr")
            extent = frame.find(f"{P}xfrm/{A}ext")
            for chart, is_chartex in _charts_in(data, rels):
                yield OfficePlacement(
                    number=number,
                    hidden=hidden,
                    name=props.get("name", "") if props is not None else "",
                    part=chart,
                    is_chartex=is_chartex,
                    aspect=_aspect(extent),
                    theme_owner=owner,
                )

    def _master(self, slide_rels: dict[str, tuple[str, str]]) -> str | None:
        """The slide master a slide's layout follows, whose theme it uses."""
        for kind, layout in slide_rels.values():
            if kind == "slideLayout" and self.has(layout):
                try:
                    layout_rels = self.rels(layout)
                except DamagedPartError:
                    # The chart is drawn in the presentation's first theme.
                    return None
                for master_kind, master in layout_rels.values():
                    if master_kind == "slideMaster" and self.has(master):
                        return master
        return None


class Document(_OfficePackage):
    """
    An open ``.docx`` package.

    Parameters
    ----------
    archive : zipfile.ZipFile
        The open zip archive.

    Raises
    ------
    NotADocumentError
        If the archive holds no document, or a Strict Open XML one.
    """

    _ROOT = f"{W}document"
    _WHAT = "Word document"
    _SAVE_AS = "Word Document (.docx)"
    _ERROR = NotADocumentError

    def charts(self) -> list[OfficePlacement]:
        """
        Every chart in the document's body, in reading order: inline and
        floating ones, and those in text boxes and tables.

        Returns
        -------
        list of OfficePlacement
            One per chart. The copy of a text box Word keeps for older
            programs is skipped, so a chart in one is read once.
        """
        body = self.root.find(f"{W}body")
        rels = self._main_rels() if body is not None else None
        if body is None or rels is None:
            return []
        out = []
        for data in body.iter(f"{A}graphicData"):
            if in_fallback(data, body):
                continue
            charts = list(_charts_in(data, rels))
            if not charts:
                continue
            name, aspect = _drawing_frame(data)
            for chart, is_chartex in charts:
                out.append(
                    OfficePlacement(
                        number=len(out) + 1,
                        hidden=False,
                        name=name,
                        part=chart,
                        is_chartex=is_chartex,
                        aspect=aspect,
                        theme_owner=self.main,
                    )
                )
        return out


def _drawing_frame(data: Any) -> tuple[str, float | None]:
    """
    The name and the proportions of the frame a document's chart is drawn in.

    A chart is usually a drawing of its own, named by its ``wp:docPr``; one in
    a drawing group is a frame of the group, named by its own ``cNvPr``.
    """
    frame = data.getparent().getparent() if data.getparent() is not None else None
    drawing = data
    while drawing is not None and drawing.tag not in (f"{WP}inline", f"{WP}anchor"):
        drawing = drawing.getparent()
    if frame is not None and frame is not drawing:
        props = frame.find("{*}cNvPr")
        extent = frame.find(f"{{*}}xfrm/{A}ext")
        if props is not None:
            return props.get("name", ""), _aspect(extent)
    if drawing is None:
        return "", None
    props = drawing.find(f"{WP}docPr")
    name = props.get("name", "") if props is not None else ""
    return name, _aspect(drawing.find(f"{WP}extent"))


def _aspect(extent: Any) -> float | None:
    """A frame's height over its width, from its ``cx`` and ``cy`` in EMUs."""
    if extent is None:
        return None
    try:
        width = int(extent.get("cx", "0"))
        height = int(extent.get("cy", "0"))
    except ValueError:
        # A damaged size costs the chart its proportions, not the chart.
        return None
    return height / width if width > 0 and height > 0 else None
