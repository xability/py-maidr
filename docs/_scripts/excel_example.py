"""Write ``docs/sales.xlsx``, the workbook the Excel gallery reads.

XlsxWriter writes chart parts the way Excel saves them, each with a cached
copy of its values, so the gallery reads what a workbook saved by Excel holds.
It cannot write the chart types Excel 2016 added, which Excel keeps in a part
of their own; for those it writes a column chart titled with a marker, and
the part is then replaced with the one Excel writes for the type.
Run from the repository root after changing it::

    uv run python docs/_scripts/excel_example.py
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import xlsxwriter

OUT = Path(__file__).parents[1] / "sales.xlsx"

ROWS = [
    ("Q1", 120, 95, 0.18),
    ("Q2", 150, 110, 0.21),
    ("Q3", 90, 130, 0.12),
    ("Q4", 175, 160, 0.24),
]


def main() -> None:
    workbook = xlsxwriter.Workbook(str(OUT))
    workbook.set_properties(
        {"title": "Quarterly sales", "created": datetime(2026, 1, 1)}
    )
    sheet = workbook.add_worksheet("Sales")
    bold = workbook.add_format({"bold": True})
    percent = workbook.add_format({"num_format": "0%"})
    sheet.write_row(0, 0, ["Quarter", "North", "South", "Margin"], bold)
    for r, (quarter, north, south, margin) in enumerate(ROWS, start=1):
        sheet.write_row(r, 0, [quarter, north, south])
        sheet.write_number(r, 3, margin, percent)

    def series(chart: object, column: int, **options: object) -> None:
        chart.add_series(  # type: ignore[attr-defined]
            {
                "name": ["Sales", 0, column],
                "categories": ["Sales", 1, 0, 4, 0],
                "values": ["Sales", 1, column, 4, column],
                **options,
            }
        )

    columns = workbook.add_chart({"type": "column"})
    series(columns, 1)
    series(columns, 2)
    columns.set_title({"name": "Revenue by region"})
    columns.set_y_axis({"name": "Revenue ($k)"})
    sheet.insert_chart("F2", columns)

    line = workbook.add_chart({"type": "line"})
    series(line, 1, marker={"type": "circle"})
    series(line, 2, marker={"type": "circle"})
    line.set_title({"name": "Revenue trend"})
    sheet.insert_chart("N2", line)

    pie = workbook.add_chart({"type": "pie"})
    series(pie, 1)
    pie.set_title({"name": "North by quarter"})
    sheet.insert_chart("F18", pie)

    combo = workbook.add_chart({"type": "column"})
    series(combo, 1)
    margin = workbook.add_chart({"type": "line"})
    series(margin, 3, y2_axis=True)
    combo.combine(margin)
    combo.set_title({"name": "North revenue and margin"})
    sheet.insert_chart("N18", combo)

    area = workbook.add_chart({"type": "area", "subtype": "stacked"})
    series(area, 1)
    series(area, 2)
    area.set_title({"name": "Revenue, stacked"})
    sheet.insert_chart("F34", area)

    radar = workbook.add_chart({"type": "radar", "subtype": "with_markers"})
    series(radar, 1)
    series(radar, 2)
    radar.set_title({"name": "Revenue around the year"})
    sheet.insert_chart("N34", radar)

    _prices(workbook, bold)
    _scores(workbook, bold)
    _budget(workbook, bold)
    _products(workbook, bold)
    workbook.close()
    _excel_2016_parts()


PRICES = [
    (datetime(2026, 1, 5), 41.2, 43.0, 40.6, 42.5),
    (datetime(2026, 1, 6), 42.5, 42.9, 41.1, 41.4),
    (datetime(2026, 1, 7), 41.4, 44.2, 41.3, 44.0),
    (datetime(2026, 1, 8), 44.0, 44.8, 43.1, 43.5),
    (datetime(2026, 1, 9), 43.5, 45.6, 43.4, 45.2),
]

SCORES = {
    "Class A": [52, 58, 61, 64, 66, 68, 70, 71, 73, 75, 77, 80, 84, 97],
    "Class B": [45, 55, 59, 62, 63, 67, 69, 72, 74, 78, 79, 83, 88],
}

BUDGET = [
    ("Opening balance", 500),
    ("Sales", 320),
    ("Services", 140),
    ("Salaries", -380),
    ("Rent", -90),
    ("Tax", -60),
    ("Closing balance", 430),
]

PRODUCTS = [
    ("Fruit", "Apples", 120),
    ("Fruit", "Pears", 60),
    ("Fruit", "Plums", 30),
    ("Vegetables", "Carrots", 80),
    ("Vegetables", "Kale", 40),
    ("Bakery", "Bread", 90),
    ("Bakery", "Cakes", 50),
]


def _prices(workbook: Any, bold: Any) -> None:
    sheet = workbook.add_worksheet("Prices")
    day = workbook.add_format({"num_format": "mmm d"})
    sheet.write_row(0, 0, ["Date", "Open", "High", "Low", "Close"], bold)
    for r, (date, *prices) in enumerate(PRICES, start=1):
        sheet.write_datetime(r, 0, date, day)
        sheet.write_row(r, 1, prices)
    stock = workbook.add_chart({"type": "stock"})
    for column in (1, 2, 3, 4):
        stock.add_series(
            {
                "name": ["Prices", 0, column],
                "categories": ["Prices", 1, 0, len(PRICES), 0],
                "values": ["Prices", 1, column, len(PRICES), column],
            }
        )
    stock.set_up_down_bars({})
    stock.set_high_low_lines({})
    stock.set_title({"name": "Share price, first week of January"})
    stock.set_x_axis({"num_format": "mmm d"})
    stock.set_legend({"none": True})
    sheet.insert_chart("G2", stock)


def _scores(workbook: Any, bold: Any) -> None:
    sheet = workbook.add_worksheet("Scores")
    sheet.write_row(0, 0, ["Class", "Score"], bold)
    rows = [(name, score) for name, scores in SCORES.items() for score in scores]
    for r, row in enumerate(rows, start=1):
        sheet.write_row(r, 0, row)
    _placeholder(workbook, sheet, "@histogram", "E2")
    _placeholder(workbook, sheet, "@box", "M2")


def _budget(workbook: Any, bold: Any) -> None:
    sheet = workbook.add_worksheet("Budget")
    sheet.write_row(0, 0, ["Item", "Amount ($k)"], bold)
    for r, row in enumerate(BUDGET, start=1):
        sheet.write_row(r, 0, row)
    _placeholder(workbook, sheet, "@waterfall", "D2")


def _products(workbook: Any, bold: Any) -> None:
    sheet = workbook.add_worksheet("Products")
    sheet.write_row(0, 0, ["Category", "Product", "Sales"], bold)
    for r, row in enumerate(PRODUCTS, start=1):
        sheet.write_row(r, 0, row)
    _placeholder(workbook, sheet, "@treemap", "E2")


def _placeholder(workbook: Any, sheet: Any, marker: str, where: str) -> None:
    """A column chart standing in for an Excel 2016 chart until it is swapped."""
    chart = workbook.add_chart({"type": "column"})
    chart.add_series({"values": [sheet.name, 1, 1, 2, 1]})
    chart.set_title({"name": marker})
    sheet.insert_chart(where, chart)


# --------------------------------------------------------------------------
# The Excel 2016 chart parts
# --------------------------------------------------------------------------

CX = "http://schemas.microsoft.com/office/drawing/2014/chartex"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
CHART = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart"
CHART_EX = "http://schemas.microsoft.com/office/2014/relationships/chartEx"


def _dimension(tag: str, kind: str, formula: str, levels: list[list[Any]]) -> str:
    """A data dimension with its cached levels, innermost first."""
    body = f"<cx:f>{formula}</cx:f>"
    for level in levels:
        code = ' formatCode="General"' if tag == "numDim" else ""
        body += f'<cx:lvl ptCount="{len(level)}"{code}>'
        body += "".join(f'<cx:pt idx="{i}">{v}</cx:pt>' for i, v in enumerate(level))
        body += "</cx:lvl>"
    return f'<cx:{tag} type="{kind}">{body}</cx:{tag}>'


def _part(title: str, layout: str, name: str, data: str, layout_pr: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<cx:chartSpace xmlns:a="{A}" xmlns:cx="{CX}"><cx:chartData>'
        f'<cx:data id="0">{data}</cx:data></cx:chartData><cx:chart><cx:title>'
        f"<cx:tx><cx:txData><cx:v>{title}</cx:v></cx:txData></cx:tx></cx:title>"
        f'<cx:plotArea><cx:plotAreaRegion><cx:series layoutId="{layout}">'
        f"<cx:tx><cx:txData><cx:v>{name}</cx:v></cx:txData></cx:tx>"
        f'<cx:dataId val="0"/><cx:layoutPr>{layout_pr}</cx:layoutPr></cx:series>'
        '</cx:plotAreaRegion><cx:axis id="0"><cx:catScaling gapWidth="0.5"/>'
        '</cx:axis><cx:axis id="1"><cx:valScaling/></cx:axis></cx:plotArea>'
        "</cx:chart></cx:chartSpace>"
    )


def _excel_2016_parts() -> None:
    """Swap each placeholder chart for the Excel 2016 chart it stands for."""
    rows = sum(len(scores) for scores in SCORES.values())
    classes = [name for name, scores in SCORES.items() for _ in scores]
    scores = [score for values in SCORES.values() for score in values]
    parts = {
        "@histogram": _part(
            "Scores, both classes",
            "clusteredColumn",
            "Score",
            _dimension("numDim", "val", f"Scores!$B$2:$B${rows + 1}", [scores]),
            '<cx:binning intervalClosed="r"><cx:binSize val="10"/></cx:binning>',
        ),
        "@box": _part(
            "Scores by class",
            "boxWhisker",
            "Score",
            _dimension("strDim", "cat", f"Scores!$A$2:$A${rows + 1}", [classes])
            + _dimension("numDim", "val", f"Scores!$B$2:$B${rows + 1}", [scores]),
            '<cx:statistics quartileMethod="exclusive"/>',
        ),
        "@waterfall": _part(
            "Cash flow",
            "waterfall",
            "Amount ($k)",
            _dimension(
                "strDim",
                "cat",
                f"Budget!$A$2:$A${len(BUDGET) + 1}",
                [[item for item, _ in BUDGET]],
            )
            + _dimension(
                "numDim",
                "val",
                f"Budget!$B$2:$B${len(BUDGET) + 1}",
                [[amount for _, amount in BUDGET]],
            ),
            '<cx:subtotals><cx:idx val="0"/>'
            f'<cx:idx val="{len(BUDGET) - 1}"/></cx:subtotals>',
        ),
        "@treemap": _part(
            "Sales by product",
            "treemap",
            "Sales",
            _dimension(
                "strDim",
                "cat",
                f"Products!$A$2:$B${len(PRODUCTS) + 1}",
                [[p for _, p, _ in PRODUCTS], [c for c, _, _ in PRODUCTS]],
            )
            + _dimension(
                "numDim",
                "size",
                f"Products!$C$2:$C${len(PRODUCTS) + 1}",
                [[v for _, _, v in PRODUCTS]],
            ),
            "",
        ),
    }
    with zipfile.ZipFile(OUT) as source:
        items = [(item, source.read(item.filename)) for item in source.infolist()]
    swapped = {}
    for item, data in items:
        if item.filename.startswith("xl/charts/chart"):
            found = re.search(rb"<a:t>(@\w+)</a:t>", data)
            if found:
                swapped[Path(item.filename).name] = found.group(1).decode()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as target:
        for item, data in items:
            name = Path(item.filename).name
            if name in swapped:
                data = parts[swapped[name]].encode("utf-8")
            elif item.filename.startswith("xl/drawings/_rels/"):
                text = data.decode("utf-8")
                for chart in swapped:
                    text = re.sub(
                        rf'Type="{CHART}" Target="../charts/{chart}"',
                        f'Type="{CHART_EX}" Target="../charts/{chart}"',
                        text,
                    )
                data = text.encode("utf-8")
            target.writestr(item, data)


if __name__ == "__main__":
    main()
