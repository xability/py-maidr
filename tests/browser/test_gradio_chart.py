"""A chart in a Gradio app is driven from the keyboard.

``maidr.widget.gradio`` places a chart in an iframe because ``gr.HTML`` does
not run the scripts of its value. These open a real Gradio app and check that
the frame works for a reader: the chart built with the app and the one an
event handler fills are both reached, both move with the arrow keys, the
frame grows as the braille panel opens, and the second chart keeps working
after the handler replaces it.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"

#: How long the inlined bundle may take to parse in each frame.
_LOAD_ROUNDS = 20


def _frame(page, title: str):
    """The chart frame named ``title``, once its chart is up."""
    for _ in range(_LOAD_ROUNDS):
        for element in page.query_selector_all("iframe[data-maidr-chart]"):
            if element.get_attribute("title") == title:
                frame = element.content_frame()
                if frame is not None and frame.locator(CHART).count():
                    return frame
        page.wait_for_timeout(1_000)
    titles = [e.get_attribute("title") for e in page.query_selector_all("iframe")]
    raise AssertionError(f"no working chart frame named {title!r}; found {titles}")


def _say(page, frame, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return frame.evaluate("document.body.innerText").strip().split("\n")[-1]


@pytest.fixture
def gradio_page(browser, gradio_app_url):
    page = browser.new_page()
    page.goto(gradio_app_url, wait_until="networkidle")
    yield page
    page.close()


def test_a_chart_built_with_the_app_is_read(gradio_page):
    page = gradio_page
    frame = _frame(page, "Sales by region, accessible chart")
    element = page.locator("iframe[title='Sales by region, accessible chart']")
    frame.locator(CHART).first.focus()

    assert "north" in _say(page, frame, "ArrowRight")
    spoken = _say(page, frame, "ArrowRight")
    assert "south" in spoken and "7" in spoken, spoken

    # The frame grows with the braille panel rather than cropping it.
    closed = element.bounding_box()["height"]
    assert _say(page, frame, "b") == "Braille is on"
    page.wait_for_timeout(500)
    assert element.bounding_box()["height"] > closed + 50


def test_a_chart_a_handler_replaces_is_read_again(gradio_page):
    page = gradio_page
    frame = _frame(page, "3 bars, accessible chart")
    frame.locator(CHART).first.focus()
    assert "b0" in _say(page, frame, "ArrowRight")

    # The slider's number box: typing a value fires the change handler.
    box = page.locator("input[type=number]").first
    box.fill("5")
    box.press("Enter")

    frame = _frame(page, "5 bars, accessible chart")
    frame.locator(CHART).first.focus()
    for _ in range(5):
        spoken = _say(page, frame, "ArrowRight")
    assert "b4" in spoken and "5" in spoken, spoken
