"""A chart renders inside a Shiny module.

A module's session namespaces the chart's route as an id, which takes
letters, digits and underscores only; the route was named ``maidr-<id>``,
so ``render_maidr`` raised in every module and the output showed Shiny's
error instead of the chart. Two instances of one module must each serve
their own chart and read it out.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"


def test_each_instance_of_a_module_shows_and_reads_its_own_chart(
    browser, module_app_url
):
    page = browser.new_page(viewport={"width": 1200, "height": 1200})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(module_app_url, wait_until="networkidle")
        page.wait_for_function(
            "() => document.querySelectorAll('iframe[data-maidr-chart]').length === 2",
            timeout=60_000,
        )
        assert not page.locator(".shiny-output-error").count()

        spoken = []
        for name, first in (("sales", "Apples"), ("costs", "North")):
            frame_element = page.locator(f"#{name}-bars iframe[data-maidr-chart]")
            assert "/dynamic_route/" + name + "-maidr_bars?" in (
                frame_element.get_attribute("src") or ""
            )
            frame = frame_element.element_handle().content_frame()
            frame.locator(CHART).first.wait_for(timeout=60_000)
            frame.locator(CHART).first.focus()
            # The first key may be answered with maidr's introduction, which
            # it reads when the chart takes the focus; the next one moves.
            text = ""
            for _ in range(3):
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(800)
                text = frame.evaluate(
                    "() => (document.getElementById('maidr-text-container') || {})"
                    ".innerText || ''"
                )
                if first in text:
                    break
            spoken.append(text)
            assert first in text, text
    finally:
        page.close()
    assert not errors, errors
