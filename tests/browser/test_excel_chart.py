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


# --------------------------------------------------------------------------
# The chart types maidr draws itself
# --------------------------------------------------------------------------

#: The ``d`` of the one outline drawn: a copy of the mark it is on.
_OUTLINE_D = (
    "() => [...document.querySelectorAll('[id^=maidr-highlight]')]"
    ".map(h => h.getAttribute('d'))"
)


def _page_of(tmp_path: Path, browser, book: Path):
    """
    The page of the workbook's one chart, open and focused, and the ``d`` of
    each mark its layer's selector names, read from the saved page before
    maidr adds anything to it.
    """
    import re

    from lxml import etree
    from lxml.cssselect import CSSSelector

    import maidr
    from maidr.core.figure_manager import FigureManager

    (chart,) = _quietly(maidr.read_excel_charts, book)
    path = tmp_path / "chart.html"
    maidr.save_html(chart, file=str(path), use_cdn=False)
    (layer,) = [
        layer
        for row in FigureManager.get_maidr(chart.figure)._flatten_maidr()["subplots"]
        for cell in row
        for layer in cell["layers"]
    ]
    maidr.close(chart)
    svg = etree.fromstring(
        re.search(r"<svg.*?</svg>", path.read_text(), re.S).group(0).encode(),
        etree.XMLParser(recover=True),
    )
    for element in svg.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    selector = layer["selectors"]
    marks = (
        [e.get("d") for e in CSSSelector(selector)(svg)]
        if isinstance(selector, str)
        else []
    )
    return _open(browser, path), marks


def _quietly(read, *args):
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return read(*args)


def test_a_waterfall_outlines_the_step_it_reads(tmp_path, browser):
    from tests.excel import test_every_chart_type as t

    rows = [["Step", "Amount"], ["Start", 100], ["Sales", 50], ["Costs", -30],
            ["End", 120]]  # fmt: skip
    part = t._part(
        "waterfall",
        t._dimension("strDim", "cat", "Sales!$A$2:$A$5", [[r[0] for r in rows[1:]]]),
        t._dimension("numDim", "val", "Sales!$B$2:$B$5", [[r[1] for r in rows[1:]]]),
        layout_pr='<cx:subtotals><cx:idx val="0"/><cx:idx val="3"/></cx:subtotals>',
    )
    page, marks = _page_of(tmp_path, browser, t._excel_2016(tmp_path, part, rows))
    try:
        _step(page, "ArrowRight")
        spoken = _step(page, "ArrowRight")
        assert "Sales" in spoken and "50" in spoken and "150" in spoken, spoken
        assert page.evaluate(_OUTLINE_D) == [marks[1]]
    finally:
        page.close()


def test_a_treemap_outlines_the_node_it_reads(tmp_path, browser):
    from tests.excel import test_every_chart_type as t

    book = t._excel_2016(tmp_path, t._tree_part("treemap"), t.TREE)
    page, marks = _page_of(tmp_path, browser, book)
    try:
        spoken = _step(page, "ArrowRight")
        assert "Fruit" in spoken and "16" in spoken, spoken
        assert page.evaluate(_OUTLINE_D) == [marks[0]]

        spoken = _step(page, "ArrowDown")
        assert "Apple" in spoken and "10" in spoken, spoken
        assert page.evaluate(_OUTLINE_D) == [marks[1]]
    finally:
        page.close()


def test_a_radar_is_read_round_its_spokes_and_across_its_series(tmp_path, browser):
    from tests.excel.test_read_excel_charts import _book, _chart

    book = _book(tmp_path, _chart("radar", subtype="with_markers"))
    page, _ = _page_of(tmp_path, browser, book)
    try:
        spoken = _step(page, "ArrowRight")
        assert "Q1" in spoken and "120" in spoken and "North" in spoken, spoken
        _step(page, "ArrowRight")
        spoken = _step(page, "ArrowDown")
        assert "Q2" in spoken and "110" in spoken and "South" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1
    finally:
        page.close()


def test_a_surface_moves_up_to_the_row_drawn_above(tmp_path, browser):
    from tests.excel import test_every_chart_type as t
    from tests.excel.test_read_excel_charts import _book, _chart, _rewrite

    book = _rewrite(_book(tmp_path, _chart("line")), "xl/charts/chart1.xml", t._surface)
    page, _ = _page_of(tmp_path, browser, book)
    top = (
        "() => document.querySelector('[id^=maidr-highlight]')"
        ".getBoundingClientRect().top"
    )
    try:
        spoken = _step(page, "ArrowRight")
        assert "North" in spoken and "120" in spoken, spoken
        below = page.evaluate(top)

        spoken = _step(page, "ArrowUp")
        assert "South" in spoken and "95" in spoken, spoken
        assert page.evaluate(top) < below
    finally:
        page.close()


def test_a_stock_chart_is_read_candle_by_candle(tmp_path, browser):
    from tests.excel import test_every_chart_type as t
    from tests.excel.test_read_excel_charts import _book

    book = _book(
        tmp_path, t._stock((1, 2, 3, 4), bars=True), rows=t.PRICES, sheet="Prices"
    )
    page, _ = _page_of(tmp_path, browser, book)
    try:
        spoken = _step(page, "ArrowRight")
        assert "Mon" in spoken and "12" in spoken, spoken
        spoken = _step(page, "ArrowRight")
        assert "Tue" in spoken and "11" in spoken, spoken
        spoken = _step(page, "ArrowUp")
        assert "Tue" in spoken and "12" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1
    finally:
        page.close()
