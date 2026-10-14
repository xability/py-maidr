"""Horizontal box navigation follows the drawing, not category input order (#911).

Seaborn puts Africa above Europe by inverting the category axis; matplotlib
puts the same first category below the second. Reversing every horizontal
export kept announcements paired with their artists but made Up move down
on seaborn. Inverting either axis after drawing must change the walk too.
These tests measure the real screen positions, independently of the schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000
_TEXT = "#maidr-text-container"
_CATEGORIES = ["Africa", "Europe"]
_VALUES = [[11, 12, 13, 14, 15], [31, 32, 33, 34, 35]]
_MEDIANS = {"Africa": 13, "Europe": 33}

#: Measure in screen coordinates, not SVG path coordinates: a transform or
#: viewBox can make those differ. Include the path to verify artist pairing.
_MEASURE = """(element) => {
  const rect = element.getBoundingClientRect();
  return {d: element.getAttribute('d'),
          x: rect.left + rect.width / 2,
          y: rect.top + rect.height / 2};
}"""


@pytest.fixture(params=["seaborn", "matplotlib"])
def horizontal_boxes(request, tmp_path: Path, invert_yaxis: bool) -> tuple[Path, dict]:
    """Save two boxes with the bundled runtime and return their median gids."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import maidr

    fig, ax = plt.subplots(figsize=(8, 5))
    path = tmp_path / "horizontal_boxes.html"
    try:
        if request.param == "seaborn":
            sns = pytest.importorskip("seaborn")
            sns.boxplot(
                x=[value for values in _VALUES for value in values],
                y=[category for category in _CATEGORIES for _ in range(5)],
                order=_CATEGORIES,
                orient="h",
                ax=ax,
            )
            medians = ax.containers[0].medians
        else:
            artists = ax.boxplot(_VALUES, vert=False)
            ax.set_yticks([1, 2], labels=_CATEGORIES)
            medians = artists["medians"]
        ax.set(xlabel="Value", ylabel="Continent")
        # The registration patch has already run. Export must inspect the
        # final axis direction rather than remember its state while drawing.
        if invert_yaxis:
            ax.invert_yaxis()
        maidr.save_html(fig, file=str(path), use_cdn=False)
        gids = {
            category: str(median.get_gid())
            for category, median in zip(_CATEGORIES, medians)
        }
    finally:
        plt.close("all")
    return path, gids


def _step(page, key: str) -> str:
    """Press one key and read the announcement after the runtime updates."""
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.locator(_TEXT).inner_text()


def _highlight(page) -> dict:
    """Return the single visible outline's path and screen-space center."""
    highlighted = page.locator("svg [id^=maidr-highlight]")
    assert highlighted.count() == 1
    # A vertical median path has zero geometric width, so Playwright's
    # non-empty bounding-box visibility check is not appropriate here.
    assert highlighted.evaluate("(e) => getComputedStyle(e).visibility") == "visible"
    return highlighted.evaluate(_MEASURE)


def _assert_pairing(spoken: str, highlight: dict, category: str, drawn: dict) -> None:
    """Keep the announced category and median paired with the drawn artist."""
    expected = f"Continent is {category}, 50% Value is {_MEDIANS[category]}"
    assert expected in spoken, spoken
    assert highlight["d"] == drawn[category]["d"], spoken
    assert highlight["x"] == pytest.approx(drawn[category]["x"], abs=0.5)
    assert highlight["y"] == pytest.approx(drawn[category]["y"], abs=0.5)


@pytest.mark.parametrize("invert_yaxis", [False, True], ids=["default", "inverted"])
def test_up_and_down_follow_the_drawn_boxes(
    browser, horizontal_boxes: tuple[Path, dict], invert_yaxis: bool
) -> None:
    """Up moves the paired median outline up, and Down returns it below."""
    path, gids = horizontal_boxes
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
        page.click("svg[maidr]", force=True)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1_500)

        drawn = {
            category: page.locator(
                f"g[id='{gid}'] > path:not([data-maidr-owned])"
            ).evaluate(_MEASURE)
            for category, gid in gids.items()
        }
        top, bottom = sorted(_CATEGORIES, key=lambda category: drawn[category]["y"])
        assert drawn[top]["y"] < drawn[bottom]["y"]
        assert drawn[top]["d"] != drawn[bottom]["d"]

        # Enter the bottom row and walk across its statistics to the median.
        # The empty lower-outlier stop is included by the shipped runtime.
        for _ in range(4):
            spoken = _step(page, "ArrowRight")
            if "50% Value" in spoken:
                break
        before = _highlight(page)
        before_spoken = spoken

        spoken = _step(page, "ArrowUp")
        above = _highlight(page)
        assert above["y"] < before["y"], "ArrowUp moved the highlight down"
        _assert_pairing(before_spoken, before, bottom, drawn)
        _assert_pairing(spoken, above, top, drawn)

        spoken = _step(page, "ArrowDown")
        below = _highlight(page)
        assert below["y"] > above["y"], "ArrowDown moved the highlight up"
        _assert_pairing(spoken, below, bottom, drawn)
        assert below["y"] == pytest.approx(before["y"], abs=0.5)
        assert not errors, errors
    finally:
        page.close()
