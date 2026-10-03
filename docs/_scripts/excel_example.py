"""Write ``docs/sales.xlsx``, the workbook the Excel gallery reads.

XlsxWriter writes chart parts the way Excel saves them, each with a cached
copy of its values, so the gallery reads what a workbook saved by Excel holds.
Run from the repository root after changing it::

    uv run python docs/_scripts/excel_example.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

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

    workbook.close()


if __name__ == "__main__":
    main()
