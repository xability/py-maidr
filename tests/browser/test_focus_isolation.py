"""With two charts on a page, the reader comes back to their own (#484).

What this establishes is the behaviour: both charts are replaced at once,
and focus returns to the one the reader was in rather than to the other.

What it does **not** establish, despite two attempts, is the container-id
scoping in ``restore`` on its own. Deleting ``held.id !== container.id``
leaves both versions of this test green:

* Pairing a re-rendering chart with a static one fails to reach the check
  at all -- the held element is still connected, so ``restore`` bails a
  line earlier.
* Re-rendering both does destroy the held element, but the two observers
  fire in an order that happens to restore the right chart first, after
  which ``adrift()`` is false and the second call returns anyway.

That ordering is incidental rather than guaranteed, so the id check is
still doing real work; it is simply not isolable from outside. Recorded
here so the next reader does not mistake a green run for proof of that
line, and does not delete it on the strength of one.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"


def _frames_with_charts(page):
    out = []
    for frame in page.frames[1:]:
        try:
            if frame.locator(CHART).count():
                out.append(frame)
        except Exception:
            pass
    return out


def _focused_frame_id(page) -> str:
    return page.evaluate(
        "document.activeElement && document.activeElement.tagName === 'IFRAME'"
        " ? (document.activeElement.closest('.shiny-html-output') || {}).id || ''"
        " : ''"
    )


@pytest.fixture
def two_chart_page(browser, two_charts_app_url):
    pg = browser.new_page()
    pg.goto(two_charts_app_url, wait_until="networkidle")
    for _ in range(20):
        pg.wait_for_timeout(3000)
        if len(_frames_with_charts(pg)) >= 2:
            break
    yield pg
    pg.close()


def test_both_charts_are_present_and_independent(two_chart_page):
    """The premise: two charts, each answering for itself."""
    frames = _frames_with_charts(two_chart_page)
    assert len(frames) == 2, f"expected two charts, found {len(frames)}"


def test_focus_returns_to_the_chart_it_left_not_the_other_one(two_chart_page):
    """Both charts are replaced; the reader belongs to exactly one of them."""
    page = two_chart_page
    assert len(_frames_with_charts(page)) == 2

    page.locator("#second iframe").focus()
    page.wait_for_timeout(500)
    assert _focused_frame_id(page) == "second", "setup failed"

    # Both outputs depend on this input, so both containers mutate and
    # the element holding focus is genuinely destroyed.
    page.evaluate(
        """() => {
             const el = document.querySelector('#n');
             const s = window.jQuery && jQuery(el).data('ionRangeSlider');
             if (s) { s.update({from: 5}); jQuery(el).trigger('change'); }
           }"""
    )
    page.wait_for_timeout(15000)

    after = _focused_frame_id(page)
    assert after == "second", (
        f"focus came back to {after!r} rather than the chart the reader was "
        "in; a restore that ignores which container it belongs to sends the "
        "reader to whichever one mutated last"
    )
