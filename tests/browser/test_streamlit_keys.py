"""The iframe is what lets maidr and Streamlit both have ``r`` (#460).

``maidr/widget/streamlit.py`` embeds every chart in an iframe on the
grounds that Streamlit claims keys at the document level and maidr needs
the same ones. That is the reason the module gives for a decision with
real costs -- a bundle per frame offline, no shared state -- so it is
worth holding to evidence rather than to a comment.

Both halves have to hold for the argument to stand: Streamlit really
takes ``r``, and the frame really keeps it from doing so. A failure here
is not necessarily a bug in maidr; it may mean Streamlit changed and the
frame is no longer buying what it costs, which is worth knowing either
way.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"


def _runcount(page) -> int | None:
    found = re.search(r"RUNCOUNT=(\d+)", page.evaluate("document.body.innerText"))
    return int(found.group(1)) if found else None


def _chart_frame(page):
    for frame in page.frames[1:]:
        try:
            if frame.locator(CHART).count():
                return frame
        except Exception:
            pass
    return None


@pytest.fixture
def streamlit_page(browser, streamlit_keys_app_url):
    pg = browser.new_page()
    pg.goto(streamlit_keys_app_url, wait_until="networkidle")
    # The srcdoc carries the inlined bundle; give it room to parse.
    for _ in range(20):
        pg.wait_for_timeout(3000)
        if _chart_frame(pg) is not None:
            break
    yield pg
    pg.close()


def test_streamlit_still_claims_r_at_the_document_level(streamlit_page):
    """Half the argument: without this, the frame costs and buys nothing."""
    page = streamlit_page
    before = _runcount(page)
    assert before is not None, "the app did not render its run counter"

    page.keyboard.press("r")
    page.wait_for_timeout(3000)

    assert _runcount(page) != before, (
        "pressing 'r' no longer reruns the Streamlit script. That is not a "
        "maidr bug -- it may mean the document-level collision this "
        "integration's iframe exists to avoid is gone, and the iframe's "
        "cost (a bundle per frame offline, no shared state) now buys less "
        "than it did. See #460."
    )


def test_the_frame_gives_r_to_the_chart_instead(streamlit_page):
    """The other half: maidr gets the key, and the script does not rerun."""
    page = streamlit_page
    frame = _chart_frame(page)
    assert frame is not None, "no chart frame on the page"

    frame.locator(CHART).first.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)
    page.keyboard.press("t")
    page.wait_for_timeout(600)

    before = _runcount(page)
    page.keyboard.press("r")
    page.wait_for_timeout(1500)

    spoken = frame.evaluate("document.body.innerText").strip().split("\n")[-1]
    assert "eview" in spoken, (
        f"the chart did not act on 'r'; it said {spoken!r}. 'No rerun' below "
        "would then prove nothing -- a dead frame swallows keys too."
    )
    assert _runcount(page) == before, (
        "the Streamlit script reran while the reader was inside the chart"
    )
