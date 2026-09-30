"""A rerun leaves an unchanged chart, and the reader in it, alone (#460).

Streamlit reruns the whole script on every widget interaction and hands the
chart's frame whatever ``render_maidr`` returned. A different string makes
the browser reload the frame, and every render used to differ -- fresh ids,
a timestamp -- so a rerun that reached the app while a reader was inside
the chart dropped them: focus fell to the frame's ``<body>``, the braille
panel closed, and the next arrow key did nothing, with nothing announced.

The rerun here is driven by clicking a checkbox from script, which leaves
focus where it was. That stands in for the reruns that reach an app while
the reader stays in the chart -- a ``st.fragment(run_every=...)`` around
it, an auto-refresh calling ``st.rerun()`` -- both of which were measured
by hand to behave the same, and is quicker and steadier than waiting on a
timer. A reader who *leaves* the chart to use the checkbox themselves is a
different case, and not one this can fix: maidr.js releases a chart's
state whenever focus leaves it, rerun or not (xability/maidr#1338).

Run once with matplotlib and once with Plotly, whose schema ids travel as
raw JSON in a script rather than in the SVG, and are found another way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"

#: Set on the frame's window. A reload gives the frame a new window, which
#: does not have it -- the one unambiguous sign the frame was rebuilt.
_MARK = "() => { window.__maidrRerunMark = 1; }"
_MARKED = "() => window.__maidrRerunMark === 1"


def _runcount(page) -> int | None:
    found = re.search(r"RUNCOUNT=(\d+)", page.evaluate("document.body.innerText"))
    return int(found.group(1)) if found else None


def _chart_frame(page):
    """The frame holding a chart whose runtime is up, or ``None``."""
    for frame in page.frames[1:]:
        try:
            if frame.locator(CHART).count() and frame.evaluate(
                "() => window.maidrLive !== undefined"
            ):
                return frame
        except Exception:
            pass
    return None


def _wait_for_chart(page):
    # The srcdoc carries the inlined bundle; give it room to parse.
    for _ in range(30):
        frame = _chart_frame(page)
        if frame is not None:
            return frame
        page.wait_for_timeout(1000)
    pytest.fail("no chart frame came up")


def _step(page, frame, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(600)
    return frame.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _rerun_by_clicking(page, label: str) -> None:
    """Toggle a checkbox without moving focus, and wait for the rerun."""
    before = _runcount(page)
    page.get_by_role("checkbox", name=label).evaluate("box => box.click()")
    for _ in range(30):
        page.wait_for_timeout(500)
        if _runcount(page) != before:
            break
    else:
        pytest.fail(f"clicking {label!r} did not rerun the script")
    # The rerun's deltas land after the counter's; let the frame's arrive.
    page.wait_for_timeout(3000)


@pytest.fixture(params=["matplotlib", "plotly"])
def streamlit_page(request, browser, streamlit_rerun_app_url):
    """The app's page, drawing its chart with the library under test."""
    pg = browser.new_page()
    if request.param == "plotly":
        # plotly.js is linked from its CDN; hand the frame the copy the
        # installed package ships, as the Plotly browser tests do, so
        # nothing here needs a network.
        plotly = pytest.importorskip("plotly")
        bundled = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
        pg.route(
            re.compile(r"^https://cdn\.plot\.ly/"),
            lambda route: route.fulfill(
                path=str(bundled), content_type="application/javascript"
            ),
        )
    pg.goto(f"{streamlit_rerun_app_url}/?lib={request.param}", wait_until="networkidle")
    yield pg
    pg.close()


def test_an_unrelated_rerun_leaves_the_reader_where_they_were(streamlit_page):
    page = streamlit_page
    frame = _wait_for_chart(page)
    frame.locator(CHART).first.focus()
    page.wait_for_timeout(600)
    _step(page, frame, "ArrowRight")
    spoken = _step(page, frame, "ArrowRight")
    assert "b" in spoken, f"the reader never reached the second bar: {spoken!r}"
    frame.evaluate(_MARK)

    _rerun_by_clicking(page, "Unrelated")

    assert frame.evaluate(_MARKED), (
        "the rerun reloaded the chart's frame although the chart did not "
        "change: render_maidr handed Streamlit a different string for the "
        "same chart, so the reader was dropped out of it (#460)"
    )
    spoken = _step(page, frame, "ArrowRight")
    assert "c" in spoken, (
        f"after the rerun the next arrow key said {spoken!r}, not the third "
        "bar: the frame survived but the reader's place in it did not"
    )


def test_a_changed_chart_still_reaches_the_reader(streamlit_page):
    """The other half: keeping the frame must never mean keeping a stale chart."""
    page = streamlit_page
    frame = _wait_for_chart(page)
    frame.evaluate(_MARK)

    _rerun_by_clicking(page, "More data")

    frame = _wait_for_chart(page)
    assert not frame.evaluate(_MARKED), (
        "the chart changed but its frame was kept, so the reader is still "
        "on the old one"
    )
    frame.locator(CHART).first.focus()
    page.wait_for_timeout(600)
    spoken = ""
    for _ in range(4):
        spoken = _step(page, frame, "ArrowRight")
    assert "d" in spoken, f"the fourth bar was not announced: {spoken!r}"
