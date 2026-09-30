"""The chart leaves the websocket (#534).

``tests/widget/test_shiny.py`` asserts that the payload names a session
route and that the route serves the document. It cannot tell whether a
browser actually loads the chart from there, nor what Shiny then sends
over the wire on a flush, which is the whole point: the document had to
leave the channel every input and output shares. Both are observable only
here, from the websocket a real page opens.

The app uses the bundled copy (``use_cdn=False``), which was the heaviest
case -- every flush used to push ~2 MB through the socket, when the
bundle was inlined into the chart. Since #457 the document names the copy
the app serves instead; ``test_served_bundle.py`` covers that.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"

#: A flush that carries only the frame is under 10 KB. One that carried the
#: document was ~2 MB while the bundle was inlined into it, but is only
#: ~30 KB for this chart now that it is not (#457) -- under this bound, so
#: the size alone no longer tells the two apart, and the test also looks
#: for the ``srcdoc`` a document on the socket would have to ride in.
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
    received: list[str | bytes] = []

    def on_socket(ws):
        ws.on("framereceived", lambda payload: received.append(payload))

    page.on("websocket", on_socket)
    page.goto(focus_app_url, wait_until="networkidle")
    page.wait_for_timeout(12_000)

    frame = _chart_frame(page)
    assert frame is not None, "no chart frame found on the page"
    assert "/dynamic_route/maidr-bars?" in frame.url, frame.url
    first_url = frame.url

    # The document at that URL is the whole chart -- the weight that used
    # to ride the socket.
    served = page.request.get(frame.url)
    assert served.ok
    body = served.text()
    assert "maidr=" in body, "the served document carries no MAIDR schema"

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
    largest = max(len(payload) for payload in after_flush)
    assert largest < _FRAME_LIMIT, (
        f"a websocket frame of {largest} bytes followed the flush; "
        "the chart is riding the socket again"
    )
    assert not [p for p in after_flush if "srcdoc" in str(p)], (
        "a websocket frame after the flush carries a srcdoc; the chart "
        "document is riding the socket again"
    )

    page.close()
