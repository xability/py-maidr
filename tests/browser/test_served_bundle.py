"""An offline Shiny chart loads its runtime from the app, once (#457).

``tests/widget/test_shiny.py`` asserts that the chart document names the
served bundle and that the name resolves, on paper, to where Shiny mounts
it. Three things only a browser can say: that the frame really loads
``maidr.js`` from there and the chart then answers the keyboard with no
network at all; that the URL survives an app mounted under a prefix; and
that the browser fetches the ~1.9 MB bundle once for a page of charts and
its re-renders, where it used to fetch it inside every chart document on
every render.

The app mounts two ``use_cdn=False`` charts two levels below the server
root, the way a hosted deployment serves an app under a prefix it never
sees.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"

#: A document that still carried the bundle would be ~2.2 MB; one that
#: names it is ~20 KB for these charts. The bound is between, well clear
#: of both.
_DOCUMENT_LIMIT = 256 * 1024

#: The bundle itself is ~1.9 MB; nothing else on the page comes close.
_BUNDLE_MIN = 1_000_000


def _chart_frames(page) -> list:
    out = []
    for frame in page.frames[1:]:
        try:
            if frame.locator(CHART).count():
                out.append(frame)
        except Exception:
            pass
    return out


def _wait_for_two_charts(page) -> list:
    for _ in range(20):
        frames = _chart_frames(page)
        if len(frames) >= 2:
            return frames
        page.wait_for_timeout(1500)
    return _chart_frames(page)


def _rerender(page, bars: int) -> None:
    """Move the slider both charts depend on, through the widget's own API."""
    page.evaluate(
        """(v) => {
             const el = document.querySelector('#n');
             const s = window.jQuery && jQuery(el).data('ionRangeSlider');
             if (s) { s.update({from: v}); jQuery(el).trigger('change'); }
           }""",
        bars,
    )
    page.wait_for_timeout(9000)


def _is_bundle(url: str) -> bool:
    return "/lib/maidr-bundle-" in url and url.endswith("/maidr.js")


def test_an_offline_chart_loads_its_runtime_from_the_app(
    browser, served_bundle_app_url
):
    """No network past the app, and the chart still answers the keyboard.

    Every request to another host is refused, so the only ``maidr.js``
    this page can run is the copy the app serves -- found through a URL
    that has to climb from the chart's session route back to the app's
    prefix, not the server's root.
    """
    page = browser.new_page()
    origin = served_bundle_app_url.split("/deep/")[0]
    elsewhere: list[str] = []
    bundle: list[tuple[str, int]] = []

    def local_only(route):
        if route.request.url.startswith(origin):
            route.continue_()
        else:
            elsewhere.append(route.request.url)
            route.abort()

    page.route("**/*", local_only)
    page.on(
        "response",
        lambda r: bundle.append((r.url, r.status)) if _is_bundle(r.url) else None,
    )
    page.goto(served_bundle_app_url, wait_until="networkidle")
    frames = _wait_for_two_charts(page)
    assert len(frames) == 2, f"expected two charts, found {len(frames)}"

    # Loaded from under the prefix: the relative URL climbed out of the
    # session route and stopped at the app, not at the server root.
    assert bundle, "no frame asked the app for maidr.js"
    assert {status for _, status in bundle} == {200}, bundle
    for url, _ in bundle:
        assert url.startswith(f"{served_bundle_app_url}lib/maidr-bundle-"), url

    # The frame's document no longer carries the runtime.
    frame = frames[0]
    document = page.request.get(frame.url).text()
    assert "maidr=" in document, "the served document carries no MAIDR schema"
    assert len(document) < _DOCUMENT_LIMIT, (
        f"{len(document)} bytes; the chart document still carries the bundle"
    )

    # And the runtime it loaded instead is live.
    frame.locator(CHART).first.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(700)
    page.keyboard.press("t")
    page.wait_for_timeout(400)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(700)
    spoken = frame.evaluate("document.body.innerText").strip().split("\n")[-1]
    assert "a" in spoken, f"the chart announced {spoken!r}"

    page.close()


def test_the_bundle_crosses_the_wire_once_for_two_charts_and_a_rerender(
    browser, served_bundle_app_url
):
    """Two charts, one re-render of both: one transfer of the bundle.

    Counted from Chromium's own network log, in bytes received, so a
    response the browser answered from its cache -- or revalidated with a
    body-less 304 -- counts for nothing, and one that carried the bundle
    counts for what it weighed. Before #457 this page moved the bundle
    four times, once inside each chart document per render.

    No request interception here: Playwright turns the browser's cache
    off while any route is registered, which would count the very
    re-fetches this is checking do not happen.
    """
    context = browser.new_context()
    page = context.new_page()
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")

    urls: dict[str, str] = {}
    received: dict[str, int] = {}
    cdp.on(
        "Network.responseReceived",
        lambda e: urls.__setitem__(e["requestId"], e["response"]["url"]),
    )
    cdp.on(
        "Network.loadingFinished",
        lambda e: received.__setitem__(e["requestId"], e["encodedDataLength"]),
    )

    def transfers() -> list[tuple[str, int]]:
        return [(urls[rid], size) for rid, size in received.items() if rid in urls]

    page.goto(served_bundle_app_url, wait_until="networkidle")
    frames = _wait_for_two_charts(page)
    assert len(frames) == 2, f"expected two charts, found {len(frames)}"
    first_urls = sorted(frame.url for frame in frames)

    _rerender(page, 5)
    frames = _wait_for_two_charts(page)
    assert len(frames) == 2
    assert sorted(frame.url for frame in frames) != first_urls, (
        "the charts were not re-rendered, so nothing below measures a re-render"
    )

    documents = [size for url, size in transfers() if "/dynamic_route/" in url]
    bundles = [size for url, size in transfers() if _is_bundle(url)]

    assert len(documents) == 4, f"expected four chart documents: {documents}"
    assert max(documents) < _DOCUMENT_LIMIT, documents
    assert bundles, "the frames never asked for maidr.js"
    assert len([size for size in bundles if size > _BUNDLE_MIN]) == 1, (
        f"the bundle was transferred more than once: {bundles}"
    )

    context.close()
