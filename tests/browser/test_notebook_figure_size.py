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
* the highlight lands on the mark it names.

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
    tmp_path: Path, cases: dict[str, tuple[Callable[[], Any], int]], **config: Any
) -> str:
    """A notebook's outputs: each figure's plain image, then its chart.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Where to write the page.
    cases : dict
        ``name -> (make the figure, the output area's width)``.
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
    out = tmp_path / "notebook.html"
    out.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_PAGE_STYLE}</style></head><body>"
        f"<script>window.__maidrJsSource = {source};</script>"
        f"{''.join(outputs)}</body></html>",
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
    finally:
        page.close()

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
    finally:
        page.close()

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
