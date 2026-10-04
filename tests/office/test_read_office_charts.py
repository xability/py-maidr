"""Charts read out of a presentation or a document.

A chart on a slide or in a document is the chart part an Excel workbook keeps,
with its data in a workbook embedded beside it. So each case here starts from a
workbook XlsxWriter writes, as ``tests/excel`` does, and moves its chart parts
into a presentation or a document laid out the way PowerPoint and Word save
them: the workbook itself becomes each chart's embedded workbook. What
``read_powerpoint_charts`` and ``read_word_charts`` read is then held to what
``read_excel_charts`` reads from the workbook the charts came from.
"""

from __future__ import annotations

import io
import re
import warnings
import zipfile
from pathlib import Path
from typing import Any, Callable

import pytest

xlsxwriter = pytest.importorskip("xlsxwriter")

import maidr  # noqa: E402
from maidr.excel.package import Package  # noqa: E402
from maidr.office import (  # noqa: E402
    NotADocumentError,
    NotAPresentationError,
    PowerPointChart,
    WordChart,
    read_powerpoint_charts,
    read_word_charts,
)
from tests.excel.test_every_chart_type import (  # noqa: E402
    TREE,
    _excel_2016,
    _sales_part,
    _tree_part,
)
from tests.excel.test_read_excel_charts import (  # noqa: E402
    _add_series,
    _book,
    _chart,
    _layers,
    _read,
    _rewrite,
    _values,
)

REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CHART_REL = f"{REL}/chart"
CHARTEX_REL = "http://schemas.microsoft.com/office/2014/relationships/chartEx"
CHART_URI = "http://schemas.openxmlformats.org/drawingml/2006/chart"
CHARTEX_URI = "http://schemas.microsoft.com/office/drawing/2014/chartex"

NAMESPACES = (
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    f'xmlns:r="{REL}" '
    'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
    f'xmlns:cx="{CHARTEX_URI}" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:cx1="http://schemas.microsoft.com/office/drawing/2015/9/8/chartex"'
)
P_NS = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
W_NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/'
    'wordprocessingDrawing" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml"'
)

#: A chart's size on a slide or a page, in EMUs: 16 by 9 centimetres.
EXTENT = 'cx="5760000" cy="3240000"'


# --------------------------------------------------------------------------
# Presentations and documents built around a workbook's charts
# --------------------------------------------------------------------------


def _rels(*rels: tuple[str, str]) -> str:
    """A relationships part, its ids ``rId1`` up in the order given."""
    body = "".join(
        f'<Relationship Id="rId{i}" Type="{kind}" Target="{target}"/>'
        for i, (kind, target) in enumerate(rels, 1)
    )
    return f'<Relationships xmlns="{PKG}">{body}</Relationships>'


def _charts_of(book: Path) -> list[tuple[bytes, bool]]:
    """Each chart part of a workbook, in order, and whether it is Excel 2016's."""
    with zipfile.ZipFile(book) as archive:
        return [(archive.read(p.part), p.is_chartex) for p in Package(archive).charts()]


def _graphic(rid: int, chartex: bool) -> str:
    uri, tag = (CHARTEX_URI, "cx:chart") if chartex else (CHART_URI, "c:chart")
    return (
        f'<a:graphic><a:graphicData uri="{uri}"><{tag} r:id="rId{rid}"/>'
        "</a:graphicData></a:graphic>"
    )


def _offered(choice: str, fallback: str, requires: str = "cx1") -> str:
    """Markup offered as Office offers an Excel 2016 chart: with a stand-in
    for programs that do not read what ``requires`` names."""
    return (
        f'<mc:AlternateContent><mc:Choice Requires="{requires}">{choice}'
        f"</mc:Choice><mc:Fallback>{fallback}</mc:Fallback></mc:AlternateContent>"
    )


def _write(path: Path, files: dict[str, bytes | str]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def _chart_files(
    folder: str, charts: list[tuple[bytes, bool]], workbook: bytes | None
) -> tuple[dict[str, bytes | str], list[str]]:
    """The chart parts, each with its own copy of the embedded workbook, and
    each part's path relative to ``folder``'s main parts."""
    files: dict[str, bytes | str] = {}
    targets = []
    for n, (part, chartex) in enumerate(charts, 1):
        name = f"chartEx{n}.xml" if chartex else f"chart{n}.xml"
        files[f"{folder}/charts/{name}"] = part
        if workbook is not None:
            embedded = f"Microsoft_Excel_Worksheet{n}.xlsx"
            files[f"{folder}/embeddings/{embedded}"] = workbook
            files[f"{folder}/charts/_rels/{name}.rels"] = _rels(
                (f"{REL}/package", f"../embeddings/{embedded}")
            )
        targets.append(f"charts/{name}")
    return files, targets


def _theme(book: Path) -> bytes:
    with zipfile.ZipFile(book) as archive:
        return archive.read("xl/theme/theme1.xml")


def _presentation(
    book: Path,
    *,
    slides: list[list[int]] | None = None,
    hidden: tuple[int, ...] = (),
    grouped: bool = False,
    twice: bool = False,
    embedded: bool | bytes = True,
) -> Path:
    """
    A presentation of the workbook's charts, one slide each unless
    ``slides`` lists which charts are on which slide; ``hidden`` slides are
    hidden in the slide show, and ``grouped`` puts each slide's charts in a
    group. With ``twice``, each chart's frame is offered again as the
    fallback of markup some programs do not read. ``embedded`` is the
    workbook embedded with each chart: the workbook itself, these bytes, or
    none.
    """
    charts = _charts_of(book)
    slides = slides if slides is not None else [[i] for i in range(len(charts))]
    workbook = book.read_bytes() if embedded is True else embedded or None
    files, targets = _chart_files("ppt", charts, workbook)
    files["_rels/.rels"] = _rels((f"{REL}/officeDocument", "ppt/presentation.xml"))
    listed = "".join(
        f'<p:sldId id="{256 + n}" r:id="rId{n + 2}"/>' for n in range(len(slides))
    )
    files["ppt/presentation.xml"] = (
        f"<p:presentation {P_NS} {NAMESPACES}>"
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/>'
        f"</p:sldMasterIdLst><p:sldIdLst>{listed}</p:sldIdLst>"
        '<p:sldSz cx="12192000" cy="6858000"/></p:presentation>'
    )
    files["ppt/_rels/presentation.xml.rels"] = _rels(
        (f"{REL}/slideMaster", "slideMasters/slideMaster1.xml"),
        *[(f"{REL}/slide", f"slides/slide{n + 1}.xml") for n in range(len(slides))],
    )
    empty_tree = "<p:cSld><p:spTree/></p:cSld>"
    files["ppt/slideMasters/slideMaster1.xml"] = (
        f"<p:sldMaster {P_NS}>{empty_tree}</p:sldMaster>"
    )
    files["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = _rels(
        (f"{REL}/slideLayout", "../slideLayouts/slideLayout1.xml"),
        (f"{REL}/theme", "../theme/theme1.xml"),
    )
    files["ppt/slideLayouts/slideLayout1.xml"] = (
        f"<p:sldLayout {P_NS}>{empty_tree}</p:sldLayout>"
    )
    files["ppt/slideLayouts/_rels/slideLayout1.xml.rels"] = _rels(
        (f"{REL}/slideMaster", "../slideMasters/slideMaster1.xml")
    )
    files["ppt/theme/theme1.xml"] = _theme(book)
    for n, members in enumerate(slides, 1):
        shapes = ""
        for k, index in enumerate(members):
            chartex = charts[index][1]
            frame = (
                "<p:graphicFrame><p:nvGraphicFramePr>"
                f'<p:cNvPr id="{k + 2}" name="Chart {index + 1}"/>'
                "<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>"
                f'<p:xfrm><a:off x="0" y="0"/><a:ext {EXTENT}/></p:xfrm>'
                f"{_graphic(k + 2, chartex)}</p:graphicFrame>"
            )
            if chartex:
                picture = (
                    f'<p:sp><p:nvSpPr><p:cNvPr id="{k + 2}" name="Chart '
                    f'{index + 1}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
                    "<p:spPr/></p:sp>"
                )
                frame = _offered(frame, picture)
            elif twice:
                frame = _offered(frame, frame, requires="p14")
            shapes += frame
        if grouped:
            shapes = (
                '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="99" name="Group 1"/>'
                f"<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>{shapes}"
                "</p:grpSp>"
            )
        show = ' show="0"' if n in hidden else ""
        files[f"ppt/slides/slide{n}.xml"] = (
            f"<p:sld {P_NS} {NAMESPACES}{show}><p:cSld><p:spTree>"
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
            f"</p:nvGrpSpPr><p:grpSpPr/>{shapes}</p:spTree></p:cSld></p:sld>"
        )
        files[f"ppt/slides/_rels/slide{n}.xml.rels"] = _rels(
            (f"{REL}/slideLayout", "../slideLayouts/slideLayout1.xml"),
            *[
                (
                    CHARTEX_REL if charts[i][1] else CHART_REL,
                    f"../{targets[i]}",
                )
                for i in members
            ],
        )
    return _write(book.with_name("deck.pptx"), files)


def _inline(rid: int, n: int, chartex: bool) -> str:
    return (
        f"<w:drawing><wp:inline><wp:extent {EXTENT}/>"
        f'<wp:docPr id="{n}" name="Chart {n}"/>{_graphic(rid, chartex)}'
        "</wp:inline></w:drawing>"
    )


def _document(
    book: Path, *, text_box: bool = False, embedded: bool | bytes = True
) -> Path:
    """
    A document of the workbook's charts, one paragraph each; with
    ``text_box`` the first chart is in a text box, which Word also writes as
    VML for older programs, with the chart in it again.
    """
    charts = _charts_of(book)
    workbook = book.read_bytes() if embedded is True else embedded or None
    files, targets = _chart_files("word", charts, workbook)
    files["_rels/.rels"] = _rels((f"{REL}/officeDocument", "word/document.xml"))
    paragraphs = ""
    for n, (_, chartex) in enumerate(charts, 1):
        drawing = _inline(n + 1, n, chartex)
        if chartex:
            drawing = _offered(drawing, "<w:t>[Chart]</w:t>")
        if text_box and n == 1:
            box = f"<w:txbxContent><w:p><w:r>{drawing}</w:r></w:p></w:txbxContent>"
            drawing = (
                '<mc:AlternateContent><mc:Choice Requires="wps"><w:drawing>'
                f'<wp:anchor><wp:extent {EXTENT}/><wp:docPr id="90" name="Text Box '
                '1"/><a:graphic><a:graphicData uri="http://schemas.microsoft.com/'
                f'office/word/2010/wordprocessingShape"><wps:wsp><wps:txbx>{box}'
                "</wps:txbx></wps:wsp></a:graphicData></a:graphic></wp:anchor>"
                "</w:drawing></mc:Choice><mc:Fallback><w:pict><v:shape>"
                f"<v:textbox>{box}</v:textbox></v:shape></w:pict></mc:Fallback>"
                "</mc:AlternateContent>"
            )
        paragraphs += f"<w:p><w:r><w:t>Figure {n}</w:t></w:r></w:p>"
        paragraphs += f"<w:p><w:r>{drawing}</w:r></w:p>"
    files["word/document.xml"] = (
        f"<w:document {W_NS} {NAMESPACES}><w:body>{paragraphs}<w:sectPr/>"
        "</w:body></w:document>"
    )
    files["word/_rels/document.xml.rels"] = _rels(
        (f"{REL}/theme", "theme/theme1.xml"),
        *[
            (CHARTEX_REL if chartex else CHART_REL, target)
            for (_, chartex), target in zip(charts, targets)
        ],
    )
    files["word/theme/theme1.xml"] = _theme(book)
    return _write(book.with_name("report.docx"), files)


def _quietly(read: Callable[[Any], list], path: Any) -> list:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return read(path)


def _comparable(layers: list[dict]) -> list[dict]:
    """The layers without the ids each reading draws afresh."""
    return [
        {k: v for k, v in layer.items() if k not in ("id", "selectors")}
        for layer in layers
    ]


def _two_charts(workbook: Any, worksheet: Any) -> None:
    for kind, cell in (("column", "E2"), ("line", "E20")):
        chart = workbook.add_chart({"type": kind})
        _add_series(chart, 1)
        _add_series(chart, 2)
        chart.set_title({"name": f"Sales by quarter ({kind})"})
        worksheet.insert_chart(cell, chart)


def _three_charts(workbook: Any, worksheet: Any) -> None:
    for kind, cell in (("column", "E2"), ("line", "E20"), ("pie", "E38")):
        chart = workbook.add_chart({"type": kind})
        _add_series(chart, 1)
        worksheet.insert_chart(cell, chart)


# --------------------------------------------------------------------------
# Every chart reads as it does in the workbook it came from
# --------------------------------------------------------------------------

BUILDS = {
    "clustered column": lambda tmp: _book(tmp, _chart("column")),
    "stacked bar": lambda tmp: _book(tmp, _chart("bar", subtype="stacked")),
    "line": lambda tmp: _book(tmp, _chart("line")),
    "pie": lambda tmp: _book(tmp, _chart("pie", (1,))),
    "doughnut": lambda tmp: _book(tmp, _chart("doughnut", (1,))),
    "scatter": lambda tmp: _book(tmp, _chart("scatter", subtype="straight")),
    "stacked area": lambda tmp: _book(tmp, _chart("area", subtype="stacked")),
    "radar": lambda tmp: _book(tmp, _chart("radar")),
    "waterfall": lambda tmp: _excel_2016(
        tmp, _sales_part("waterfall", [120, 150, 90, 175])
    ),
    "funnel": lambda tmp: _excel_2016(tmp, _sales_part("funnel", [175, 150, 120, 90])),
    "treemap": lambda tmp: _excel_2016(tmp, _tree_part("treemap"), TREE),
}


@pytest.mark.parametrize("build", sorted(BUILDS))
@pytest.mark.parametrize(
    "office", [(_presentation, read_powerpoint_charts), (_document, read_word_charts)]
)
def test_each_chart_reads_as_it_does_in_its_workbook(tmp_path, build, office):
    make, read = office
    book = BUILDS[build](tmp_path)
    (excel,) = _read(book)

    (chart,) = _quietly(read, make(book))

    assert chart.title == excel.title
    assert _comparable(_layers(chart)) == _comparable(_layers(excel))


@pytest.mark.parametrize("make", [_presentation, _document])
def test_a_chart_is_drawn_in_the_theme_s_colors(tmp_path, make):
    book = _book(tmp_path, _chart("column"))
    (excel,) = _read(book)
    read = read_powerpoint_charts if make is _presentation else read_word_charts

    (chart,) = _quietly(read, make(book))

    colors = [p.get_facecolor() for p in chart.figure.axes[0].patches]
    assert colors == [p.get_facecolor() for p in excel.figure.axes[0].patches]
    assert len(set(colors)) == 2


# --------------------------------------------------------------------------
# Presentations
# --------------------------------------------------------------------------


def test_a_presentation_reads_slide_by_slide_and_says_where(tmp_path):
    book = _book(tmp_path, _three_charts)

    charts = _quietly(read_powerpoint_charts, _presentation(book, slides=[[1, 0], [2]]))

    assert all(isinstance(chart, PowerPointChart) for chart in charts)
    assert [(c.slide, c.name) for c in charts] == [
        (1, "Chart 2"),
        (1, "Chart 1"),
        (2, "Chart 3"),
    ]
    assert [_layers(c)[0]["type"] for c in charts] == ["line", "bar", "pie"]
    assert not any(chart.hidden for chart in charts)


def test_a_hidden_slide_s_charts_are_read_and_say_so(tmp_path):
    book = _book(tmp_path, _two_charts)

    charts = _quietly(read_powerpoint_charts, _presentation(book, hidden=(2,)))

    assert [(c.slide, c.hidden) for c in charts] == [(1, False), (2, True)]
    assert charts[1].title == "Sales by quarter (line)"


def test_a_chart_in_a_group_is_read(tmp_path):
    book = _book(tmp_path, _two_charts)

    charts = _quietly(
        read_powerpoint_charts, _presentation(book, slides=[[0, 1]], grouped=True)
    )

    assert [(c.slide, c.name) for c in charts] == [(1, "Chart 1"), (1, "Chart 2")]


def test_an_excel_2016_chart_is_read_once_and_not_through_its_stand_in(tmp_path):
    book = _excel_2016(tmp_path, _sales_part("waterfall", [120, 150, 90, 175]))
    deck = _presentation(book)
    with zipfile.ZipFile(deck) as archive:
        slide = archive.read("ppt/slides/slide1.xml").decode()
    # The stand-in names the chart too: only one of the two is read.
    assert slide.count('name="Chart 1"') == 2

    (chart,) = _quietly(read_powerpoint_charts, deck)

    assert _layers(chart)[0]["type"] == "waterfall"


def test_a_chart_offered_again_as_a_fallback_is_read_once(tmp_path):
    book = _book(tmp_path, _two_charts)

    charts = _quietly(read_powerpoint_charts, _presentation(book, twice=True))

    assert [(c.slide, c.name) for c in charts] == [(1, "Chart 1"), (2, "Chart 2")]


def test_a_presentation_can_be_read_from_a_stream(tmp_path):
    deck = _presentation(_book(tmp_path, _chart("column", (1,))))

    (chart,) = _quietly(read_powerpoint_charts, io.BytesIO(deck.read_bytes()))

    assert _values(_layers(chart)[0]["data"]) == [120, 150, 90, 175]


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------


def test_a_document_reads_in_reading_order_and_numbers_its_charts(tmp_path):
    book = _book(tmp_path, _three_charts)

    charts = _quietly(read_word_charts, _document(book))

    assert all(isinstance(chart, WordChart) for chart in charts)
    assert [(c.number, c.name) for c in charts] == [
        (1, "Chart 1"),
        (2, "Chart 2"),
        (3, "Chart 3"),
    ]
    assert [_layers(c)[0]["type"] for c in charts] == ["bar", "line", "pie"]


def test_a_chart_in_a_text_box_is_read_once(tmp_path):
    book = _book(tmp_path, _two_charts)
    report = _document(book, text_box=True)
    with zipfile.ZipFile(report) as archive:
        body = archive.read("word/document.xml").decode()
    # Word keeps the text box twice, the chart in both copies.
    assert body.count('r:id="rId2"') == 2

    charts = _quietly(read_word_charts, report)

    assert [(c.number, c.title) for c in charts] == [
        (1, "Sales by quarter (column)"),
        (2, "Sales by quarter (line)"),
    ]


# --------------------------------------------------------------------------
# The embedded workbook
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("make", "read"),
    [(_presentation, read_powerpoint_charts), (_document, read_word_charts)],
)
def test_an_untitled_axis_is_named_after_a_header_in_the_embedded_workbook(
    tmp_path, make, read
):
    book = _book(tmp_path, _chart("column", (1,)))

    (named,) = _quietly(read, make(book))
    (unnamed,) = _quietly(read, make(book, embedded=False))

    assert _layers(named)[0]["axes"]["x"]["label"] == "Quarter"
    assert _layers(unnamed)[0]["axes"]["x"]["label"] != "Quarter"
    # Without the workbook, the values still come from the chart's own copy.
    assert _values(_layers(unnamed)[0]["data"]) == [120, 150, 90, 175]


def test_a_chart_with_no_copy_of_its_values_reads_the_embedded_workbook(tmp_path):
    def strip(text: str) -> str:
        return re.sub(r"<c:(numCache|strCache)>.*?</c:\1>", "", text, flags=re.S)

    book = _rewrite(_book(tmp_path, _chart("column")), "xl/charts/chart1.xml", strip)

    (chart,) = _quietly(read_powerpoint_charts, _presentation(book))

    north, south = _layers(chart)[0]["data"]
    assert _values(north, "x") == ["Q1", "Q2", "Q3", "Q4"]
    assert _values(north) == [120, 150, 90, 175]
    assert {north[0]["z"], south[0]["z"]} == {"North", "South"}


def test_an_excel_2016_chart_reads_its_header_through_the_embedded_names(tmp_path):
    book = _excel_2016(tmp_path, _sales_part("funnel", [175, 150, 120, 90]))
    (excel,) = _read(book)

    (chart,) = _quietly(read_word_charts, _document(book))

    assert _comparable(_layers(chart)) == _comparable(_layers(excel))


def test_a_damaged_embedded_workbook_costs_its_cells_not_its_chart(tmp_path):
    book = _book(tmp_path, _chart("column", (1,)))

    with pytest.warns(
        UserWarning,
        match="cannot read the workbook 'Chart 1' on slide 1 keeps its data in",
    ):
        (chart,) = read_powerpoint_charts(
            _presentation(book, embedded=b"not a workbook")
        )

    assert _values(_layers(chart)[0]["data"]) == [120, 150, 90, 175]


# --------------------------------------------------------------------------
# Damaged files, and files of another kind
# --------------------------------------------------------------------------


def test_a_damaged_chart_part_costs_that_chart_alone(tmp_path):
    book = _rewrite(
        _book(tmp_path, _two_charts), "xl/charts/chart1.xml", lambda text: text[:200]
    )

    with pytest.warns(UserWarning, match="cannot read 'Chart 1' on slide 1"):
        charts = read_powerpoint_charts(_presentation(book))

    assert [c.name for c in charts] == ["Chart 2"]


def test_a_damaged_chart_part_in_a_document_says_which_chart(tmp_path):
    book = _rewrite(
        _book(tmp_path, _two_charts), "xl/charts/chart2.xml", lambda text: text[:200]
    )

    with pytest.warns(
        UserWarning, match=r"cannot read 'Chart 2' \(chart 2 of the document\)"
    ):
        charts = read_word_charts(_document(book))

    assert [c.number for c in charts] == [1]


def test_a_damaged_slide_costs_the_charts_on_it(tmp_path):
    book = _book(tmp_path, _two_charts)
    deck = _rewrite(
        _presentation(book), "ppt/slides/slide1.xml", lambda text: text[:100]
    )

    with pytest.warns(UserWarning, match="cannot read slide 1"):
        charts = read_powerpoint_charts(deck)

    assert [c.slide for c in charts] == [2]


@pytest.mark.parametrize(
    ("make", "read", "part"),
    [
        (_presentation, read_powerpoint_charts, "ppt/slides/slide1.xml"),
        (_document, read_word_charts, "word/document.xml"),
    ],
)
def test_a_frame_whose_size_is_not_a_number_is_still_read(tmp_path, make, read, part):
    book = _book(tmp_path, _chart("column", (1,)))
    damaged = _rewrite(
        make(book), part, lambda text: text.replace('cx="5760000"', 'cx="wide"')
    )

    (chart,) = _quietly(read, damaged)

    assert _values(_layers(chart)[0]["data"]) == [120, 150, 90, 175]


@pytest.mark.parametrize(
    ("read", "error"),
    [
        (read_powerpoint_charts, NotAPresentationError),
        (read_word_charts, NotADocumentError),
    ],
)
def test_a_file_that_is_not_a_zip_says_what_is_read(tmp_path, read, error):
    path = tmp_path / "old.ppt"
    path.write_bytes(b"\xd0\xcf\x11\xe0 an old binary file")

    with pytest.raises(error, match="can be saved as"):
        read(path)
    assert issubclass(error, ValueError)


def test_a_workbook_is_sent_to_the_reader_for_workbooks(tmp_path):
    book = _book(tmp_path, _chart("column"))

    with pytest.raises(NotAPresentationError, match=r"maidr\.read_excel_charts\(\)"):
        read_powerpoint_charts(book)
    with pytest.raises(NotADocumentError, match=r"maidr\.read_excel_charts\(\)"):
        read_word_charts(book)


def test_a_presentation_and_a_document_are_sent_to_each_other_s_reader(tmp_path):
    book = _book(tmp_path, _chart("column"))
    deck, report = _presentation(book), _document(book)

    with pytest.raises(NotADocumentError, match=r"read_powerpoint_charts\(\)"):
        read_word_charts(deck)
    with pytest.raises(NotAPresentationError, match=r"read_word_charts\(\)"):
        read_powerpoint_charts(report)


def test_a_strict_open_xml_file_says_how_to_save_it(tmp_path):
    book = _book(tmp_path, _chart("column"))

    def strict(text: str) -> str:
        return text.replace(
            "http://schemas.openxmlformats.org/presentationml/2006/main",
            "http://purl.oclc.org/ooxml/presentationml/main",
        )

    deck = _rewrite(_presentation(book), "ppt/presentation.xml", strict)

    with pytest.raises(NotAPresentationError, match="Strict Open XML"):
        read_powerpoint_charts(deck)


# --------------------------------------------------------------------------
# The charts read are what maidr shows
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("make", "read"),
    [(_presentation, read_powerpoint_charts), (_document, read_word_charts)],
)
def test_a_chart_read_is_shown_rendered_and_saved_like_a_figure(tmp_path, make, read):
    (chart,) = _quietly(read, make(_book(tmp_path, _chart("column", (1,)))))

    html = str(maidr.render(chart, use_cdn=False))
    out = tmp_path / "chart.html"
    maidr.save_html(chart, str(out), use_cdn=False)

    assert "maidr" in html and "Q1" in html
    assert out.read_text(encoding="utf-8").count("Q4") >= 1
    maidr.close(chart)
