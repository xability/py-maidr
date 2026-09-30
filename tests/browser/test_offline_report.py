"""``"auto"`` with no CDN: the app's copy, or a report that says why not.

Under Shiny the offline fallback of ``use_cdn="auto"`` is the bundled copy
the app serves (#457). Before that it named a relative ``lib/`` path that
nothing answered, so an air-gapped Shiny app on the default setting got a
chart with no runtime -- which is why the report below exists (#455, #467).

``tests/core/test_offline_fallback_report.py`` asserts the message is in
the emitted script. That cannot tell whether it ever *reaches* a console:
a `ReferenceError` earlier in the script, a fallback that never fires, or
a report wired to a branch that is not the one taken would all pass it.

The failure being guarded is the worst kind this project has. The chart
renders, it looks like a chart, and nothing anywhere says why it cannot
be navigated. Under Shiny it now takes the app's own copy failing as well
as the CDN, so the tests that need it refuse both.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"

#: Every host the runtime might legitimately come from. Blocked so the
#: test creates the air-gapped condition itself rather than inheriting it
#: from whatever network the runner happens to have.
_CDN = "**://*.jsdelivr.net/**"

#: The copy the app serves, refused to leave the chart no source at all.
_SERVED = "**/lib/maidr-bundle-*/**"


def _chart_frame(page):
    for frame in page.frames[1:]:
        if frame.locator(CHART).count():
            return frame
    return None


def test_an_unreachable_cdn_falls_back_to_the_copy_the_app_serves(
    browser, offline_app_url
):
    """The air-gapped app on the default setting now gets a working chart.

    The CDN is refused; the fallback loads the app's copy, the chart
    answers the keyboard, and nothing reports a missing runtime.
    """
    page = browser.new_page()
    messages: list[str] = []
    served: list[int] = []
    page.on("console", lambda m: messages.append(m.text))
    page.on(
        "response",
        lambda r: served.append(r.status) if "/lib/maidr-bundle-" in r.url else None,
    )

    page.route(_CDN, lambda route: route.abort())
    page.goto(offline_app_url, wait_until="networkidle")
    page.wait_for_timeout(12_000)

    assert served == [200], f"the fallback did not load the app's copy: {served}"
    assert not [m for m in messages if "its runtime did not" in m], messages[-5:]

    frame = _chart_frame(page)
    assert frame is not None, "no chart frame found on the page"
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


def test_a_chart_with_no_runtime_says_so_in_the_console(browser, offline_app_url):
    """The report fires, names the failure, and names the fix."""
    page = browser.new_page()
    messages: list[str] = []
    page.on("console", lambda m: messages.append(m.text))

    page.route(_CDN, lambda route: route.abort())
    page.route(_SERVED, lambda route: route.abort())
    page.goto(offline_app_url, wait_until="networkidle")
    page.wait_for_timeout(12_000)

    reports = [m for m in messages if "its runtime did not" in m]
    assert reports, (
        "no runtime report reached the console; a reader would get a chart "
        f"that silently cannot be navigated. Console was: {messages[-5:]}"
    )

    report = reports[0]
    # Naming the failure is not enough -- `use_cdn=False` is not guessable
    # from a blank chart, and it is the only thing that works offline.
    assert "use_cdn=False" in report, report

    page.close()


def test_the_report_is_not_a_reference_error(browser, offline_app_url):
    """The reporter has to be defined where it is called.

    An earlier version of this fix emitted the call sites without the
    definition on one path. That throws `ReferenceError` instead of
    reporting, which is worse than the silence it replaced -- and it is
    invisible to a test that only greps the emitted script for a name.
    """
    page = browser.new_page()
    errors: list[str] = []
    # Both channels: an uncaught throw arrives as `pageerror`, but one
    # raised inside the frame's own script surfaces only on the console.
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    page.route(_CDN, lambda route: route.abort())
    page.route(_SERVED, lambda route: route.abort())
    page.goto(offline_app_url, wait_until="networkidle")
    page.wait_for_timeout(12_000)

    assert not [e for e in errors if "reportNoRuntime" in e], (
        f"the reporter was called but not defined: {errors}"
    )

    page.close()
