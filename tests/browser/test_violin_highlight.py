"""A violin's box layer is outlined on the violin read, in the drawn order.

Two things the schema tests cannot see, measured in a real browser:

* on seaborn's horizontal violins, Up moves the outline up the page, onto the
  whisker of the violin it announces. The box layer used to reverse its data
  for a horizontal violin and not its selectors, so each violin was outlined
  at its mirror image, and the announced violin moved down the page.
  seaborn draws a violin's whiskers as one line from the minimum to the
  maximum, and the layer names that line for both: maidr.js marks the
  minimum with a dot at the line's left end, where it is drawn, rather than
  outlining the whole line (xability/maidr#1548, in maidr.js 4.17.0);
* on a matplotlib violin, whose drawing has no element spanning the
  quartiles, the 25% and 75% stops are announced with no outline at all. The
  layer used to name the min-to-max bar there, which put them on the caps.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000
_TEXT = "#maidr-text-container"
_HIGHLIGHTS = "[id^='maidr-highlight']"

#: Measure in screen coordinates, as the box plot test does: the centre, and
#: the left end, which is where a whisker drawn along x has its minimum.
_MEASURE = """(element) => {
  const rect = element.getBoundingClientRect();
  return {left: rect.left,
          x: rect.left + rect.width / 2,
          y: rect.top + rect.height / 2};
}"""

#: Connected highlight elements, which is what the audit harness counts.
_CONNECTED = f"""() => [...document.querySelectorAll("{_HIGHLIGHTS}")]
  .filter((element) => element.isConnected).length"""


def _open(browser, path: Path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.goto(path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)
    return page, errors


def _step(page, key: str) -> str:
    """Press one key and read the announcement after the runtime updates."""
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.locator(_TEXT).inner_text()


def _highlight(page) -> dict:
    """The one outline drawn, by its screen-space centre."""
    highlighted = page.locator(f"svg {_HIGHLIGHTS}")
    assert highlighted.count() == 1
    return highlighted.evaluate(_MEASURE)


@pytest.fixture
def seaborn_horizontal_violins(tmp_path: Path) -> tuple[Path, dict]:
    """Two horizontal seaborn violins; return the page and each one's whisker."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    import maidr

    sns = pytest.importorskip("seaborn")
    rng = np.random.default_rng(5)
    values = np.concatenate([rng.normal(10, 1, 60), rng.normal(30, 2, 60)])
    names = ["first"] * 60 + ["second"] * 60
    fig, ax = plt.subplots(figsize=(8, 5))
    path = tmp_path / "violins.html"
    try:
        sns.violinplot(x=values, y=names, inner="box", ax=ax)
        ax.set(xlabel="Value", ylabel="Group")
        maidr.save_html(fig, file=str(path), use_cdn=False)
        # The whisker of each violin is its inner box's longest line along x,
        # at that violin's category position.
        whiskers: dict = {}
        labels = [tick.get_text() for tick in ax.get_yticklabels()]
        positions = dict(zip(labels, ax.get_yticks()))
        for name, position in positions.items():
            lines = [
                line
                for line in ax.lines
                if len(line.get_ydata()) == 2
                and np.allclose(line.get_ydata(), position)
            ]
            whisker = max(lines, key=lambda line: np.ptp(line.get_xdata()))
            whiskers[name] = str(whisker.get_gid())
    finally:
        plt.close("all")
    return path, whiskers


def test_up_moves_the_outline_up_onto_the_violin_announced(
    browser, seaborn_horizontal_violins: tuple[Path, dict]
) -> None:
    path, whiskers = seaborn_horizontal_violins
    page, errors = _open(browser, path)
    try:
        drawn = {
            name: page.locator(
                f"g[id='{gid}'] > path:not([data-maidr-owned])"
            ).evaluate(_MEASURE)
            for name, gid in whiskers.items()
        }
        top, bottom = sorted(drawn, key=lambda name: drawn[name]["y"])

        # The minimum is marked where it is drawn: at the left end of the
        # whisker of the violin announced.
        spoken = _step(page, "ArrowRight")
        start = _highlight(page)
        assert f"Group is {bottom}, Minimum" in spoken, spoken
        assert start["x"] == pytest.approx(drawn[bottom]["left"], abs=0.5), spoken
        assert start["y"] == pytest.approx(drawn[bottom]["y"], abs=0.5), spoken

        spoken = _step(page, "ArrowUp")
        above = _highlight(page)
        assert f"Group is {top}, Minimum" in spoken, spoken
        assert above["x"] == pytest.approx(drawn[top]["left"], abs=0.5), spoken
        assert above["y"] == pytest.approx(drawn[top]["y"], abs=0.5), spoken
        assert above["y"] < start["y"], "ArrowUp moved the outline down"
        assert not errors, errors
    finally:
        page.close()


@pytest.fixture
def matplotlib_violins(tmp_path: Path) -> Path:
    """Two matplotlib violins with their medians drawn."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    import maidr

    rng = np.random.default_rng(6)
    fig, ax = plt.subplots(figsize=(8, 5))
    path = tmp_path / "mpl_violins.html"
    try:
        ax.violinplot([rng.normal(10, 1, 60), rng.normal(30, 2, 60)], showmedians=True)
        ax.set(xlabel="Group", ylabel="Value")
        maidr.save_html(fig, file=str(path), use_cdn=False)
    finally:
        plt.close("all")
    return path


def test_the_quartiles_are_announced_without_an_outline(
    browser, matplotlib_violins: Path
) -> None:
    page, errors = _open(browser, matplotlib_violins)
    try:
        spoken = _step(page, "ArrowRight")
        assert "Minimum" in spoken, spoken
        assert page.evaluate(_CONNECTED) == 1

        for stop, outlined in (("25%", 0), ("50%", 1), ("75%", 0), ("Maximum", 1)):
            spoken = _step(page, "ArrowUp")
            assert f"{stop} Value" in spoken, spoken
            assert page.evaluate(_CONNECTED) == outlined, spoken
        assert not errors, errors
    finally:
        page.close()
