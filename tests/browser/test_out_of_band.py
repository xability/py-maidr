"""The chart leaves the websocket (#534).

``tests/widget/test_shiny.py`` asserts that the payload names a session
route and that the route serves the document. It cannot tell whether a
browser actually loads the chart from there, nor what Shiny then sends
over the wire on a flush, which is the whole point: the document had to
leave the channel every input and output shares. Both are observable only
here, from the websocket a real page opens.

The app inlines the bundle (``use_cdn=False``), which is the heaviest
case -- every flush used to push ~2 MB through the socket.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"

#: A flush that carried the chart would be at least the bundle's ~1.5 MB;
#: one that carries only the frame is under 10 KB. The bound is between,
#: well clear of both.
_FRAME_LIMIT = 64 * 1024


def _chart_frame(page):
    for frame in page.frames[1:]:
        if frame.locator(CHART).count():
            return frame
    return None


def _rerender(page, bars: int) -> None:
    """Change the slider through the widget's own API, as the focus tests do."""
    page.evaluate(
        """(v) => {
             const el = document.querySelector('#n');
             const s = window.jQuery && jQuery(el).data('ionRangeSlider');
             if (s) { s.update({from: v}); jQuery(el).trigger('change'); }
           }""",
        bars,
    )
    page.wait_for_timeout(9000)


def test_the_chart_loads_from_a_session_route_and_the_flush_stays_small(
    browser, focus_app_url
):
    """The document comes from ``dynamic_route``; the socket carries a reference.

    Frames are recorded from before navigation, since the socket opens
    with the page. Sizes are taken over everything Shiny sends after the
    re-render is triggered, so a payload that smuggled the chart back in
    on any flush would show up whichever message it rode.
    """
    page = browser.new_page()
    received: list[int] = []

    def on_socket(ws):
        ws.on("framereceived", lambda payload: received.append(len(payload)))

    page.on("websocket", on_socket)
    page.goto(focus_app_url, wait_until="networkidle")
    page.wait_for_timeout(12_000)

    frame = _chart_frame(page)
    assert frame is not None, "no chart frame found on the page"
    assert "/dynamic_route/maidr-bars?" in frame.url, frame.url
    first_url = frame.url

    # The document at that URL is the whole chart, bundle included -- the
    # weight that used to ride the socket.
    served = page.request.get(frame.url)
    assert served.ok
    body = served.text()
    assert "maidr=" in body, "the served document carries no MAIDR schema"
    assert len(body) > 1_000_000, f"{len(body)} bytes; the bundle is not inlined"

    before = len(received)
    _rerender(page, 5)

    # The re-render happened: a new version at the same route, and the
    # served document is the new chart. Established before the socket is
    # measured, so a slider that silently failed to move cannot pass the
    # size check on an unrelated small message.
    frame = _chart_frame(page)
    assert frame is not None
    assert frame.url != first_url, "the frame still points at the first render"
    assert frame.url.split("&v=")[0] == first_url.split("&v=")[0], frame.url
    assert frame.locator(CHART).count() == 1
    assert (
        "&quot;e&quot;" in page.request.get(frame.url).text()
    ), "the served document is not the five-bar chart"

    after_flush = received[before:]
    assert after_flush, "the re-render sent nothing over the socket"
    assert max(after_flush) < _FRAME_LIMIT, (
        f"a websocket frame of {max(after_flush)} bytes followed the flush; "
        "the chart is riding the socket again"
    )

    page.close()
