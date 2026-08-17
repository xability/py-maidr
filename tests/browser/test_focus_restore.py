"""A reactive re-render must not eject the reader from the chart (#484).

Four cases, and the two that matter pull in opposite directions: A is the
bug, D is the failure a careless fix introduces. A test suite that only
covered A would pass on a version that grabs focus from whatever the
reader was doing.

These need a browser. The behaviour is a browser behaviour -- an element
losing focus because it left the document -- and nothing about it is
visible in the emitted markup, which is all the rest of the suite can see.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"


def _active(page) -> str:
    """The focused element, as tag plus id, in the top document."""
    return page.evaluate(
        "document.activeElement.tagName"
        " + (document.activeElement.id ? '#' + document.activeElement.id : '')"
    )


def _enter_chart(page) -> None:
    """Focus the chart and activate it, the way a reader would."""
    frame = page.frames[1] if len(page.frames) > 1 else page
    frame.locator(CHART).first.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(700)


def _rerender(page, bars: int) -> None:
    """Change the slider without touching focus.

    Driven through the widget's own API rather than by clicking it: a
    click would move focus, which is the very thing under test.
    """
    page.evaluate(
        """(v) => {
             const el = document.querySelector('#n');
             const s = window.jQuery && jQuery(el).data('ionRangeSlider');
             if (s) { s.update({from: v}); jQuery(el).trigger('change'); }
           }""",
        bars,
    )
    page.wait_for_timeout(9000)


def test_the_chart_is_reachable_and_answers_the_keyboard(page):
    """The premise the rest of the file rests on.

    If this fails, the others are meaningless rather than merely failing:
    a chart nobody can focus cannot lose focus.
    """
    frame = page.frames[1] if len(page.frames) > 1 else page
    assert frame.locator(CHART).count() == 1

    _enter_chart(page)
    page.keyboard.press("t")
    page.wait_for_timeout(400)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(700)

    spoken = frame.evaluate("document.body.innerText").strip().split("\n")[-1]
    assert "a" in spoken, f"the chart announced {spoken!r}"


def test_focus_returns_to_the_chart_after_a_rerender(page):
    """The bug: a reader mid-chart was dropped to the top of the document."""
    _enter_chart(page)
    before = _active(page)
    assert before.startswith(("IFRAME", "DIV")), before

    _rerender(page, 5)

    after = _active(page)
    assert after.startswith(("IFRAME", "DIV")), (
        f"focus was left on {after} after the re-render; the reader would "
        "have to tab back through every preceding control"
    )


def test_a_deliberate_move_away_is_not_undone(page):
    """The opposite failure: never take focus from what the reader chose.

    Worse than the bug it fixes -- being pulled out of a control mid-task
    is more disruptive than being dropped from a chart.
    """
    _enter_chart(page)
    page.locator("#note").focus()
    page.wait_for_timeout(300)

    _rerender(page, 4)

    assert _active(page) == "INPUT#note"
    page.keyboard.type("hello")
    page.wait_for_timeout(400)
    assert page.locator("#note").input_value() == "hello", (
        "keystrokes went somewhere other than the focused input"
    )


def test_a_chart_nobody_focused_does_not_take_focus(page):
    """Page load is a re-render too, and must not steal focus."""
    assert _active(page) == "BODY"

    _rerender(page, 5)

    assert _active(page) == "BODY", (
        "the chart took focus from a reader who had not gone near it"
    )
