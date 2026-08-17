"""A chart that cannot load its runtime has to say so (#455, #467).

``tests/core/test_offline_fallback_report.py`` asserts the message is in
the emitted script. That cannot tell whether it ever *reaches* a console:
a `ReferenceError` earlier in the script, a fallback that never fires, or
a report wired to a branch that is not the one taken would all pass it.

The failure being guarded is the worst kind this project has. The chart
renders, it looks like a chart, and nothing anywhere says why it cannot
be navigated -- and the person hitting it is on an air-gapped deployment
where the setting that works is otherwise only discoverable by reading
the source.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

#: Every host the runtime might legitimately come from. Blocked so the
#: test creates the air-gapped condition itself rather than inheriting it
#: from whatever network the runner happens to have.
_CDN = "**://*.jsdelivr.net/**"


def test_a_chart_with_no_runtime_says_so_in_the_console(browser, offline_app_url):
    """The report fires, names the failure, and names the fix."""
    page = browser.new_page()
    messages: list[str] = []
    page.on("console", lambda m: messages.append(m.text))

    page.route(_CDN, lambda route: route.abort())
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
    page.goto(offline_app_url, wait_until="networkidle")
    page.wait_for_timeout(12_000)

    assert not [e for e in errors if "reportNoRuntime" in e], (
        f"the reporter was called but not defined: {errors}"
    )

    page.close()
