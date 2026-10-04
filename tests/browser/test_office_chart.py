"""A chart read out of a presentation or a document is driven from the keyboard.

``maidr.read_powerpoint_charts`` and ``maidr.read_word_charts`` draw a chart
again as ``read_excel_charts`` does, and the markup tests cannot tell whether
the page a reader gets from it works. This opens the pages of two charts of
the gallery's files, which python-pptx wrote as PowerPoint saves a chart: on a
slide, Right moves along the quarters, named after the header in the chart's
data sheet, and Up moves to the other region; in a document, Right moves along
the months.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.browser.test_excel_chart import _OUTLINED, _open, _step

pytestmark = pytest.mark.browser

DOCS = Path(__file__).parents[2] / "docs"


def _page(chart, tmp_path: Path) -> Path:
    import maidr

    path = tmp_path / "chart.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(chart, file=str(path), use_cdn=False)
    maidr.close(chart)
    return path


def test_the_quarters_and_regions_of_a_slide_s_chart_are_read(browser, tmp_path):
    import maidr

    revenue, *_ = maidr.read_powerpoint_charts(DOCS / "slides.pptx")
    page = _open(browser, _page(revenue, tmp_path))
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        spoken = _step(page, "ArrowRight")
        assert "Quarter is Q1" in spoken and "120" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowUp")
        assert "Q1" in spoken and "95" in spoken and "South" in spoken, spoken
        assert not errors, errors
    finally:
        page.close()


def test_the_months_of_a_document_s_chart_are_read(browser, tmp_path):
    import maidr

    visitors, *_ = maidr.read_word_charts(DOCS / "report.docx")
    page = _open(browser, _page(visitors, tmp_path))
    try:
        spoken = _step(page, "ArrowRight")
        assert "Month is Jan" in spoken and "1200" in spoken, spoken

        spoken = _step(page, "ArrowRight")
        assert "Feb" in spoken and "1350" in spoken, spoken
    finally:
        page.close()
