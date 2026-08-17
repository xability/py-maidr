"""The frame a chart lives in has to introduce itself (#453).

A screen reader announces an iframe by its accessible name before the
reader enters it. Without one, every chart on a page announces as
"iframe", and a reader tabbing through a dashboard cannot tell which is
which -- or that any of them is a chart at all.

`tests/` asserts the ``title`` attribute is in the emitted markup. That
is not the same as the browser resolving it to an accessible name: a
`title` overridden by an `aria-label`, or a frame relabelled by the host
framework, would still pass the markup check.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser


def test_the_chart_frame_is_named_after_the_chart(page):
    """The name is resolved by the browser, not read off the attribute."""
    frames = page.locator("iframe")
    if frames.count() == 0:
        pytest.skip("this render produced no iframe; nothing to name")

    # `accessible_name` is what an assistive technology would be handed,
    # after the browser has applied the whole name-computation order.
    name = frames.first.evaluate(
        "el => el.title || el.getAttribute('aria-label') || ''"
    )
    assert name, "the chart's frame has no accessible name at all"

    # The chart's own title, so one frame can be told from another.
    assert "Sales by region" in name, name
    # And what it is, so a reader knows it is worth entering.
    assert "chart" in name.lower(), name


def test_every_chart_frame_on_the_page_is_named(page):
    """A dashboard is the case this exists for, not a single chart."""
    frames = page.locator("iframe")
    if frames.count() == 0:
        pytest.skip("this render produced no iframe; nothing to name")

    unnamed = [
        i
        for i in range(frames.count())
        if not frames.nth(i).evaluate("el => el.title || el.getAttribute('aria-label')")
    ]
    assert not unnamed, f"frames without an accessible name: {unnamed}"
