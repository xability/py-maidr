"""A chart read out of an Excel workbook is driven from the keyboard.

``maidr.read_excel_charts`` draws a workbook's chart again with matplotlib,
and the markup tests cannot tell whether the page a reader gets from it works.
This opens two such pages. In a clustered column chart, Right moves along the
quarters, named after the header cell above them because the axis has no
title, Up moves to the other region, and the bar being read is outlined. In a
combo chart, Page Up reaches the margin line drawn on a second axis, which is
read as the percentage its cells are formatted as.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

xlsxwriter = pytest.importorskip("xlsxwriter")

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"

ROWS = [("Q1", 120, 95, 0.18), ("Q2", 150, 110, 0.21), ("Q3", 90, 130, 0.12)]


@pytest.fixture
def pages(tmp_path) -> tuple[Path, Path]:
    """The clustered column chart's page and the combo chart's page."""
    import maidr

    book = tmp_path / "sales.xlsx"
    workbook = xlsxwriter.Workbook(str(book))
    sheet = workbook.add_worksheet("Sales")
    percent = workbook.add_format({"num_format": "0%"})
    sheet.write_row(0, 0, ["Quarter", "North", "South", "Margin"])
    for r, (quarter, north, south, margin) in enumerate(ROWS, start=1):
        sheet.write_row(r, 0, [quarter, north, south])
        sheet.write_number(r, 3, margin, percent)

    def series(chart, column, **options):
        chart.add_series(
            {
                "name": ["Sales", 0, column],
                "categories": ["Sales", 1, 0, 3, 0],
                "values": ["Sales", 1, column, 3, column],
                **options,
            }
        )

    columns = workbook.add_chart({"type": "column"})
    series(columns, 1)
    series(columns, 2)
    sheet.insert_chart("F2", columns)
    combo = workbook.add_chart({"type": "column"})
    series(combo, 1)
    line = workbook.add_chart({"type": "line"})
    series(line, 3, y2_axis=True)
    combo.combine(line)
    sheet.insert_chart("F18", combo)
    workbook.close()

    clustered, mixed = maidr.read_excel_charts(book)
    out = []
    for chart in (clustered, mixed):
        path = tmp_path / f"{chart.name}.html"
        # Bundled rather than CDN: the shipped bundle is the thing under test.
        maidr.save_html(chart, file=str(path), use_cdn=False)
        maidr.close(chart)
        out.append(path)
    return out[0], out[1]


def _open(browser, path: Path):
    page = browser.new_page()
    page.goto(path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)
    return page


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_quarters_and_regions_of_a_column_chart_are_read(browser, pages):
    clustered, _ = pages
    page = _open(browser, clustered)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        spoken = _step(page, "ArrowRight")
        assert "Quarter is Q1" in spoken and "120" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowRight")
        assert "Q2" in spoken and "150" in spoken, spoken

        spoken = _step(page, "ArrowUp")
        assert "Q2" in spoken and "110" in spoken and "South" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1
        assert not errors, errors
    finally:
        page.close()


def test_the_margin_on_a_second_axis_is_a_layer_read_as_a_percentage(browser, pages):
    _, mixed = pages
    page = _open(browser, mixed)
    try:
        spoken = _step(page, "ArrowRight")
        assert "North is 120" in spoken, spoken

        spoken = _step(page, "PageUp")
        assert "Margin is 18%" in spoken, spoken
    finally:
        page.close()
