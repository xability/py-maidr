"""Charts read out of an Excel workbook with ``maidr.read_excel_charts``.

The workbooks are written by XlsxWriter, which writes chart parts the way
Excel does -- the same elements, and a cached copy of each series' values --
and is tested against files Excel saved. What XlsxWriter cannot write (a part
with no cached values, multi-level categories, an Excel 2016 chart) is made by
editing the part it wrote.
"""

from __future__ import annotations

import datetime
import io
import json
import re
import warnings
import zipfile
from pathlib import Path
from typing import Any, Callable

import pytest

xlsxwriter = pytest.importorskip("xlsxwriter")

from lxml import etree  # noqa: E402
from lxml.cssselect import CSSSelector  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.excel import ExcelChart, NotAWorkbookError, read_excel_charts  # noqa: E402

SALES = [
    ["Quarter", "North", "South"],
    ["Q1", 120, 95],
    ["Q2", 150, 110],
    ["Q3", 90, 130],
    ["Q4", 175, 160],
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _book(
    tmp_path: Path,
    build: Callable[[Any, Any], None],
    *,
    rows: list[list[Any]] = SALES,
    sheet: str = "Sales",
    **options: Any,
) -> Path:
    """Write ``rows`` to a sheet, let ``build`` add charts, and save."""
    path = tmp_path / "book.xlsx"
    workbook = xlsxwriter.Workbook(str(path), options)
    worksheet = workbook.add_worksheet(sheet)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if value is not None:
                worksheet.write(r, c, value)
    build(workbook, worksheet)
    workbook.close()
    return path


def _add_series(
    chart: Any, column: int, *, sheet: str = "Sales", last: int = 4
) -> None:
    chart.add_series(
        {
            "name": [sheet, 0, column],
            "categories": [sheet, 1, 0, last, 0],
            "values": [sheet, 1, column, last, column],
        }
    )


def _chart(kind: str, columns: tuple[int, ...] = (1, 2), **options: Any) -> Callable:
    """A ``build`` that adds one chart of ``kind`` over ``columns`` at E2."""

    def build(workbook: Any, worksheet: Any) -> None:
        chart = workbook.add_chart({"type": kind, **options})
        for column in columns:
            _add_series(chart, column)
        worksheet.insert_chart("E2", chart)

    return build


def _read(path: Any) -> list[ExcelChart]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return read_excel_charts(path)


def _layers(chart: ExcelChart) -> list[dict]:
    """Every layer of the chart, as the schema maidr.js receives carries it."""
    schema = json.loads(
        json.dumps(FigureManager.get_maidr(chart.figure)._flatten_maidr())
    )
    return [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]


def _only_layer(path: Path) -> dict:
    (chart,) = _read(path)
    (layer,) = _layers(chart)
    return layer


def _values(series: list[dict], key: str = "y") -> list[Any]:
    return [point[key] for point in series]


def _rewrite(path: Path, part: str, edit: Callable[[str], str]) -> Path:
    """A copy of the workbook with one part's text passed through ``edit``."""
    out = path.with_name(f"{path.stem}-edited.xlsx")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == part:
                data = edit(data.decode("utf-8")).encode("utf-8")
            target.writestr(item, data)
    return out


# --------------------------------------------------------------------------
# What each chart type is read as
# --------------------------------------------------------------------------


def test_clustered_columns_read_as_dodged_bars(tmp_path):
    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "column"})
        _add_series(chart, 1)
        _add_series(chart, 2)
        chart.set_title({"name": "Revenue by quarter"})
        chart.set_x_axis({"name": "Quarter of year"})
        chart.set_y_axis({"name": "Revenue (k$)"})
        worksheet.insert_chart("E2", chart)

    (chart,) = _read(_book(tmp_path, build))
    (layer,) = _layers(chart)

    assert chart.sheet == "Sales" and chart.name == "Chart 1"
    assert chart.title == "Revenue by quarter"
    assert layer["type"] == "dodged_bar"
    north, south = layer["data"]
    assert _values(north, "x") == ["Q1", "Q2", "Q3", "Q4"]
    assert _values(north) == [120, 150, 90, 175]
    assert _values(south) == [95, 110, 130, 160]
    assert {north[0]["z"], south[0]["z"]} == {"North", "South"}
    assert layer["axes"]["x"]["label"] == "Quarter of year"
    assert layer["axes"]["y"]["label"] == "Revenue (k$)"


def test_one_series_of_columns_reads_as_a_bar_chart(tmp_path):
    layer = _only_layer(_book(tmp_path, _chart("column", (1,))))

    assert layer["type"] == "bar"
    assert _values(layer["data"], "x") == ["Q1", "Q2", "Q3", "Q4"]
    assert _values(layer["data"]) == [120, 150, 90, 175]


def test_stacked_columns_read_as_a_stacked_bar(tmp_path):
    layer = _only_layer(_book(tmp_path, _chart("column", subtype="stacked")))

    assert layer["type"] == "stacked_bar"
    north, south = layer["data"]
    assert _values(north) == [120, 150, 90, 175]
    assert _values(south) == [95, 110, 130, 160]


def test_percent_stacked_columns_read_as_shares_of_each_category(tmp_path):
    layer = _only_layer(_book(tmp_path, _chart("column", subtype="percent_stacked")))

    assert layer["type"] == "stacked_bar"
    north, south = layer["data"]
    for a, b in zip(_values(north), _values(south)):
        assert a + b == pytest.approx(100)
    assert _values(north)[0] == pytest.approx(100 * 120 / 215)
    assert "%" in json.dumps(layer["axes"]["y"]["format"])


def test_bar_charts_read_horizontally(tmp_path):
    layer = _only_layer(_book(tmp_path, _chart("bar", (1,))))

    assert layer["type"] == "bar"
    assert layer["orientation"] == "horz"
    assert _values(layer["data"], "y") == ["Q1", "Q2", "Q3", "Q4"]
    assert _values(layer["data"], "x") == [120, 150, 90, 175]


def test_line_chart_reads_a_line_per_series(tmp_path):
    layer = _only_layer(_book(tmp_path, _chart("line")))

    assert layer["type"] == "line"
    north, south = layer["data"]
    assert _values(north, "x") == ["Q1", "Q2", "Q3", "Q4"]
    assert _values(north) == [120, 150, 90, 175]
    assert {north[0]["z"], south[0]["z"]} == {"North", "South"}


def test_pie_reads_clockwise_from_the_top_with_the_header_naming_the_slices(tmp_path):
    (chart,) = _read(_book(tmp_path, _chart("pie", (1,))))
    (layer,) = _layers(chart)

    assert layer["type"] == "pie"
    assert _values(layer["data"], "x") == ["Q1", "Q2", "Q3", "Q4"]
    assert _values(layer["data"]) == [120, 150, 90, 175]
    assert layer["axes"]["x"]["label"] == "Quarter"
    assert layer["axes"]["y"]["label"] == "North"
    # Excel titles a one-series chart with the series' name.
    assert chart.title == "North"


def test_doughnut_reads_as_a_pie(tmp_path):
    layer = _only_layer(_book(tmp_path, _chart("doughnut", (2,))))

    assert layer["type"] == "pie"
    assert _values(layer["data"]) == [95, 110, 130, 160]


def test_scatter_reads_points_on_two_numeric_axes(tmp_path):
    rows = [["Spend", "Sales"], [1, 12], [2, 19], [3, 25], [4, 31]]

    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "scatter"})
        chart.add_series(
            {
                "name": "Stores",
                "categories": ["Sales", 1, 0, 4, 0],
                "values": ["Sales", 1, 1, 4, 1],
            }
        )
        chart.set_x_axis({"name": "Ad spend"})
        chart.set_y_axis({"name": "Sales"})
        worksheet.insert_chart("E2", chart)

    layer = _only_layer(_book(tmp_path, build, rows=rows))

    assert layer["type"] == "point"
    assert _values(layer["data"], "x") == [1, 2, 3, 4]
    assert _values(layer["data"]) == [12, 19, 25, 31]
    assert layer["axes"]["x"]["label"] == "Ad spend"
    assert layer["axes"]["y"]["label"] == "Sales"


def test_scatter_with_lines_reads_as_a_line(tmp_path):
    rows = [["x", "y"], [1, 2], [2, 4], [3, 9]]

    def build(workbook, worksheet):
        chart = workbook.add_chart(
            {"type": "scatter", "subtype": "straight_with_markers"}
        )
        chart.add_series(
            {"categories": ["Sales", 1, 0, 3, 0], "values": ["Sales", 1, 1, 3, 1]}
        )
        worksheet.insert_chart("E2", chart)

    layer = _only_layer(_book(tmp_path, build, rows=rows))

    assert layer["type"] == "line"
    (series,) = layer["data"]
    assert _values(series, "x") == [1, 2, 3]
    assert _values(series) == [2, 4, 9]


def test_stacked_area_reads_as_a_stacked_area(tmp_path):
    layer = _only_layer(_book(tmp_path, _chart("area", subtype="stacked")))

    assert layer["type"] == "stacked_area"
    north, south = layer["data"]
    assert _values(north) == [120, 150, 90, 175]
    assert _values(south) == [95, 110, 130, 160]


def test_plain_area_reads_each_band_from_zero(tmp_path):
    (chart,) = _read(_book(tmp_path, _chart("area")))

    north, south = _layers(chart)
    assert north["type"] == south["type"] == "area"
    assert _values(north["data"][0]) == [120, 150, 90, 175]
    assert _values(south["data"][0]) == [95, 110, 130, 160]


def test_combo_on_a_second_axis_is_two_layers_of_one_subplot(tmp_path):
    rows = [["Month", "Revenue", "Margin"]] + [
        [m, 1000 + 250 * i, 0.1 + 0.05 * i] for i, m in enumerate(["Jan", "Feb", "Mar"])
    ]

    def build(workbook, worksheet):
        percent = workbook.add_format({"num_format": "0%"})
        for i in range(3):
            worksheet.write_number(i + 1, 2, rows[i + 1][2], percent)
        columns = workbook.add_chart({"type": "column"})
        columns.add_series(
            {"name": ["Sales", 0, 1], "categories": ["Sales", 1, 0, 3, 0],
             "values": ["Sales", 1, 1, 3, 1]}
        )  # fmt: skip
        line = workbook.add_chart({"type": "line"})
        line.add_series(
            {"name": ["Sales", 0, 2], "categories": ["Sales", 1, 0, 3, 0],
             "values": ["Sales", 1, 2, 3, 2], "y2_axis": True}
        )  # fmt: skip
        columns.combine(line)
        worksheet.insert_chart("E2", columns)

    (chart,) = _read(_book(tmp_path, build, rows=rows))
    schema = FigureManager.get_maidr(chart.figure)._flatten_maidr()

    assert len(schema["subplots"]) == 1 and len(schema["subplots"][0]) == 1
    bars, line = _layers(chart)
    assert bars["type"] == "bar" and line["type"] == "line"
    # Each value axis is named after the one series drawn against it, and the
    # margin keeps the percent format of its cells.
    assert bars["axes"]["y"]["label"] == "Revenue"
    assert line["axes"]["y"]["label"] == "Margin"
    assert line["axes"]["y"]["format"] == {"type": "percent", "decimals": 0}


# --------------------------------------------------------------------------
# Names, titles and order
# --------------------------------------------------------------------------


def test_an_untitled_axis_is_named_after_its_header_but_not_drawn(tmp_path):
    (chart,) = _read(_book(tmp_path, _chart("column")))
    (layer,) = _layers(chart)
    (ax,) = chart.figure.axes

    assert layer["axes"]["x"]["label"] == "Quarter"
    assert not ax.xaxis.label.get_visible()


def test_a_titled_axis_is_drawn(tmp_path):
    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "column"})
        _add_series(chart, 1)
        chart.set_x_axis({"name": "Quarter of year"})
        worksheet.insert_chart("E2", chart)

    (chart,) = _read(_book(tmp_path, build))
    (ax,) = chart.figure.axes

    assert ax.get_xlabel() == "Quarter of year"
    assert ax.xaxis.label.get_visible()


def test_a_deleted_title_stays_deleted(tmp_path):
    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "column"})
        _add_series(chart, 1)
        chart.set_title({"none": True})
        worksheet.insert_chart("E2", chart)

    (chart,) = _read(_book(tmp_path, build))

    assert chart.title is None


def test_charts_are_listed_by_sheet_then_top_to_bottom_and_left_to_right(tmp_path):
    def build(workbook, worksheet):
        for cell, column in (("E20", 1), ("M2", 2), ("E2", 1)):
            chart = workbook.add_chart({"type": "column"})
            _add_series(chart, column)
            chart.set_title({"name": cell})
            worksheet.insert_chart(cell, chart)
        second = workbook.add_worksheet("Later")
        chart = workbook.add_chart({"type": "line"})
        _add_series(chart, 1)
        chart.set_title({"name": "on the second sheet"})
        second.insert_chart("A1", chart)

    charts = _read(_book(tmp_path, build))

    assert [(c.sheet, c.title) for c in charts] == [
        ("Sales", "E2"),
        ("Sales", "M2"),
        ("Sales", "E20"),
        ("Later", "on the second sheet"),
    ]


def test_a_chart_sheet_is_read(tmp_path):
    def build(workbook, worksheet):
        sheet = workbook.add_chartsheet("Share")
        chart = workbook.add_chart({"type": "pie"})
        _add_series(chart, 2)
        sheet.set_chart(chart)

    (chart,) = _read(_book(tmp_path, build))

    assert chart.sheet == "Share"
    assert _layers(chart)[0]["type"] == "pie"


# --------------------------------------------------------------------------
# Values: gaps, dates, formats
# --------------------------------------------------------------------------


def test_a_blank_value_is_a_gap_never_a_zero(tmp_path):
    rows = [list(row) for row in SALES]
    rows[3][1] = None
    (chart,) = _read(_book(tmp_path, _chart("line", (1,)), rows=rows))
    (layer,) = _layers(chart)

    assert _values(layer["data"][0]) == [120, 150, None, 175]


def test_blanks_shown_as_zero_read_as_zero(tmp_path):
    rows = [list(row) for row in SALES]
    rows[3][1] = None

    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "line"})
        _add_series(chart, 1)
        chart.show_blanks_as("zero")
        worksheet.insert_chart("E2", chart)

    layer = _only_layer(_book(tmp_path, build, rows=rows))

    assert _values(layer["data"][0]) == [120, 150, 0, 175]


def test_a_category_with_no_label_reads_blank(tmp_path):
    rows = [list(row) for row in SALES]
    rows[2][0] = None
    layer = _only_layer(_book(tmp_path, _chart("column", (1,)), rows=rows))

    assert _values(layer["data"], "x") == ["Q1", "(blank)", "Q3", "Q4"]


def test_a_repeated_category_on_a_line_reads_its_occurrence(tmp_path):
    rows = [list(row) for row in SALES]
    rows[3][0] = "Q1"
    layer = _only_layer(_book(tmp_path, _chart("line", (1,)), rows=rows))

    assert _values(layer["data"][0], "x") == ["Q1", "Q2", "Q1 (2)", "Q4"]


def test_dates_read_as_the_cells_show_them(tmp_path):
    rows = [["Month", "Revenue"]] + [[None, 1000 + 250 * i] for i in range(3)]

    def build(workbook, worksheet):
        month = workbook.add_format({"num_format": "mmm-yy"})
        for i in range(3):
            worksheet.write_datetime(i + 1, 0, datetime.datetime(2024, i + 1, 1), month)
        chart = workbook.add_chart({"type": "column"})
        chart.add_series(
            {"name": ["Sales", 0, 1], "categories": ["Sales", 1, 0, 3, 0],
             "values": ["Sales", 1, 1, 3, 1]}
        )  # fmt: skip
        worksheet.insert_chart("E2", chart)

    layer = _only_layer(_book(tmp_path, build, rows=rows))

    assert _values(layer["data"], "x") == ["Jan-24", "Feb-24", "Mar-24"]
    assert layer["axes"]["x"]["label"] == "Month"


def test_a_date_axis_reads_in_its_own_format(tmp_path):
    rows = [["Day", "Visits"]] + [[None, 10 * (i + 1)] for i in range(3)]

    def build(workbook, worksheet):
        day = workbook.add_format({"num_format": "yyyy-mm-dd"})
        for i in range(3):
            worksheet.write_datetime(i + 1, 0, datetime.datetime(2024, 1, 15 + i), day)
        chart = workbook.add_chart({"type": "line"})
        chart.add_series(
            {"name": ["Sales", 0, 1], "categories": ["Sales", 1, 0, 3, 0],
             "values": ["Sales", 1, 1, 3, 1]}
        )  # fmt: skip
        chart.set_x_axis({"date_axis": True, "num_format": "d mmm"})
        worksheet.insert_chart("E2", chart)

    layer = _only_layer(_book(tmp_path, build, rows=rows))

    assert _values(layer["data"][0], "x") == ["15 Jan", "16 Jan", "17 Jan"]


def test_dates_count_from_1904_when_the_workbook_does(tmp_path):
    rows = [["Day", "Visits"], [None, 1]]

    def build(workbook, worksheet):
        day = workbook.add_format({"num_format": "yyyy-mm-dd"})
        worksheet.write_datetime(1, 0, datetime.datetime(2024, 3, 1), day)
        chart = workbook.add_chart({"type": "column"})
        chart.add_series(
            {"categories": ["Sales", 1, 0, 1, 0], "values": ["Sales", 1, 1, 1, 1]}
        )
        worksheet.insert_chart("E2", chart)

    layer = _only_layer(_book(tmp_path, build, rows=rows, date_1904=True))

    assert _values(layer["data"], "x") == ["2024-03-01"]


def test_the_value_axis_number_format_is_announced(tmp_path):
    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "column"})
        _add_series(chart, 1)
        chart.set_y_axis({"num_format": "$#,##0"})
        worksheet.insert_chart("E2", chart)

    layer = _only_layer(_book(tmp_path, build))

    assert layer["axes"]["y"]["format"] == {
        "type": "currency",
        "decimals": 0,
        "currency": "USD",
    }


def test_series_are_drawn_in_the_theme_accents_unless_colored(tmp_path):
    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "column"})
        _add_series(chart, 1)
        chart.add_series(
            {"categories": ["Sales", 1, 0, 4, 0], "values": ["Sales", 1, 2, 4, 2],
             "fill": {"color": "#123456"}}
        )  # fmt: skip
        worksheet.insert_chart("E2", chart)

    (chart,) = _read(_book(tmp_path, build))
    (ax,) = chart.figure.axes
    first, second = ax.containers

    # XlsxWriter writes the Office 2007 theme, whose first accent is #4F81BD.
    assert first.patches[0].get_facecolor()[:3] == pytest.approx(
        (0x4F / 255, 0x81 / 255, 0xBD / 255)
    )
    assert second.patches[0].get_facecolor()[:3] == pytest.approx(
        (0x12 / 255, 0x34 / 255, 0x56 / 255)
    )


# --------------------------------------------------------------------------
# What is not read, and says so
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "subtype", "name"),
    [
        ("radar", None, "radar"),
        ("stock", None, "stock"),
        ("line", "stacked", "stacked line"),
    ],
)
def test_a_chart_maidr_does_not_read_is_left_out_with_a_warning(
    tmp_path, kind, subtype, name
):
    options = {"type": kind, **({"subtype": subtype} if subtype else {})}

    def build(workbook, worksheet):
        chart = workbook.add_chart(options)
        for column in (1, 2) if kind != "stock" else (1, 2, 2):
            _add_series(chart, column)
        worksheet.insert_chart("E2", chart)
        readable = workbook.add_chart({"type": "column"})
        _add_series(readable, 1)
        worksheet.insert_chart("E20", readable)

    with pytest.warns(UserWarning, match=f"does not read {name} charts yet; 'Chart 1'"):
        charts = read_excel_charts(_book(tmp_path, build))

    assert [c.name for c in charts] == ["Chart 2"]


def test_the_warning_names_the_line_that_read_the_workbook(tmp_path):
    path = _book(tmp_path, _chart("radar"))

    with pytest.warns(UserWarning, match="radar") as caught:
        read_excel_charts(path)

    assert Path(caught[0].filename).name == Path(__file__).name


def test_an_excel_2016_chart_is_left_out_naming_its_type(tmp_path):
    path = _book(tmp_path, _chart("column", (1,)))
    rels = "xl/drawings/_rels/drawing1.xml.rels"
    edited = _rewrite(
        path,
        rels,
        lambda text: text.replace(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart",
            "http://schemas.microsoft.com/office/2014/relationships/chartEx",
        ),
    )
    edited = _rewrite(
        edited,
        "xl/charts/chart1.xml",
        lambda _: (
            '<cx:chartSpace xmlns:cx="http://schemas.microsoft.com/office/drawing/'
            '2014/chartex"><cx:chart><cx:plotArea><cx:plotAreaRegion>'
            '<cx:series layoutId="waterfall"/></cx:plotAreaRegion></cx:plotArea>'
            "</cx:chart></cx:chartSpace>"
        ),
    )

    with pytest.warns(UserWarning, match="does not read waterfall charts yet"):
        assert read_excel_charts(edited) == []


def test_the_fallback_picture_of_a_newer_chart_is_not_read_as_a_second_chart(tmp_path):
    path = _book(tmp_path, _chart("column", (1,)))
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"

    def wrap(text: str) -> str:
        # Excel keeps a newer chart in an AlternateContent whose Fallback holds
        # a copy for older readers; only the Choice is the chart.
        frame = re.search(r"<xdr:graphicFrame.*?</xdr:graphicFrame>", text, re.S).group(
            0
        )
        return text.replace(
            frame,
            f'<mc:AlternateContent xmlns:mc="{mc}"><mc:Choice Requires="c14">{frame}'
            f"</mc:Choice><mc:Fallback>{frame}</mc:Fallback></mc:AlternateContent>",
        )

    charts = _read(_rewrite(path, "xl/drawings/drawing1.xml", wrap))

    assert len(charts) == 1


# --------------------------------------------------------------------------
# What a chart part can leave out
# --------------------------------------------------------------------------


def test_a_chart_without_cached_values_reads_them_from_the_cells(tmp_path):
    path = _book(tmp_path, _chart("column"))

    def strip(text: str) -> str:
        return re.sub(r"<c:(numCache|strCache)>.*?</c:\1>", "", text, flags=re.S)

    (chart,) = _read(_rewrite(path, "xl/charts/chart1.xml", strip))
    (layer,) = _layers(chart)

    north, south = layer["data"]
    assert _values(north, "x") == ["Q1", "Q2", "Q3", "Q4"]
    assert _values(north) == [120, 150, 90, 175]
    assert {north[0]["z"], south[0]["z"]} == {"North", "South"}


def test_multi_level_categories_read_with_the_level_above(tmp_path):
    path = _book(tmp_path, _chart("column", (1,)))
    levels = (
        "<c:multiLvlStrRef><c:f>Sales!$A$2:$A$5</c:f><c:multiLvlStrCache>"
        '<c:ptCount val="4"/>'
        '<c:lvl><c:pt idx="0"><c:v>H1</c:v></c:pt><c:pt idx="1"><c:v>H2</c:v></c:pt>'
        '<c:pt idx="2"><c:v>H1</c:v></c:pt><c:pt idx="3"><c:v>H2</c:v></c:pt></c:lvl>'
        '<c:lvl><c:pt idx="0"><c:v>2023</c:v></c:pt><c:pt idx="2"><c:v>2024</c:v></c:pt>'
        "</c:lvl></c:multiLvlStrCache></c:multiLvlStrRef>"
    )

    def swap(text: str) -> str:
        return re.sub(
            r"<c:cat>.*?</c:cat>", f"<c:cat>{levels}</c:cat>", text, flags=re.S
        )

    layer = _only_layer(_rewrite(path, "xl/charts/chart1.xml", swap))

    assert _values(layer["data"], "x") == [
        "2023 / H1",
        "2023 / H2",
        "2024 / H1",
        "2024 / H2",
    ]


# --------------------------------------------------------------------------
# Files that are not workbooks, and where a workbook can come from
# --------------------------------------------------------------------------


def test_a_file_that_is_not_a_workbook_says_so(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2\n")

    with pytest.raises(NotAWorkbookError, match="saved as .xlsx"):
        read_excel_charts(path)


def test_a_zip_that_is_not_a_workbook_says_so(tmp_path):
    path = tmp_path / "other.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("readme.txt", "hello")

    with pytest.raises(NotAWorkbookError):
        read_excel_charts(path)

    assert issubclass(NotAWorkbookError, ValueError)


def test_a_workbook_without_charts_reads_as_none(tmp_path):
    assert _read(_book(tmp_path, lambda workbook, worksheet: None)) == []


def test_a_workbook_is_read_from_an_open_stream(tmp_path):
    data = _book(tmp_path, _chart("column", (1,))).read_bytes()

    (chart,) = _read(io.BytesIO(data))

    assert _layers(chart)[0]["type"] == "bar"


# --------------------------------------------------------------------------
# The maidr entry points take an ExcelChart
# --------------------------------------------------------------------------


def test_render_save_html_and_close_take_an_excel_chart(tmp_path):
    (chart,) = _read(_book(tmp_path, _chart("column")))

    html = str(maidr.render(chart, use_cdn=False))
    saved = maidr.save_html(chart, str(tmp_path / "chart.html"), use_cdn=False)
    maidr.close(chart)

    assert "dodged_bar" in html
    assert Path(saved).read_text().count("dodged_bar") >= 1


def test_each_bar_selector_names_one_drawn_bar(tmp_path):
    (chart,) = _read(_book(tmp_path, _chart("column")))

    html = str(maidr.render(chart, use_cdn=False))
    svg = etree.fromstring(
        re.search(r"<svg.*?</svg>", html, re.S).group(0).encode(),
        etree.XMLParser(recover=True),
    )
    for element in svg.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    schema = json.loads(svg.get("maidr"))
    (layer,) = [
        layer for row in schema["subplots"] for c in row for layer in c["layers"]
    ]
    selectors = layer["selectors"]
    selectors = selectors if isinstance(selectors, list) else [selectors]
    found = [element for s in selectors for element in CSSSelector(s)(svg)]

    # Two series of four quarters: one drawn bar each.
    assert len(found) == 8


def test_a_chart_with_nothing_to_read_is_left_out_with_a_warning(tmp_path):
    rows = [["Quarter", "North"], ["Q1", 0], ["Q2", -5]]

    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "pie"})
        chart.add_series(
            {"categories": ["Sales", 1, 0, 2, 0], "values": ["Sales", 1, 1, 2, 1]}
        )
        worksheet.insert_chart("E2", chart)

    with pytest.warns(UserWarning) as caught:
        charts = read_excel_charts(_book(tmp_path, build, rows=rows))

    messages = [str(w.message) for w in caught]
    assert charts == []
    assert any("1 negative value(s)" in m for m in messages)
    assert any("has no data maidr can read" in m for m in messages)


def test_a_damaged_chart_costs_that_chart_and_not_the_workbook(tmp_path):
    def build(workbook, worksheet):
        for cell in ("E2", "E20"):
            chart = workbook.add_chart({"type": "column"})
            _add_series(chart, 1)
            worksheet.insert_chart(cell, chart)

    path = _rewrite(
        _book(tmp_path, build), "xl/charts/chart1.xml", lambda text: text[:200]
    )

    with pytest.warns(UserWarning, match="cannot read 'Chart 1' on sheet 'Sales'"):
        charts = read_excel_charts(path)

    assert [c.name for c in charts] == ["Chart 2"]


def test_a_point_count_a_part_overstates_reads_only_the_points_it_holds(tmp_path):
    path = _book(tmp_path, _chart("column", (1,)))

    def inflate(text: str) -> str:
        return re.sub(r'<c:ptCount val="4"/>', '<c:ptCount val="999999999"/>', text)

    layer = _only_layer(_rewrite(path, "xl/charts/chart1.xml", inflate))

    assert _values(layer["data"]) == [120, 150, 90, 175]
