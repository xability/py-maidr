"""A rug is read by the core's rug trace, and outlines the tick it announces.

Emitted as ``rug`` rather than ``point`` since xability/maidr#1132: read as a
scatter, the pitch axis was the constant one across the ticks, so every tick
played the same note. The rug trace walks the observations from the lowest
position up, whatever order they were drawn in, and pairs each with its own
tick -- which is what this drives the shipped bundle to check, since a
selector that paired the walk with the draw order would outline the wrong
tick while announcing the right number.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000
_TEXT = "#maidr-text-container"

#: The outline the core draws for the current tick: a visible clone of the
#: tick's ``<path>``, whose first point says which tick it copies.
_HIGHLIGHTED = """() => [...document.querySelectorAll("svg [data-maidr-owned]")]
  .filter((e) => getComputedStyle(e).visibility !== "hidden")
  .map((e) => e.getAttribute("d").trim().split(/\\s+/).slice(1, 3).map(Number))"""

#: Drawn out of order on purpose, so the walk and the draw order differ.
_VALUES = [2.2, 1.2, 3.0, 9.0]


def _save(tmp_path: Path, name: str, draw) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    import maidr

    frame = pd.DataFrame({"v": _VALUES, "g": ["a", "b", "a", "b"]})
    fig, ax = plt.subplots()
    draw(frame, ax)
    path = tmp_path / f"{name}.html"
    try:
        maidr.save_html(fig, file=str(path), use_cdn=False)
    finally:
        plt.close("all")
    return path


def _walk(browser, chart: Path, steps: int) -> list[tuple[str, list]]:
    page = browser.new_page()
    try:
        page.goto(chart.as_uri(), wait_until="load")
        page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
        page.click("svg[maidr]", force=True)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1_500)
        seen = []
        for _ in range(steps):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(400)
            text = page.evaluate(f"document.querySelector('{_TEXT}')?.innerText")
            seen.append((text or "", page.evaluate(_HIGHLIGHTED)))
        return seen
    finally:
        page.close()


def test_a_rug_walks_its_ticks_in_order_and_outlines_each(browser, tmp_path):
    import seaborn as sns

    chart = _save(tmp_path, "rug", lambda f, ax: sns.rugplot(f, x="v", ax=ax))
    seen = _walk(browser, chart, 4)

    assert [text.split(",")[0] for text, _ in seen] == [
        "v is 1.2",
        "v is 2.2",
        "v is 3",
        "v is 9",
    ]
    assert all(len(outlined) == 1 for _, outlined in seen)
    # The walk rises along x, so the outlined tick has to move right each step.
    xs = [outlined[0][0] for _, outlined in seen]
    assert xs == sorted(xs) and len(set(xs)) == 4


def test_a_horizontal_rug_outlines_the_tick_it_announces(browser, tmp_path):
    import seaborn as sns

    chart = _save(tmp_path, "rug_y", lambda f, ax: sns.rugplot(f, y="v", ax=ax))
    seen = _walk(browser, chart, 4)

    assert seen[0][0].startswith("v is 1.2")
    assert all(len(outlined) == 1 for _, outlined in seen)
    # SVG y grows downward, so a rising value moves the tick up.
    ys = [outlined[0][1] for _, outlined in seen]
    assert ys == sorted(ys, reverse=True) and len(set(ys)) == 4


def test_a_hue_split_rug_outlines_its_own_group_only(browser, tmp_path):
    import seaborn as sns

    chart = _save(
        tmp_path, "rug_hue", lambda f, ax: sns.rugplot(f, x="v", hue="g", ax=ax)
    )
    seen = _walk(browser, chart, 2)

    # Group "a" is 2.2 and 3.0: the layer announces those two, not all four.
    assert [text.split(",")[0] for text, _ in seen] == ["v is 2.2", "v is 3"]
    assert all(len(outlined) == 1 for _, outlined in seen)
    assert seen[0][1] != seen[1][1]
