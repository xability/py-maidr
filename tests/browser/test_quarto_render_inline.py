"""A real ``quarto render`` puts working charts in the page (#895).

``test_quarto_inline.py`` drives a page shaped like Quarto's output. This
renders a document with Quarto itself, to ``html`` and to ``revealjs``, in the
kernel this interpreter runs, so what Quarto adds to a page -- require.js
among it -- is all there, and drives the result. It needs the ``quarto`` CLI
(1.8 or newer) and skips without it.

The charts are rendered with ``use_cdn=False``, so the page needs no network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser

pytestmark = pytest.mark.browser

_PLOT = 'figure[id^="maidr-figure"] > [tabindex]'
_BOUND = "() => document.querySelectorAll('article[id^=maidr-article-]').length"

_DOCUMENT = """\
---
title: Two charts
---

```{python}
#| include: false
import matplotlib.pyplot as plt
import maidr
maidr.set_use_cdn(False)
```

## First

```{python}
fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(["a", "b", "c"], [3, 1, 2])
ax.set_title("First")
plt.show()
```

## Second

```{python}
#| label: fig-second
#| fig-cap: "The second chart"
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot([1, 2, 3], [2, 3, 1])
plt.show()
```
"""


def _quarto() -> str:
    quarto = shutil.which("quarto")
    if quarto is None:
        pytest.skip("the quarto CLI is not installed")
    return quarto


def _render(tmp_path: Path, to: str) -> Path:
    quarto = _quarto()
    source = tmp_path / "doc.qmd"
    source.write_text(_DOCUMENT, encoding="utf-8")
    env = {**os.environ, "QUARTO_PYTHON": sys.executable, "MPLBACKEND": "Agg"}
    result = subprocess.run(
        [quarto, "render", str(source), "--to", to, "--output", f"{to}.html"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        pytest.fail(f"quarto render failed:\n{result.stderr[-4000:]}")
    return tmp_path / f"{to}.html"


@pytest.fixture(scope="module", params=["html", "revealjs"])
def rendered(request, tmp_path_factory) -> tuple[str, Path]:
    return request.param, _render(tmp_path_factory.mktemp(request.param), request.param)


def test_the_charts_are_in_the_page(rendered):
    _to, path = rendered
    html = path.read_text(encoding="utf-8")

    assert html.count('class="maidr-inline"') == 2
    assert "<iframe" not in html
    # What a frame kept away from the page: Quarto puts require.js there.
    assert "require" in html


def test_maidr_takes_over_every_chart_and_leaves_the_page_alone(
    browser: Browser, rendered
):
    to, path = rendered
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function(f"() => ({_BOUND})() === 2", timeout=60_000)

        slide = "() => window.Reveal ? JSON.stringify(Reveal.getIndices()) : ''"
        before = page.evaluate(slide)
        for index in range(2):
            plot = page.locator(_PLOT).nth(index)
            if to == "revealjs":
                page.evaluate(f"Reveal.slide({index + 1})")
                page.wait_for_timeout(800)
                before = page.evaluate(slide)
            plot.focus()
            page.wait_for_timeout(300)
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
            announced = page.evaluate(
                "() => (document.getElementById('maidr-text-container') || {})"
                ".innerText || ''"
            )
            assert announced.strip(), f"chart {index} said nothing"
            assert page.evaluate(slide) == before, "the deck moved"
    finally:
        page.close()
    assert not errors


_DASHBOARD = """\
---
title: Two cards
format: dashboard
---

```{python}
#| include: false
import matplotlib.pyplot as plt
import maidr
maidr.set_use_cdn(False)
```

## Row

```{python}
#| title: Bars
fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(["a", "b", "c"], [3, 1, 2])
plt.show()
```

```{python}
#| title: Line
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot([1, 2, 3], [2, 3, 1])
plt.show()
```
"""


def test_a_dashboards_charts_stay_in_their_cards(tmp_path):
    """Quarto's dashboard filter lifts an output it takes for a bslib component."""
    from lxml import html as lxml_html

    quarto = _quarto()
    (tmp_path / "dash.qmd").write_text(_DASHBOARD, encoding="utf-8")
    env = {**os.environ, "QUARTO_PYTHON": sys.executable, "MPLBACKEND": "Agg"}
    result = subprocess.run(
        [quarto, "render", "dash.qmd"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        pytest.fail(f"quarto render failed:\n{result.stderr[-4000:]}")
    page = lxml_html.parse(str(tmp_path / "dash.html"))

    charts = page.xpath("//div[contains(concat(' ', @class, ' '), ' maidr-inline ')]")
    assert len(charts) == 2
    for chart in charts:
        card = chart.xpath(
            "ancestor::div[contains(concat(' ', @class, ' '), ' card ')]"
        )
        assert card, "a chart was moved out of its card"
