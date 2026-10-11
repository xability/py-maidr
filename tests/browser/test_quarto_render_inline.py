"""A real ``quarto render`` puts working charts in the page (#895).

``test_quarto_inline.py`` drives a page shaped like Quarto's output. This
renders a document with Quarto itself, to ``html`` and to ``revealjs``, in the
kernel this interpreter runs, so what Quarto adds to a page -- require.js
among it -- is all there, and drives the result. It needs the ``quarto`` CLI
(1.8 or newer) and skips without it.

The last part renders documents and a dashboard twice, as they are and
without maidr, and holds each chart to the size, shape and place Quarto gives
the plain figure in the same place.

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
#| fig-alt: "Three bars: a is the tallest, b the shortest."
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


def test_a_cells_fig_alt_names_its_chart_and_describes_it_first(
    browser: Browser, rendered
):
    """Quarto takes ``#| fig-alt`` off before the kernel runs the cell, and
    puts none on a cell's HTML output; the chart reads it from the notebook
    Quarto executes, as r-maidr reads ``fig.alt`` from knitr."""
    _to, path = rendered
    alt = "Three bars: a is the tallest, b the shortest."
    html = path.read_text(encoding="utf-8")
    assert html.count('class="maidr-inline-alt"') == 1
    assert f'aria-label="{alt}"' in html

    page = browser.new_page(viewport={"width": 1200, "height": 900})
    try:
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function(f"() => ({_BOUND})() === 2", timeout=60_000)
        described = page.evaluate(
            """plot => [...document.querySelectorAll(plot)].map(element =>
                 (element.getAttribute('aria-describedby') || '').split(' ')
                   .filter(Boolean)
                   .map(id => (document.getElementById(id) || {}).textContent || ''))""",
            _PLOT,
        )
    finally:
        page.close()
    assert described[0][0] == alt
    assert alt not in described[1]


_SEARCH_BOX = (
    "() => { const box = document.querySelector('.searchbox');"
    " return !!box && getComputedStyle(box).display !== 'none'; }"
)


@pytest.mark.parametrize("rendered", ["revealjs"], indirect=True)
def test_a_decks_search_and_shift_tab_leave_a_chart_on_its_slide(
    browser: Browser, rendered
):
    """inline.js knows a deck, and its search plugin, as Quarto loads them.

    It holds Ctrl+Shift+F and Shift+Tab only on a deck, and knows one by the
    globals reveal.js and its search plugin leave. This checks that Quarto's
    own deck has them: with a check that missed it, the search would open
    from a chart and Shift+Tab would leave the slide. Ctrl+F with Caps Lock
    on is the plugin's key as well.
    """
    _to, path = rendered
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    try:
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function(f"() => ({_BOUND})() === 2", timeout=60_000)
        page.evaluate("Reveal.slide(1)")
        page.wait_for_timeout(800)
        plot = page.locator(_PLOT).first

        plot.focus()
        page.wait_for_timeout(300)
        page.keyboard.press("Control+Shift+F")
        page.wait_for_timeout(300)
        assert not page.evaluate(_SEARCH_BOX), "the deck's search opened"
        page.keyboard.press("Control+F")
        page.wait_for_timeout(300)
        assert not page.evaluate(_SEARCH_BOX), "the deck's search opened on Ctrl+F"

        plot.focus()
        page.wait_for_timeout(300)
        page.keyboard.press("Shift+Tab")
        assert page.evaluate(
            "() => document.activeElement.matches('.reveal .slides section')"
        )

        page.keyboard.press("Control+Shift+F")
        page.wait_for_timeout(300)
        assert page.evaluate(_SEARCH_BOX), "the deck's search never opens"
    finally:
        page.close()


@pytest.mark.parametrize("rendered", ["revealjs"], indirect=True)
def test_the_decks_search_key_can_be_recorded_in_maidrs_settings(
    browser: Browser, rendered
):
    """On Quarto's own deck, whose search plugin hears it on the document.

    The plugin toggles its box, so it is looked at after each press.
    """
    _to, path = rendered
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    try:
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function(f"() => ({_BOUND})() === 2", timeout=60_000)
        page.evaluate("Reveal.slide(1)")
        page.wait_for_timeout(800)
        page.locator(_PLOT).first.focus()
        page.wait_for_timeout(300)
        page.keyboard.press("Control+Comma")
        page.get_by_role("tab", name="Keyboard Shortcuts").click()
        page.get_by_role("button", name="Change shortcut for Toggle Text Mode").click()
        page.keyboard.press("Control+Shift+F")
        status = page.locator('.settings-shortcuts [role="status"]')
        status.filter(has_text="Toggle Text Mode is now").wait_for(timeout=5_000)
        assert not page.evaluate(_SEARCH_BOX), "the deck's search opened"

        # Pressed again in the dialog, with nothing recording it.
        page.keyboard.press("Control+Shift+F")
        page.wait_for_timeout(300)
        assert not page.evaluate(_SEARCH_BOX), "the deck's search opened"
    finally:
        page.close()


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


_SAME_CODE = """\
---
title: Same code
---

```{python}
#| include: false
import matplotlib.pyplot as plt
import maidr
maidr.set_use_cdn(False)
```

```{python}
data, title = [1, 2], "First"
```

```{python}
#| fig-alt: "First: b is twice a."
plt.bar(["a", "b"], data)
plt.title(title)
plt.show()
```

```{python}
data, title = [2, 1], "Second"
```

```{python}
#| fig-alt: "Second: a is twice b."
plt.bar(["a", "b"], data)
plt.title(title)
plt.show()
```

```{python}
#| label: fig-third
#| fig-cap: "Third chart."
#| fig-alt: "Third chart."
plt.bar(["a"], [1])
plt.title("Third")
plt.show()
```
"""


def test_cells_with_the_same_code_take_their_own_alt_text(tmp_path):
    """Of cells with the same code, the running one is found by the kernel's
    place in the render. Alt text that is the figure's caption is left to the
    caption, as r-maidr leaves it, so it is read once."""
    from lxml import html as lxml_html

    quarto = _quarto()
    (tmp_path / "same.qmd").write_text(_SAME_CODE, encoding="utf-8")
    env = {**os.environ, "QUARTO_PYTHON": sys.executable, "MPLBACKEND": "Agg"}
    result = subprocess.run(
        [quarto, "render", "same.qmd", "--to", "html"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        pytest.fail(f"quarto render failed:\n{result.stderr[-4000:]}")
    page = lxml_html.parse(str(tmp_path / "same.html"))

    def having(tag: str, name: str) -> list:
        return page.xpath(f"//{tag}[contains(concat(' ', @class, ' '), ' {name} ')]")

    alts = [element.text_content() for element in having("span", "maidr-inline-alt")]
    names = [chart.get("aria-label") for chart in having("div", "maidr-inline")]
    captions = [" ".join(c.text_content().split()) for c in page.xpath("//figcaption")]
    assert alts == ["First: b is twice a.", "Second: a is twice b."]
    assert names == [
        "First: b is twice a.",
        "Second: a is twice b.",
        "Third, accessible chart",
    ]
    assert captions == ["Figure 1: Third chart."]


# --- The size of the figure Quarto shows without maidr -----------------------
#
# Each document is rendered twice, as it is and without maidr, and each chart
# is held to the plain figure in the same place: Quarto shows that through
# the kernel's figure formatter, cut to what is drawn and sized by fig-dpi.

_SIZED = """\
---
title: Sizes
{options}
---

```{{python}}
#| include: false
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
{maidr}
```

## Defaults

```{{python}}
fig, ax = plt.subplots()
ax.bar(["Q1", "Q2", "Q3", "Q4"], [3, 7, 2, 5])
ax.set_xlabel("Quarter")
plt.show()
```

## Four by three

```{{python}}
fig, ax = plt.subplots(figsize=(4, 3))
ax.bar(["Q1", "Q2", "Q3", "Q4"], [3, 7, 2, 5])
ax.set_xlabel("Quarter")
ax.xaxis.label.set_gid("x-label")
plt.show()
```

## Violins

```{{python}}
rng = np.random.default_rng(1)
cats = [c for c in "ABC" for _ in range(30)]
vals = np.concatenate([rng.normal(i, 1, 30) for i in range(3)])
fig, ax = plt.subplots(figsize=(5, 3.5))
sns.violinplot(x=cats, y=vals, ax=ax)
plt.show()
```

## Regression

```{{python}}
x = np.arange(1, 21)
y = 2 * x + rng.normal(0, 4, 20)
fig, ax = plt.subplots(figsize=(5, 3.5))
sns.regplot(x=x, y=y, ax=ax)
plt.show()
```

## A legend beside the axes

```{{python}}
fig, ax = plt.subplots()
ax.plot([1, 2, 3, 4], [2, 5, 3, 6], label="2024 sales")
ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1)).set_gid("legend")
plt.show()
```
"""

_WITH_MAIDR = "import maidr\nmaidr.set_use_cdn(False)"


def _render_pair(tmp_path: Path, template: str, options: str = "") -> tuple[Path, Path]:
    """Render ``template`` as it is and without maidr; the two HTML files.

    In a kernel with the inline backend, as Quarto runs one: a plain figure
    reaches the page only through it.
    """
    quarto = _quarto()
    env = {**os.environ, "QUARTO_PYTHON": sys.executable}
    env.pop("MPLBACKEND", None)
    paths = []
    for name, setup in (("plain", ""), ("maidr", _WITH_MAIDR)):
        source = tmp_path / f"{name}.qmd"
        source.write_text(
            template.format(options=options, maidr=setup), encoding="utf-8"
        )
        result = subprocess.run(
            [quarto, "render", source.name],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            pytest.fail(f"quarto render failed:\n{result.stderr[-4000:]}")
        paths.append(tmp_path / f"{name}.html")
    return paths[0], paths[1]


@pytest.fixture(scope="module", params=["defaults", "fig-dpi"])
def sized(request, tmp_path_factory) -> tuple[str, Path, Path]:
    options = "fig-dpi: 150" if request.param == "fig-dpi" else ""
    plain, charted = _render_pair(
        tmp_path_factory.mktemp(request.param), _SIZED, options
    )
    return request.param, plain, charted


_BOXES = """sel => [...document.querySelectorAll(sel)].map(e => {
  const r = e.getBoundingClientRect();
  const column = (e.closest('.cell-output-display') || e.parentElement)
    .getBoundingClientRect();
  return {w: r.width, h: r.height, left: r.left, right: r.right,
    column: column.right, attr: [e.getAttribute('width'), e.getAttribute('height')]};
})"""


def _open(browser: Browser, path: Path | str, width: int = 1280, height: int = 900):
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(path if isinstance(path, str) else path.as_uri(), wait_until="load")
    return page


def _boxes(browser: Browser, path: Path, selector: str) -> list[dict]:
    page = _open(browser, path)
    try:
        if "maidr" in selector:
            page.wait_for_function(f"() => ({_BOUND})() === 5", timeout=60_000)
        else:
            page.wait_for_function(
                "() => [...document.images].every(i => i.complete)", timeout=60_000
            )
        return page.evaluate(_BOXES, selector)
    finally:
        page.close()


def test_each_chart_is_the_size_of_the_plain_figure(browser: Browser, sized):
    """Cut to what is drawn and sized by fig-dpi, as the image Quarto writes.

    Where the image is wider than its column -- 7 by 5 inches at fig-dpi
    150 -- it keeps its size and the column scrolls, while the chart
    shrinks to the column as it always has: its own size is the image's
    then, and it is shown at the column's width.
    """
    _label, plain, charted = sized
    images = _boxes(browser, plain, "main .cell-output-display img")
    charts = _boxes(browser, charted, "svg.maidr-inline-svg")

    assert len(images) == len(charts) == 5
    for image, chart in zip(images, charts):
        if image["right"] <= image["column"] + 0.5:
            assert chart["w"] == pytest.approx(image["w"], abs=1.5)
            assert chart["h"] == pytest.approx(image["h"], abs=1.5)
        else:
            # Quarto writes a retina image's size as its pixels halved.
            width, height = (float(v[:-2]) for v in chart["attr"])
            assert width == pytest.approx(float(image["attr"][0]), abs=1.5)
            assert height == pytest.approx(float(image["attr"][1]), abs=1.5)
            assert chart["right"] <= chart["column"] + 0.5
            assert chart["w"] / chart["h"] == pytest.approx(width / height, rel=0.01)


@pytest.mark.parametrize(
    "gid, edge",
    [
        # A 4x3 inch figure's x label, below its canvas's bottom edge.
        ("x-label", (0, 216)),
        # A 7x5 inch figure's legend, past its canvas's right edge.
        ("legend", (504, 0)),
    ],
)
def test_what_lies_outside_the_canvas_is_shown(browser: Browser, sized, gid, edge):
    """The plain figure grows past its canvas to show it; so does the chart."""
    _label, _plain, charted = sized
    page = _open(browser, charted)
    try:
        page.wait_for_function(f"() => ({_BOUND})() === 5", timeout=60_000)
        found = page.evaluate(
            """([gid, edge]) => {
              const mark = document.querySelector(`svg.maidr-inline-svg [id^="${gid}"]`);
              const svg = mark.closest('svg');
              const a = mark.getBoundingClientRect(), b = svg.getBoundingClientRect();
              const corner = new DOMPoint(...edge).matrixTransform(svg.getScreenCTM());
              return {drawn: a.width > 0 && a.height > 0,
                inside: a.top >= b.top - 0.5 && a.bottom <= b.bottom + 0.5
                  && a.left >= b.left - 0.5 && a.right <= b.right + 0.5,
                past_canvas: edge[0] ? a.right > corner.x + 1 : a.bottom > corner.y + 1};
            }""",
            [gid, list(edge)],
        )
    finally:
        page.close()

    assert found == {"drawn": True, "inside": True, "past_canvas": True}


#: The highlight maidr.js draws: its box, and how far its centre is from the
#: nearest point of the layer's marks, in CSS pixels; and the marks' boxes.
_HIGHLIGHT = """([index, type]) => {
  const svg = document.querySelectorAll('svg.maidr-inline-svg')[index];
  const shown = [...svg.querySelectorAll('[data-maidr-owned]')]
    .filter(e => getComputedStyle(e).visibility !== 'hidden');
  if (!shown.length) return null;
  const h = shown[shown.length - 1].getBoundingClientRect();
  const x = h.left + h.width / 2, y = h.top + h.height / 2;
  const schema = JSON.parse(svg.getAttribute('maidr'));
  const layer = schema.subplots.flat().flatMap(c => c.layers).find(l => l.type === type);
  const selectors = [].concat(layer.selectors).join(', ');
  const marks = [...svg.querySelectorAll(selectors)]
    .filter(m => !m.hasAttribute('data-maidr-owned'));
  let nearest = Infinity;
  for (const mark of marks) {
    // A violin's body is a <use> of a path in <defs>, at its x and y.
    let shape = mark, dx = 0, dy = 0;
    if (mark.tagName === 'use') {
      const href = mark.getAttribute('href') || mark.getAttribute('xlink:href');
      shape = svg.querySelector(`[id="${href.slice(1)}"]`);
      dx = +mark.getAttribute('x') || 0;
      dy = +mark.getAttribute('y') || 0;
    }
    if (!shape || !shape.getTotalLength || mark.closest('defs')) continue;
    const length = shape.getTotalLength(), matrix = mark.getScreenCTM();
    for (let s = 0; s <= length; s += 0.25) {
      const q = shape.getPointAtLength(s);
      const p = new DOMPoint(q.x + dx, q.y + dy).matrixTransform(matrix);
      nearest = Math.min(nearest, Math.hypot(p.x - x, p.y - y));
    }
  }
  const box = r => [r.left, r.top, r.width, r.height];
  return {nearest, highlight: box(h),
    marks: marks.map(m => box(m.getBoundingClientRect())).sort((a, b) => a[0] - b[0])};
}"""


@pytest.mark.parametrize("sized", ["defaults"], indirect=True)
@pytest.mark.parametrize(
    "index, type, keys",
    [
        (1, "bar", ["ArrowRight", "ArrowRight"]),
        (2, "violin_kde", ["ArrowRight", "PageUp", "ArrowRight", "ArrowUp"]),
        (3, "smooth", ["ArrowRight", "PageUp", "ArrowRight", "ArrowRight"]),
        (4, "line", ["ArrowRight", "ArrowRight"]),
    ],
)
def test_the_highlight_lands_on_its_mark(browser: Browser, sized, index, type, keys):
    """On the second bar, and on the violin's outline and the lines.

    The bar's highlight is a copy of the bar, drawn in the coordinates the
    chart's box no longer starts at; the others are points on the mark, the
    violin's and the regression's placed from the axes' position, which
    settling the layout no longer moves (#704).
    """
    _label, _plain, charted = sized
    page = _open(browser, charted)
    try:
        page.wait_for_function(f"() => ({_BOUND})() === 5", timeout=60_000)
        page.locator(_PLOT).nth(index).focus()
        page.wait_for_timeout(300)
        for key in keys:
            page.keyboard.press(key)
            page.wait_for_timeout(400)
        found = page.evaluate(_HIGHLIGHT, [index, type])
    finally:
        page.close()

    assert found is not None, f"nothing highlighted on the {type} layer"
    if type == "bar":
        # Q2, the second bar from the left, after two steps.
        assert found["highlight"] == pytest.approx(found["marks"][1], abs=1)
    else:
        assert found["nearest"] < 1.5, found


_CARDS = """\
---
title: Cards
format:
  dashboard:
    expandable: true
---

```{{python}}
#| include: false
import matplotlib.pyplot as plt
{maidr}


# A dashboard shows the value of every line of a cell, and Quarto drops
# matplotlib's only beside an image: drawn in a function, as in a dashboard.
def bars(figsize=None):
    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(["A", "B", "C", "D"], [3, 7, 2, 5])
    ax.set_xlabel("Store")
    plt.show()
```

## Row

```{{python}}
#| title: Sales
bars()
```

```{{python}}
#| title: Small
bars((4, 3))
```
"""


def _served(tmp_path: Path, template: str):
    """Render ``template`` as it is and without maidr, and serve the two pages.

    A dashboard loads modules ``file:`` refuses. Yields their URLs.
    """
    import functools
    import http.server
    import threading

    plain, charted = _render_pair(tmp_path, template)

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args, **kwargs):
            pass

    handler = functools.partial(Quiet, directory=str(plain.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield f"{root}/{plain.name}", f"{root}/{charted.name}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def cards(tmp_path_factory):
    """The two dashboards' URLs."""
    yield from _served(tmp_path_factory.mktemp("cards"), _CARDS)


#: Each card's picture: the part of its box an image draws in (object-fit:
#: contain, as Quarto fills a card with one) or an svg (preserveAspectRatio),
#: and the card body's content box it is placed in.
_PICTURES = """() => [...document.querySelectorAll(
    '.card-body img, .card-body svg.maidr-inline-svg')].map(e => {
  const body = e.closest('.cell-output-display');
  const b = body.getBoundingClientRect(), r = e.getBoundingClientRect();
  const w = e.tagName === 'IMG' ? e.naturalWidth : e.viewBox.baseVal.width;
  const h = e.tagName === 'IMG' ? e.naturalHeight : e.viewBox.baseVal.height;
  const k = Math.min(r.width / w, r.height / h);
  const wrapper = e.closest('.maidr-inline');
  return {w: w * k, h: h * k, left: r.left + (r.width - w * k) / 2 - b.left,
    right: b.right - (r.left + (r.width + w * k) / 2), boxW: b.width, boxH: b.height,
    bottom: r.top + (r.height + h * k) / 2 - b.top,
    line: wrapper ? parseFloat(getComputedStyle(wrapper).lineHeight) : 0,
    scrolls: body.scrollHeight > body.clientHeight + 1,
    full: e.closest('.card').getAttribute('data-full-screen')};
})"""


def _pictures(
    browser: Browser, url: str, width: int, height: int, full: bool, charts: int = 2
):
    """The cards' pictures as laid out, after the first is shown full screen, and after."""
    page = _open(browser, url, width, height)
    try:
        if url.endswith("maidr.html"):
            page.wait_for_function(f"() => ({_BOUND})() === {charts}", timeout=60_000)
        page.wait_for_function(
            "() => [...document.images].every(i => i.complete)", timeout=60_000
        )
        page.wait_for_timeout(500)
        seen = [page.evaluate(_PICTURES)]
        if full:
            # bslib hides the control on a phone, where it still works.
            page.evaluate("document.querySelector('.bslib-full-screen-enter').click()")
            page.wait_for_timeout(800)
            seen.append([p for p in page.evaluate(_PICTURES) if p["full"] == "true"])
            page.keyboard.press("Escape")
            page.wait_for_timeout(800)
            seen.append(page.evaluate(_PICTURES))
        return seen
    finally:
        page.close()


@pytest.mark.parametrize("viewport", [(1280, 800), (390, 844)])
def test_a_card_is_filled_as_the_plain_figure_fills_it(
    browser: Browser, cards, viewport
):
    """As large as the card allows, its shape kept, centred; and full screen.

    Less a line below it for maidr's text where the card's height is the
    limit: shown full screen, or a small card. Where its width is, and in a
    phone's single column, where the card takes its height from the figure,
    exactly the plain figure.
    """
    plain, charted = cards
    images = _pictures(browser, plain, *viewport, full=True)
    charts = _pictures(browser, charted, *viewport, full=True)

    assert [len(shown) for shown in charts] == [len(shown) for shown in images]
    assert [len(shown) for shown in charts] == [2, 1, 2]
    for shown_images, shown_charts in zip(images, charts):
        for image, chart in zip(shown_images, shown_charts):
            assert chart["w"] / chart["h"] == pytest.approx(
                image["w"] / image["h"], rel=0.01
            )
            if image["w"] >= image["boxW"] - 1:
                # The width is the limit.
                assert chart["w"] == pytest.approx(image["w"], abs=1.5)
                assert chart["h"] == pytest.approx(image["h"], abs=1.5)
            else:
                assert chart["h"] == pytest.approx(image["h"] - chart["line"], abs=1.5)
                assert chart["bottom"] + chart["line"] <= chart["boxH"] + 1
            assert chart["left"] == pytest.approx(chart["right"], abs=1.5)


def test_maidrs_braille_field_is_in_view_in_a_card(browser: Browser, cards):
    """Below a chart that fills its card, the card scrolls to it when it opens."""
    _plain, charted = cards
    page = _open(browser, charted, 1280, 800)
    try:
        page.wait_for_function(f"() => ({_BOUND})() === 2", timeout=60_000)
        page.locator(_PLOT).first.focus()
        page.wait_for_timeout(300)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(300)
        page.keyboard.press("b")
        page.wait_for_timeout(600)
        field = page.evaluate(
            """() => {
              const a = document.activeElement, card = a.closest('.card-body');
              const r = a.getBoundingClientRect(), c = card.getBoundingClientRect();
              return {braille: a.id.startsWith('maidr-braille-textarea'),
                in_view: r.top >= c.top - 1 && r.bottom <= c.bottom + 1};
            }"""
        )
    finally:
        page.close()

    assert field == {"braille": True, "in_view": True}


_SHARED = """\
---
title: Shared cards
format:
  dashboard:
    expandable: true
---

```{{python}}
#| include: false
import matplotlib.pyplot as plt
{maidr}


# Labels long enough for maidr's text of a value to take two lines.
def bars(title):
    fig, ax = plt.subplots()
    ax.bar(["A", "B", "C", "D"], [3, 7, 2, 5])
    ax.set_title(title)
    ax.set_xlabel("Store of the northern sales region")
    ax.set_ylabel("Thousands of units sold over the last quarter")
    plt.show()
```

## Row

```{{python}}
#| title: Two charts
bars("North")
bars("South")
```

```{{python}}
#| title: Text and a chart
print("Units sold this quarter, in thousands.")
bars("East")
```
"""


@pytest.fixture(scope="module")
def shared_cards(tmp_path_factory):
    """Two dashboards whose cards hold more than a chart, served."""
    yield from _served(tmp_path_factory.mktemp("shared"), _SHARED)


#: maidr's text below a chart in a card, and the chart, against what of
#: their box is shown.
_TEXT_IN_VIEW = """() => {
  const wrapper = document.activeElement.closest('.maidr-inline');
  const area = wrapper.querySelector('[id^="maidr-text-container"]').parentElement;
  const plot = wrapper.querySelector('figure[id^="maidr-figure"] > [tabindex]');
  const box = area.closest('.cell-output-display');
  const r = area.getBoundingClientRect(), b = box.getBoundingClientRect();
  const top = b.top + box.clientTop, bottom = top + box.clientHeight;
  const line = parseFloat(getComputedStyle(area).lineHeight);
  return {text: area.textContent.trim(), lines: Math.round(r.height / line),
    in_view: r.top >= top - 1 && r.bottom <= bottom + 1,
    chart_in_view: plot.getBoundingClientRect().top >= top - 1};
}"""


def test_maidrs_text_is_in_view_in_a_card(browser: Browser, shared_cards):
    """A value longer than the line kept for it: the card is scrolled to show it.

    Below a chart whose share of its card's height is the limit. The
    instructions maidr shows as the chart takes the focus, several lines
    here, are left where they run: the chart stays where the reader, or
    the pointer that clicked it, found it.
    """
    _plain, charted = shared_cards
    page = _open(browser, charted, 1280, 800)
    try:
        page.wait_for_function(f"() => ({_BOUND})() === 3", timeout=60_000)
        page.locator(_PLOT).first.focus()
        page.wait_for_timeout(600)
        instructions = page.evaluate(_TEXT_IN_VIEW)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(600)
        value = page.evaluate(_TEXT_IN_VIEW)
    finally:
        page.close()

    assert instructions["lines"] > 1, instructions
    assert instructions["chart_in_view"], instructions
    # More than the line kept for it, below a chart that fills the rest.
    assert value["lines"] > 1, value
    assert value["in_view"], value


@pytest.mark.parametrize("viewport", [(1280, 800), (390, 844)])
def test_a_card_shared_with_other_outputs_gives_the_chart_the_figures_share(
    browser: Browser, shared_cards, viewport
):
    """Two charts from one cell, or a print() before one, as with plain figures.

    The card's body shares its height among its outputs as it does among
    plain figures, and a chart is fitted into its share as a figure is,
    less the line for maidr's text where the share's height is the limit:
    all of it shown, nothing to scroll. At a phone's width, where the card
    takes its height from what it holds, a chart's share is the figure's
    height and no more.
    """
    plain, charted = shared_cards
    images = _pictures(browser, plain, *viewport, full=True, charts=3)
    charts = _pictures(browser, charted, *viewport, full=True, charts=3)

    assert [len(shown) for shown in charts] == [len(shown) for shown in images]
    assert [len(shown) for shown in charts] == [3, 2, 3]
    for shown_images, shown_charts in zip(images, charts):
        for image, chart in zip(shown_images, shown_charts):
            assert chart["boxH"] == pytest.approx(image["boxH"], abs=1.5)
            assert chart["w"] / chart["h"] == pytest.approx(
                image["w"] / image["h"], rel=0.01
            )
            if image["w"] >= image["boxW"] - 1:
                assert chart["w"] == pytest.approx(image["w"], abs=1.5)
            else:
                assert chart["h"] == pytest.approx(image["h"] - chart["line"], abs=1.5)
            assert chart["bottom"] <= chart["boxH"] + 1
            assert not chart["scrolls"], chart
