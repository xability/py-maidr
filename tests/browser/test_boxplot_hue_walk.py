"""A seaborn ``hue`` box plot is walked box by box, as it is drawn.

seaborn draws a ``hue`` level by level, and the boxes were read in that order:
Right moved the outline from a category's first box to the next category's
first box, skipping the box drawn beside it, and jumped back across the chart
halfway. These drive the shipped runtime over a saved page and hold every
step to the box drawn next, in screen coordinates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000
_TEXT = "#maidr-text-container"

#: Each category's levels with their medians apart.
_CATEGORIES = ["a", "b", "c"]
_LEVELS = ["p", "q"]

_CENTRE = """(element) => {
  const rect = element.getBoundingClientRect();
  return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
}"""


def _save(tmp_path: Path, horizontal: bool) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    import maidr

    sns = pytest.importorskip("seaborn")
    rows = [
        (category, level, 20 * c + 10 * g + step)
        for c, category in enumerate(_CATEGORIES)
        for g, level in enumerate(_LEVELS)
        for step in range(-2, 3)
    ]
    data = pd.DataFrame(rows, columns=["cat", "grp", "val"])
    fig, ax = plt.subplots(figsize=(8, 5))
    path = tmp_path / f"hue_boxes_{'h' if horizontal else 'v'}.html"
    try:
        if horizontal:
            sns.boxplot(data, y="cat", x="val", hue="grp", ax=ax)
        else:
            sns.boxplot(data, x="cat", y="val", hue="grp", ax=ax)
        maidr.save_html(fig, file=str(path), use_cdn=False)
    finally:
        plt.close("all")
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(400)
    return page.locator(_TEXT).inner_text()


def _outline(page) -> dict:
    highlighted = page.locator("svg [id^=maidr-highlight]")
    assert highlighted.count() == 1
    return highlighted.evaluate(_CENTRE)


@pytest.mark.parametrize("horizontal", [False, True], ids=["vertical", "horizontal"])
def test_each_step_reaches_the_box_drawn_next(browser, tmp_path, horizontal):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    # Across the boxes: Right on a vertical chart, Up on one on its side,
    # which is walked from the bottom. The other arrow moves along a box.
    across, along = ("ArrowUp", "ArrowRight")
    if not horizontal:
        across, along = along, across
    names = [f"{category}, {level}" for category in _CATEGORIES for level in _LEVELS]
    if horizontal:
        # seaborn draws the first category at the top, its first level first.
        names.reverse()
    try:
        page.goto(_save(tmp_path, horizontal).as_uri(), wait_until="load")
        page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
        page.click("svg[maidr]", force=True)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1_500)

        for _ in range(4):
            spoken = _step(page, along)
            if "50%" in spoken:
                break
        places = []
        for index, name in enumerate(names):
            if index:
                spoken = _step(page, across)
            assert f"is {name}, 50%" in spoken, (name, spoken)
            places.append(_outline(page)["y" if horizontal else "x"])

        # Rightwards, or up the page, at every step.
        steps = [after - before for before, after in zip(places, places[1:])]
        if horizontal:
            assert all(step < 0 for step in steps), places
        else:
            assert all(step > 0 for step in steps), places
        assert not errors, errors
    finally:
        page.close()
