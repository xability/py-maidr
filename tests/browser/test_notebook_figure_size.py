"""A chart in a notebook's frame is shown as the notebook shows the plain figure.

This opens a page shaped like a notebook's outputs: for each figure, the image
the inline backend makes of it -- IPython's ``print_figure`` or
``retina_figure`` with ``InlineBackend.print_figure_kwargs``, in an output
area that keeps an image to its width (``max-width: 100%``, as JupyterLab's
``.jp-RenderedImage`` does) -- and the maidr chart of the same figure, in an
output area of the same width. ``tests/util/test_notebook_figure.py`` holds
the sizes the chart is given to IPython's; this holds what a browser shows:

* the chart's size and shape are the image's, at the default settings, for
  a 4x3 figure, whose x label lies below the canvas and is shown, at a dpi
  of 150, and in ``retina``;
* in an output area narrower than the image, the chart shrinks with it, as
  the image does, to the same width, though JupyterLab pads an HTML output
  on its right and an image not; and maidr's text, braille and review
  fields and its help and settings dialogs stay inside the frame;
* the highlight lands on the mark it names;
* a frame is measured again only when something in it, or its width,
  changes, and the notebook stays where it was scrolled, down or across,
  when it is;
* maidr's dialogs are shown whole in the part of the notebook a reader
  sees, over a chart smaller than a dialog, in a narrow output area, and
  over a chart taller than the window; once one closes, the notebook is
  where the reader had it, or, if the window changed size meanwhile, the
  chart is in view.

The other half is the libraries maidr shows in the same frame: a Plotly
figure without a height is as tall as the notebook's renderer draws it and
is not cut at the frame's edge, a Plotly or Bokeh chart wider than the
output area widens the frame rather than being cut off, a Bokeh chart keeps
its bottom edge, and a Bokeh or Altair chart sized by its container fills
the frame.

The charts use the bundled ``maidr.js``, stashed on the page as a notebook
stashes it, so the page needs no network. plotly.js and BokehJS come from the
installed packages; Vega, which no package ships, is fetched once and handed
to the page, and the Altair test skips without a network.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Frame, Page

pytestmark = pytest.mark.browser

IPython = pytest.importorskip("IPython")
pytest.importorskip("matplotlib_inline")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from IPython.core.formatters import DisplayFormatter  # noqa: E402
from IPython.core.interactiveshell import InteractiveShellABC  # noqa: E402
from IPython.core.pylabtools import print_figure, retina_figure  # noqa: E402
from matplotlib_inline.config import InlineBackend  # noqa: E402
from traitlets.config import Configurable  # noqa: E402

import maidr  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402
from maidr.util.notebook_figure import register_inline_backend  # noqa: E402

_PARSE_TIMEOUT_MS = 60_000
_PLOT = 'figure[id^="maidr-figure-"] > [tabindex]'
_BOUND = f"() => document.querySelector('{_PLOT}') !== null"
_ANNOUNCED = (
    "() => { const t = document.querySelector('#maidr-text-container');"
    " return !!t && t.textContent.trim().length > 0; }"
)

#: An output area, the rule JupyterLab keeps an image to it with, and the
#: padding it keeps to the right of an HTML output and not of an image.
_PAGE_STYLE = """
body { margin: 0; font-family: sans-serif; }
.output { overflow-x: auto; margin: 0 0 24px; box-sizing: border-box; }
.image > img { max-width: 100%; height: auto; }
.html { padding-right: 20px; }
"""


class _Shell(Configurable):
    """A notebook kernel's shell, as far as ``%config`` and the formatter go."""

    def __init__(self) -> None:
        super().__init__()
        self.display_formatter = DisplayFormatter()
        self.configurables: list = []
        self.user_ns: dict = {}


InteractiveShellABC.register(_Shell)


def _figure(size=None, dpi=None, title="Units by quarter"):
    kwargs: dict[str, Any] = {}
    if size is not None:
        kwargs["figsize"] = size
    if dpi is not None:
        kwargs["dpi"] = dpi
    fig, ax = plt.subplots(**kwargs)
    ax.bar(["Q1", "Q2", "Q3", "Q4"], [5, 7, 3, 8])
    ax.set_title(title)
    ax.set_xlabel("Quarter")
    ax.set_ylabel("Units")
    ax.xaxis.label.set_gid("x-label")
    return fig


def _plain_image(fig) -> str:
    """The ``<img>`` a notebook shows of ``fig``, as the inline backend makes it."""
    config = InlineBackend.instance()
    kwargs = dict(config.print_figure_kwargs)
    if "retina" in config.figure_formats:
        data, shown = retina_figure(fig, base64=True, **kwargs)
        return (
            f'<img src="data:image/png;base64,{data}" '
            f'width="{shown["width"]}" height="{shown["height"]}">'
        )
    data = print_figure(fig, "png", base64=True, **kwargs)
    return f'<img src="data:image/png;base64,{data}">'


def _notebook_page(
    tmp_path: Path,
    cases: dict[str, tuple[Callable[[], Any], int]],
    *,
    scroller: int | None = None,
    **config: Any,
) -> str:
    """A notebook's outputs: each figure's plain image, then its chart.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Where to write the page.
    cases : dict
        ``name -> (make the figure, the output area's width)``.
    scroller : int, optional
        The height of a box the outputs scroll in, below a toolbar, as
        JupyterLab's and Notebook 7's do. By default the page scrolls, as
        an nbconvert export does.
    **config
        ``InlineBackend`` settings, as ``%config`` would set them.

    Returns
    -------
    str
        The page's ``file://`` URL.
    """
    source = json.dumps(maidr.read_bundled_js()).replace("</", "<\\/")
    shell = _Shell()
    outputs = []
    InlineBackend.clear_instance()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(IPython, "get_ipython", lambda: shell)
            patch.setattr(Environment, "is_notebook", staticmethod(lambda: True))
            backend = register_inline_backend()
            backend.shell = None  # No formatter: as ``import maidr`` leaves a kernel.
            for name, value in config.items():
                setattr(backend, name, value)
            for name, (make, width) in cases.items():
                fig = make()
                try:
                    plain = _plain_image(fig)
                    chart = str(maidr.render(fig, use_cdn=False))
                finally:
                    plt.close(fig)
                style = f"width: {width}px"
                outputs.append(
                    f'<div class="output image" id="plain-{name}" style="{style}">'
                    f"{plain}</div>"
                    f'<div class="output html" id="chart-{name}" style="{style}">'
                    f"{chart}</div>"
                )
    finally:
        InlineBackend.clear_instance()
    body = "".join(outputs)
    if scroller is not None:
        body = (
            '<div class="toolbar" style="height: 120px"></div>'
            f'<div class="scroller" style="height: {scroller}px; overflow-y: auto">'
            f'<div style="height: 300px"></div>{body}'
            '<div style="height: 300px"></div></div>'
        )
    out = tmp_path / "notebook.html"
    out.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_PAGE_STYLE}</style></head><body>"
        f"<script>window.__maidrJsSource = {source};</script>"
        f"{body}</body></html>",
        encoding="utf-8",
    )
    return out.as_uri()


#: Read in the notebook's page: the plain image, the chart's frame, and the
#: chart's svg in the page's coordinates.
_MEASURE = """(name) => {
  const box = (r) => ({x: r.x, y: r.y, width: r.width, height: r.height});
  const image = document.querySelector(`#plain-${name} img`);
  const frame = document.querySelector(`#chart-${name} iframe`);
  const doc = frame.contentDocument;
  const svg = doc.querySelector('figure[id^="maidr-figure-"] svg');
  const f = frame.getBoundingClientRect();
  const s = svg.getBoundingClientRect();
  const label = doc.getElementById('x-label');
  const output = document.querySelector(`#chart-${name}`);
  return {
    image: box(image.getBoundingClientRect()),
    imageOutput: box(image.parentElement.getBoundingClientRect()),
    frame: box(f),
    chartOutput: box(output.getBoundingClientRect()),
    svg: {x: f.x + s.x, y: f.y + s.y, width: s.width, height: s.height},
    frameHeight: frame.clientHeight,
    docHeight: doc.documentElement.scrollHeight,
    label: label ? box(label.getBoundingClientRect()) : null,
    svgInFrame: box(s),
    outputScrolls: output.scrollWidth > output.clientWidth + 1,
  };
}"""


def _open(browser: Browser, url: str, frames: int, width: int = 1200) -> Page:
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.goto(url, wait_until="load")
    assert len(page.frames) - 1 == frames
    for frame in page.frames[1:]:
        frame.wait_for_function(_BOUND, timeout=_PARSE_TIMEOUT_MS)
    # The frame is sized on load and again as maidr.js mounts the chart.
    page.wait_for_timeout(1_500)
    return page


def _chart_frame(page: Page, name: str) -> Frame:
    frame = page.query_selector(f"#chart-{name} iframe").content_frame()
    assert frame is not None
    return frame


# --- matplotlib: the chart is the plain figure's image ------------------------

_SIZES = {
    "default": (lambda: _figure(), 1100),
    "small": (lambda: _figure(size=(4, 3)), 1100),
    "dpi150": (lambda: _figure(dpi=150), 1100),
    "wide": (lambda: _figure(size=(12, 4)), 1100),
    "narrow": (lambda: _figure(), 320),
}


@pytest.fixture(scope="module")
def png_page(tmp_path_factory) -> str:
    return _notebook_page(tmp_path_factory.mktemp("png"), _SIZES)


@pytest.fixture(scope="module")
def retina_page(tmp_path_factory) -> str:
    return _notebook_page(
        tmp_path_factory.mktemp("retina"),
        {"default": _SIZES["default"], "small": _SIZES["small"]},
        figure_formats={"retina"},
    )


def _assert_like_the_image(seen: dict, name: str) -> None:
    image, svg = seen["image"], seen["svg"]
    assert svg["width"] == pytest.approx(image["width"], abs=1), (
        f"{name}: the chart is {svg['width']:.1f}px wide, the plain figure "
        f"{image['width']:.1f}px"
    )
    assert svg["height"] == pytest.approx(image["height"], abs=1), (
        f"{name}: the chart is {svg['height']:.1f}px tall, the plain figure "
        f"{image['height']:.1f}px"
    )
    # Where the image starts in its output area, the chart starts in its own.
    assert svg["x"] - seen["chartOutput"]["x"] == pytest.approx(
        image["x"] - seen["imageOutput"]["x"], abs=0.5
    )
    # The frame holds the chart, and no more than its width.
    assert seen["frame"]["width"] == pytest.approx(svg["width"], abs=1)
    assert seen["frameHeight"] >= seen["docHeight"] - 1


@pytest.mark.parametrize("name", ["default", "small", "dpi150", "wide", "narrow"])
def test_a_chart_has_the_plain_figures_size(browser, png_page, name):
    page = _open(browser, png_page, frames=len(_SIZES))
    try:
        seen = page.evaluate(_MEASURE, name)
    finally:
        page.close()

    _assert_like_the_image(seen, name)
    assert not seen["outputScrolls"], f"{name}: the chart's output area scrolls"


@pytest.mark.parametrize("name", ["default", "small"])
def test_retina_is_shown_at_the_figures_dpi(browser, retina_page, name):
    page = _open(browser, retina_page, frames=2)
    try:
        seen = page.evaluate(_MEASURE, name)
    finally:
        page.close()

    _assert_like_the_image(seen, name)


def test_the_x_label_of_a_small_figure_is_shown(browser, png_page):
    """A 4x3 figure's x label lies below its canvas; the chart shows it."""
    page = _open(browser, png_page, frames=len(_SIZES))
    try:
        seen = page.evaluate(_MEASURE, "small")
    finally:
        page.close()

    label, svg = seen["label"], seen["svgInFrame"]
    assert label is not None and label["height"] > 0
    assert (
        label["y"] + label["height"] <= svg["y"] + svg["height"] + 0.5
    ), "the x label runs past the bottom of the chart"


def test_the_highlight_lands_on_the_bar(browser, png_page):
    page = _open(browser, png_page, frames=len(_SIZES))
    try:
        frame = _chart_frame(page, "narrow")
        frame.focus(_PLOT)
        page.wait_for_timeout(300)
        page.keyboard.press("ArrowRight")
        frame.wait_for_selector(
            "[id^=maidr-highlight]", state="attached", timeout=10_000
        )
        page.wait_for_timeout(300)
        boxes = frame.evaluate(
            """() => {
              const box = (e) => {
                const r = e.getBoundingClientRect();
                return [r.left, r.top, r.right, r.bottom];
              };
              const bar = document.querySelector('g[maidr] > path:not([data-maidr-owned])');
              const lit = document.querySelector('[id^=maidr-highlight]');
              return {bar: box(bar), lit: lit ? box(lit) : null};
            }"""
        )
    finally:
        page.close()

    assert boxes["lit"] is not None, "nothing is highlighted"
    assert boxes["lit"] == pytest.approx(boxes["bar"], abs=1)


def test_in_a_narrow_output_maidrs_fields_and_dialogs_stay_in_the_frame(
    browser, png_page
):
    page = _open(browser, png_page, frames=len(_SIZES))
    inside = """() => {
      const box = (e) => e ? e.getBoundingClientRect() : null;
      const view = {w: window.innerWidth, h: window.innerHeight};
      const parts = {
        text: box(document.querySelector('#maidr-text-container')),
        braille: box(document.querySelector('[id^=maidr-braille-textarea]')),
        review: box(document.querySelector('[id^=maidr-review-input]')),
        dialog: box(document.querySelector('.MuiDialog-paper')),
      };
      const out = {};
      for (const [name, r] of Object.entries(parts)) {
        out[name] = r && r.width > 0
          ? r.left >= -0.5 && r.top >= -0.5 && r.right <= view.w + 0.5
            && r.bottom <= view.h + 0.5
          : null;
      }
      return out;
    }"""
    seen = {}
    try:
        frame = _chart_frame(page, "narrow")
        for state, (opens, shown, closes) in {
            "braille": ("b", "[id^=maidr-braille-textarea]", "b"),
            "review": ("r", "[id^=maidr-review-input]", "r"),
            "help": ("Control+Slash", ".MuiDialog-paper", "Escape"),
            "settings": ("Control+Comma", ".MuiDialog-paper", "Escape"),
        }.items():
            frame.focus(_PLOT)
            page.keyboard.press("ArrowRight")
            # The chart has taken the key, and will take the next one.
            frame.wait_for_function(_ANNOUNCED, timeout=10_000)
            page.keyboard.press(opens)
            frame.wait_for_selector(shown, state="visible", timeout=10_000)
            # The frame is measured again a frame after it changes.
            page.wait_for_timeout(600)
            seen[state] = frame.evaluate(inside)
            page.keyboard.press(closes)
            frame.wait_for_selector(shown, state="detached", timeout=10_000)
        page.wait_for_timeout(600)
        seen["after"] = page.evaluate(_MEASURE, "narrow")
    finally:
        page.close()

    assert seen["braille"]["braille"] is True, seen["braille"]
    assert seen["braille"]["text"] is True, seen["braille"]
    assert seen["review"]["review"] is True, seen["review"]
    assert seen["help"]["dialog"] is True, seen["help"]
    assert seen["settings"]["dialog"] is True, seen["settings"]
    # The frame is back to the chart once the dialogs are closed.
    assert seen["after"]["frame"]["width"] == pytest.approx(320, abs=1)


# --- A notebook left idle, and scrolled ---------------------------------------

#: How many times the frames' sizes are set in ``ms`` milliseconds.
_STYLE_CHANGES = """async (ms) => {
  const frames = Array.from(document.querySelectorAll('iframe[data-maidr-chart]'));
  let changes = 0;
  const watch = new MutationObserver((records) => { changes += records.length; });
  for (const f of frames) watch.observe(f, {attributes: true, attributeFilter: ['style']});
  await new Promise((done) => setTimeout(done, ms));
  watch.disconnect();
  return changes;
}"""

#: Something in a chart's frame changes size, which measures the frame again.
_GROW = (
    "() => { const d = document.createElement('div');"
    " d.style.height = '1px'; document.body.appendChild(d); }"
)


def test_an_idle_notebook_leaves_its_frames_alone(browser, png_page):
    """A frame's own measuring resized its window, which measured it again.

    On every frame, for as long as the notebook was open: the notebook
    could not be scrolled for it, and every chart kept the browser busy.
    """
    page = _open(browser, png_page, frames=len(_SIZES))
    try:
        changes = page.evaluate(_STYLE_CHANGES, 1_000)
    finally:
        page.close()

    assert changes == 0


def test_a_frame_loaded_again_is_measured_again(browser, png_page):
    """A frame taken out of the page and put back loads its document again.

    That document was left with a resize listener and nothing else: no
    height, as maidr.js had not drawn the chart yet when it ran.
    """
    page = _open(browser, png_page, frames=len(_SIZES))
    size = "() => { const r = document.querySelector('#chart-small iframe')"
    size += ".getBoundingClientRect(); return [r.width, r.height]; }"
    try:
        before = page.evaluate(size)
        page.evaluate(
            "() => { const f = document.querySelector('#chart-small iframe');"
            " const p = f.parentElement; p.removeChild(f); p.appendChild(f); }"
        )
        _chart_frame(page, "small").wait_for_function(_BOUND, timeout=_PARSE_TIMEOUT_MS)
        page.wait_for_timeout(1_500)
        after = page.evaluate(size)
        changes = page.evaluate(_STYLE_CHANGES, 1_000)
    finally:
        page.close()

    assert after == pytest.approx(before, abs=1)
    assert changes == 0


def test_the_notebook_stays_where_it_is_scrolled(browser, png_page):
    """Measured at no height, a frame let the page clamp its scroll position.

    Near the end of a notebook, the page went back up each time the last
    chart was measured: as a reader scrolled down to it, and as its content
    changed while they read it.
    """
    page = _open(browser, png_page, frames=len(_SIZES))
    scrolled = "() => Math.round(window.scrollY)"
    try:
        bottom = page.evaluate(
            "() => { window.scrollTo(0, document.documentElement.scrollHeight);"
            " return Math.round(window.scrollY); }"
        )
        page.evaluate("(y) => window.scrollTo(0, y)", bottom - 300)
        page.wait_for_timeout(200)
        # Beside the outputs, which are 1100px wide.
        page.mouse.move(1_150, 450)
        wheeled = []
        for _ in range(3):
            page.mouse.wheel(0, 100)
            page.wait_for_timeout(300)
            wheeled.append(page.evaluate(scrolled))
        _chart_frame(page, "narrow").evaluate(_GROW)
        page.wait_for_timeout(300)
        after = page.evaluate(scrolled)
    finally:
        page.close()

    assert wheeled == [bottom - 200, bottom - 100, bottom]
    assert after == pytest.approx(bottom, abs=1)


def test_a_chart_above_the_readers_place_leaves_it_where_it_was(browser, png_page):
    """A frame above what the page shows grows: the browser keeps the reader's
    place by scrolling as far (scroll anchoring), which keeping the page's
    scroll position while the frame is measured must not undo."""
    page = _open(browser, png_page, frames=len(_SIZES))
    place = "() => document.querySelector('#chart-small').getBoundingClientRect().top"
    try:
        page.evaluate(
            "() => window.scrollTo(0, window.scrollY"
            " + document.querySelector('#chart-small').getBoundingClientRect().top"
            " - 100)"
        )
        page.wait_for_timeout(300)
        before = page.evaluate(place)
        _chart_frame(page, "default").evaluate(
            "() => { const d = document.createElement('div');"
            " d.style.height = '100px'; document.body.appendChild(d); }"
        )
        page.wait_for_timeout(500)
        after = page.evaluate(place)
    finally:
        page.close()

    assert before == pytest.approx(100, abs=1)
    assert after == pytest.approx(before, abs=1)


# --- maidr's dialogs: the part of the notebook a reader sees --------------------

_DIALOG_CASES = {
    # Narrower than a dialog: the frame widens to the output area.
    "narrow": (lambda: _figure(), 320),
    # Smaller than a dialog: the frame widens to one, 664px.
    "tiny": (lambda: _figure(size=(3, 2)), 1100),
    # Taller than the window: the dialog is kept to the window's height.
    "tall": (lambda: _figure(size=(6, 11)), 1100),
}

#: The open dialog, the frame and the output area, and the part of the
#: notebook a reader sees: the box it scrolls in, or the window.
_DIALOG = """(name) => {
  const output = document.querySelector(`#chart-${name}`);
  const frame = output.querySelector('iframe');
  const doc = frame.contentDocument;
  const f = frame.getBoundingClientRect();
  const paper = doc.querySelector('.MuiDialog-paper');
  const p = paper.getBoundingClientRect();
  const content = paper.querySelector('.MuiDialogContent-root');
  const box = document.querySelector('.scroller');
  const v = box ? box.getBoundingClientRect() : {top: 0, bottom: innerHeight};
  return {
    frame: {width: f.width, height: f.height},
    output: output.clientWidth,
    paper: {top: f.top + p.top, bottom: f.top + p.bottom,
            left: f.left + p.left, right: f.left + p.right, width: p.width},
    view: {top: Math.max(v.top, 0), bottom: Math.min(v.bottom, innerHeight),
           height: box ? box.clientHeight : innerHeight},
    contentScrolls: content ? content.scrollHeight > content.clientHeight + 1 : null,
  };
}"""

_FRAME_HEIGHT = (
    "(name) => document.querySelector(`#chart-${name} iframe`)"
    ".getBoundingClientRect().height"
)

_OPEN = {"help": "Control+Slash", "settings": "Control+Comma", "chat": "Shift+Slash"}


@pytest.fixture(scope="module")
def dialog_page(tmp_path_factory) -> str:
    return _notebook_page(tmp_path_factory.mktemp("dialogs"), _DIALOG_CASES)


@pytest.fixture(scope="module")
def scrolled_dialog_page(tmp_path_factory) -> str:
    """The outputs in a box 600px tall, as JupyterLab's notebook is."""
    return _notebook_page(
        tmp_path_factory.mktemp("scrolled"),
        {"tiny": _DIALOG_CASES["tiny"]},
        scroller=600,
    )


def _open_dialog(page: Page, name: str, dialog: str) -> tuple[Frame, float]:
    """Open one of maidr's dialogs; the frame, and its height before it opened."""
    frame = _chart_frame(page, name)
    frame.focus(_PLOT)
    page.keyboard.press("ArrowRight")
    frame.wait_for_function(_ANNOUNCED, timeout=10_000)
    page.wait_for_timeout(300)
    before = page.evaluate(_FRAME_HEIGHT, name)
    page.keyboard.press(_OPEN[dialog])
    frame.wait_for_selector(".MuiDialog-paper", state="visible", timeout=10_000)
    # Measured a frame after the dialog comes, and scrolled to.
    page.wait_for_timeout(700)
    return frame, before


def _close_dialog(page: Page, frame: Frame) -> None:
    page.keyboard.press("Escape")
    frame.wait_for_selector(".MuiDialog-root", state="detached", timeout=10_000)
    page.wait_for_timeout(400)


def _assert_in_view(seen: dict, what: str) -> None:
    paper, view = seen["paper"], seen["view"]
    assert (
        paper["top"] >= view["top"] - 0.5
    ), f"{what}: the dialog's top is {view['top'] - paper['top']:.0f}px out of view"
    assert paper["bottom"] <= view["bottom"] + 0.5, (
        f"{what}: the dialog's bottom is {paper['bottom'] - view['bottom']:.0f}px "
        "out of view"
    )
    assert paper["left"] >= -0.5 and paper["right"] <= 1_200.5, what


@pytest.mark.parametrize("dialog", ["help", "settings", "chat"])
@pytest.mark.parametrize("name", ["narrow", "tiny", "tall"])
def test_a_dialog_is_shown_whole_in_the_readers_view(
    browser, dialog_page, name, dialog
):
    page = _open(browser, dialog_page, frames=len(_DIALOG_CASES))
    try:
        frame, before = _open_dialog(page, name, dialog)
        seen = page.evaluate(_DIALOG, name)
        _close_dialog(page, frame)
        closed = page.evaluate(_FRAME_HEIGHT, name)
    finally:
        page.close()

    _assert_in_view(seen, f"{name} {dialog}")
    # As wide as a dialog, or as the output area where that is narrower.
    assert seen["frame"]["width"] == pytest.approx(min(664, seen["output"]), abs=1)
    # As tall as the reader's view, or as the chart where that is taller.
    assert seen["frame"]["height"] == pytest.approx(
        max(seen["view"]["height"], before), abs=1
    )
    if dialog == "settings":
        assert seen["contentScrolls"] is False, "the settings scroll in their dialog"
    # Back to the chart's height once it is closed.
    assert closed == pytest.approx(before, abs=1)


def test_a_dialog_is_shown_whole_in_the_box_the_notebook_scrolls_in(
    browser, scrolled_dialog_page
):
    page = _open(browser, scrolled_dialog_page, frames=1)
    try:
        frame, _ = _open_dialog(page, "tiny", "help")
        seen = page.evaluate(_DIALOG, "tiny")
        _close_dialog(page, frame)
    finally:
        page.close()

    # The box's height, not the window's.
    assert seen["view"]["height"] == 600
    assert seen["frame"]["height"] == pytest.approx(600, abs=1)
    _assert_in_view(seen, "help")


def test_the_settings_tabs_leave_the_frame_as_it_is(browser, dialog_page):
    """The frame was as tall as each tab, and moved the notebook at each."""
    page = _open(browser, dialog_page, frames=len(_DIALOG_CASES))
    heights = []
    try:
        frame, _ = _open_dialog(page, "tiny", "settings")
        tabs = frame.locator('[role="tab"]')
        assert tabs.count() > 1
        for i in range(tabs.count()):
            tabs.nth(i).focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(400)
            heights.append(page.evaluate(_DIALOG, "tiny")["frame"]["height"])
        _close_dialog(page, frame)
    finally:
        page.close()

    assert max(heights) - min(heights) <= 1, heights


_FRAME_TOP = (
    "(name) => [window.scrollY, document.querySelector(`#chart-${name} iframe`)"
    ".getBoundingClientRect().toJSON()]"
)


@pytest.mark.parametrize("resized", [None, (640, 450)], ids=["same", "zoomed"])
def test_closing_a_dialog_leaves_the_notebook_where_the_reader_had_it(
    browser, dialog_page, resized
):
    """The notebook is scrolled to centre help; it goes back once help goes.

    Left where help had been, the reader's place was lost. Put back after
    the window changed size while help was open (the browser zoomed to
    200%), the offsets measured in the old layout put the chart wholly off
    screen; the chart is shown instead.
    """
    page = _open(browser, dialog_page, frames=len(_DIALOG_CASES))
    try:
        frame = _chart_frame(page, "tiny")
        frame.focus(_PLOT)
        page.keyboard.press("ArrowRight")
        frame.wait_for_function(_ANNOUNCED, timeout=10_000)
        page.evaluate(
            "() => document.querySelector('#chart-tiny iframe')"
            ".scrollIntoView({block: 'end', behavior: 'instant'})"
        )
        page.wait_for_timeout(500)
        before, _ = page.evaluate(_FRAME_TOP, "tiny")
        page.keyboard.press(_OPEN["help"])
        frame.wait_for_selector(".MuiDialog-paper", state="visible", timeout=10_000)
        page.wait_for_timeout(700)
        opened, _ = page.evaluate(_FRAME_TOP, "tiny")
        if resized:
            page.set_viewport_size({"width": resized[0], "height": resized[1]})
            page.wait_for_timeout(1_000)
        _close_dialog(page, frame)
        page.wait_for_timeout(400)
        after, rect = page.evaluate(_FRAME_TOP, "tiny")
        height = page.evaluate("() => window.innerHeight")
    finally:
        page.close()

    assert opened != pytest.approx(before, abs=50), "help moved nothing"
    if resized:
        assert rect["top"] >= -1 and rect["bottom"] <= height + 1, (rect, height)
    else:
        assert after == pytest.approx(before, abs=1), (before, opened, after)


# --- Plotly, Bokeh and Altair in the same frame -------------------------------

_PLOTLY_CDN = re.compile(r"^https://cdn\.plot\.ly/plotly-[^/]+\.min\.js$")
_BOKEH_CDN = re.compile(
    r"^https://cdn\.bokeh\.org/bokeh/release/(bokeh[a-z-]*)-[^/]+\.min\.js$"
)


def _library_page(tmp_path: Path, charts: dict[str, tuple[Any, int]]) -> str:
    """Each chart in an output area of its own width, as a notebook shows it."""
    source = json.dumps(maidr.read_bundled_js()).replace("</", "<\\/")
    outputs = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Environment, "is_notebook", staticmethod(lambda: True))
        for name, (chart, width) in charts.items():
            html = str(maidr.render(chart, use_cdn=False))
            outputs.append(
                f'<div class="output html" id="chart-{name}" '
                f'style="width: {width}px">{html}</div>'
            )
    out = tmp_path / "notebook.html"
    out.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_PAGE_STYLE}</style></head><body>"
        f"<script>window.__maidrJsSource = {source};</script>"
        f"{''.join(outputs)}</body></html>",
        encoding="utf-8",
    )
    return out.as_uri()


def _serve_locally(page: Page) -> None:
    """plotly.js and BokehJS from the installed packages, nothing from a network."""
    import bokeh
    import plotly

    plotly_js = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    bokeh_js = Path(bokeh.__file__).parent / "server" / "static" / "js"
    page.route(
        _PLOTLY_CDN,
        lambda route: route.fulfill(
            path=str(plotly_js), content_type="application/javascript"
        ),
    )
    page.route(
        _BOKEH_CDN,
        lambda route: route.fulfill(
            path=str(bokeh_js / f"{_BOKEH_CDN.match(route.request.url)[1]}.min.js"),
            content_type="application/javascript",
        ),
    )


#: The chart's frame, what is drawn in it, and the output area around it.
_LIBRARY = """([name, drawn]) => {
  const box = (r) => ({x: r.x, y: r.y, width: r.width, height: r.height});
  const output = document.querySelector(`#chart-${name}`);
  const frame = output.querySelector('iframe');
  const doc = frame.contentDocument;
  const marks = doc.querySelector(drawn);
  return {
    frame: box(frame.getBoundingClientRect()),
    view: {width: frame.clientWidth, height: frame.clientHeight},
    drawn: marks ? box(marks.getBoundingClientRect()) : null,
    outputScrolls: output.scrollWidth > output.clientWidth + 1,
  };
}"""


def _settle(page: Page, names: list[str], drawn: str) -> None:
    for name in names:
        frame = page.query_selector(f"#chart-{name} iframe").content_frame()
        frame.wait_for_function(_BOUND, timeout=_PARSE_TIMEOUT_MS)
        frame.wait_for_selector(drawn, timeout=_PARSE_TIMEOUT_MS)
    # The plotly frame is measured again 0.5s, 1.5s and 3s after it loads.
    page.wait_for_timeout(3_500)


#: Scroll an output area to its right end; where it is a moment later, and
#: once its chart has been measured again.
_SCROLL_ACROSS = """async ([name, grow]) => {
  const output = document.querySelector(`#chart-${name}`);
  const frame = output.querySelector('iframe');
  const end = output.scrollWidth - output.clientWidth;
  output.scrollLeft = end;
  for (let i = 0; i < 6; i++) await new Promise((done) => requestAnimationFrame(done));
  const later = output.scrollLeft;
  frame.contentWindow.eval(`(${grow})()`);
  await new Promise((done) => setTimeout(done, 300));
  return {end, later, measured: output.scrollLeft};
}"""


def _assert_stays_scrolled(page: Page, name: str, *, keys: bool = False) -> None:
    """A frame measured at the output area's width scrolled it back to its start.

    With ``keys``, the reader then moves into the chart and through it, which
    measures the frame again too. Not for a Plotly chart: there maidr.js's
    focusable element is a 0x0 box at the chart's left edge, which the browser
    scrolls to as it takes the focus.
    """
    seen = page.evaluate(_SCROLL_ACROSS, [name, _GROW])
    assert seen["end"] > 0, f"{name}: the output area does not scroll"
    assert seen["later"] == seen["end"], f"{name}: {seen}"
    assert seen["measured"] == seen["end"], f"{name}: {seen}"
    if keys:
        frame = _chart_frame(page, name)
        frame.focus(_PLOT)
        page.keyboard.press("ArrowRight")
        frame.wait_for_function(_ANNOUNCED, timeout=10_000)
        page.wait_for_timeout(400)
        left = page.evaluate(
            "(name) => document.querySelector(`#chart-${name}`).scrollLeft", name
        )
        assert left == seen["end"], f"{name}: moved to {left} from {seen['end']}"


#: Where maidr's text line lies in its frame once the chart has announced
#: a point: [its bottom, the frame's height].
_TEXT_LINE = """() => {
  const text = document.querySelector('#maidr-text-container');
  return [text.getBoundingClientRect().bottom, window.innerHeight];
}"""


def _assert_text_in_frame(page: Page, name: str) -> None:
    """maidr's text line, below a Plotly or Bokeh chart's body, is in its frame.

    Nothing measured the frame again as the text came, once the frame no
    longer measured itself on every frame.
    """
    frame = _chart_frame(page, name)
    frame.focus(_PLOT)
    page.keyboard.press("ArrowRight")
    frame.wait_for_function(_ANNOUNCED, timeout=10_000)
    page.wait_for_timeout(400)
    bottom, height = frame.evaluate(_TEXT_LINE)
    assert (
        bottom <= height + 0.5
    ), f"{name}: maidr's text runs {bottom - height:.0f}px past the frame"


def _assert_whole(seen: dict, name: str) -> None:
    drawn, view = seen["drawn"], seen["view"]
    assert drawn is not None, f"{name}: nothing was drawn"
    assert drawn["x"] >= -0.5 and drawn["y"] >= -0.5, f"{name}: {seen}"
    assert drawn["x"] + drawn["width"] <= view["width"] + 0.5, (
        f"{name}: the chart runs {drawn['x'] + drawn['width'] - view['width']:.0f}"
        "px past the frame's right edge"
    )
    assert drawn["y"] + drawn["height"] <= view["height"] + 0.5, (
        f"{name}: the chart runs {drawn['y'] + drawn['height'] - view['height']:.0f}"
        "px past the frame's bottom edge"
    )


def test_plotly_charts_are_whole_and_as_tall_as_the_notebook_draws_them(
    browser, tmp_path, monkeypatch
):
    go = pytest.importorskip("plotly.graph_objects")
    pio = pytest.importorskip("plotly.io")
    monkeypatch.setattr(pio.renderers, "default", "plotly_mimetype+notebook")

    def bar(**layout):
        fig = go.Figure(go.Bar(x=["Q1", "Q2", "Q3", "Q4"], y=[5, 7, 3, 8]))
        return fig.update_layout(**layout)

    charts = {"auto": (bar(), 700), "wide": (bar(width=1200, height=400), 600)}
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    try:
        _serve_locally(page)
        page.goto(_library_page(tmp_path, charts), wait_until="load")
        _settle(page, list(charts), "svg.main-svg")
        seen = {
            name: page.evaluate(_LIBRARY, [name, "svg.main-svg"]) for name in charts
        }
        idle = page.evaluate(_STYLE_CHANGES, 1_000)
        _assert_stays_scrolled(page, "wide")
        _assert_text_in_frame(page, "auto")
    finally:
        page.close()

    assert idle == 0, "the frames measure themselves again with nothing changed"

    for name in charts:
        _assert_whole(seen[name], name)
    # JupyterLab's renderer draws a figure without a height 360px tall.
    assert seen["auto"]["drawn"]["height"] == pytest.approx(360, abs=1)
    assert seen["auto"]["drawn"]["width"] == pytest.approx(700, abs=1)
    # Wider than its output area: the frame widens and the output area
    # scrolls to it, as it does to the plain chart.
    assert seen["wide"]["drawn"]["width"] == pytest.approx(1200, abs=1)
    assert seen["wide"]["outputScrolls"]


def test_bokeh_charts_are_whole_and_a_stretched_one_fills_the_frame(browser, tmp_path):
    plotting = pytest.importorskip("bokeh.plotting")

    def bar(**kwargs):
        fig = plotting.figure(x_range=["Q1", "Q2", "Q3", "Q4"], **kwargs)
        fig.vbar(x=["Q1", "Q2", "Q3", "Q4"], top=[5, 7, 3, 8], width=0.8)
        fig.xaxis.axis_label = "Quarter"
        return fig

    charts = {
        "fixed": (bar(width=400, height=300), 700),
        "wide": (bar(width=1100, height=300), 600),
        "stretched": (bar(sizing_mode="stretch_width", height=300), 700),
    }
    drawn = ".bk-Canvas, .bk-Figure, canvas"
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    try:
        _serve_locally(page)
        page.goto(_library_page(tmp_path, charts), wait_until="load")
        _settle(page, list(charts), drawn)
        seen = {name: page.evaluate(_LIBRARY, [name, drawn]) for name in charts}
        idle = page.evaluate(_STYLE_CHANGES, 1_000)
        _assert_stays_scrolled(page, "wide", keys=True)
        _assert_text_in_frame(page, "fixed")
    finally:
        page.close()

    assert idle == 0, "the frames measure themselves again with nothing changed"
    for name in charts:
        _assert_whole(seen[name], name)
    assert seen["fixed"]["drawn"]["width"] == pytest.approx(400, abs=1)
    assert seen["wide"]["outputScrolls"]
    # As wide as the frame, not the 73px it collapsed to.
    assert seen["stretched"]["drawn"]["width"] == pytest.approx(
        seen["stretched"]["view"]["width"], abs=2
    )


_VEGA = (
    "https://cdn.jsdelivr.net/npm/vega@5",
    "https://cdn.jsdelivr.net/npm/vega-lite@5",
    "https://cdn.jsdelivr.net/npm/vega-embed@6",
)


def _fulfil_with(body: bytes) -> Callable[[Any], None]:
    """A route handler answering with ``body``, a script."""

    def fulfil(route) -> None:
        route.fulfill(body=body, content_type="application/javascript")

    return fulfil


def test_an_altair_chart_of_the_containers_width_fills_the_frame(browser, tmp_path):
    alt = pytest.importorskip("altair")
    pd = pytest.importorskip("pandas")
    from maidr.util.cdn import cdn_url
    from maidr.util.dependencies import MAIDR_VEGALITE_FILENAME

    adapter = cdn_url(MAIDR_VEGALITE_FILENAME)
    scripts = {}
    for url in (*_VEGA, adapter):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
                scripts[url] = response.read()
        except OSError as error:
            pytest.skip(f"Vega could not be fetched: {error}")

    data = pd.DataFrame({"q": ["Q1", "Q2", "Q3", "Q4"], "units": [5, 7, 3, 8]})
    chart = (
        alt.Chart(data)
        .mark_bar()
        .encode(x="q", y="units")
        .properties(width="container", height=300)
    )
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    try:
        for url, body in scripts.items():
            page.route(url, _fulfil_with(body))
        page.goto(
            _library_page(tmp_path, {"container": (chart, 700)}), wait_until="load"
        )
        _settle(page, ["container"], "svg.marks, canvas.marks")
        seen = page.evaluate(_LIBRARY, ["container", "svg.marks, canvas.marks"])
        bars = (
            page.query_selector("#chart-container iframe")
            .content_frame()
            .evaluate("() => document.querySelectorAll('.mark-rect path').length")
        )
    finally:
        page.close()

    _assert_whole(seen, "container")
    # As wide as the frame, where it grew without end and drew no bars.
    assert seen["drawn"]["width"] <= seen["view"]["width"] + 0.5
    assert seen["drawn"]["width"] >= seen["view"]["width"] * 0.8
    assert bars == 4
