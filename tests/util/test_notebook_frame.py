"""A chart's frame in a notebook holds it as the output area holds an image.

The frame's document gets ``maidr/assets/frame.css``: the margins a browser
gives a document and a ``<figure>`` are reset, so the chart starts at the
frame's edge as the image starts at the output area's; the chart shrinks
with a narrow output area, keeping its shape; focus rings are drawn inside
the frame, whose edge is now the chart's; and a chart sized by its container
fills the frame. Its script makes the frame as wide as the output area up to
the chart's own width, and makes room for maidr's dialogs.

Elsewhere -- Shiny, Flask, a Pyodide page -- the frame is left as it was.
What a browser makes of it is ``tests/browser/test_notebook_figure_size.py``.
"""

from __future__ import annotations

import html as html_module
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from htmltools import tags  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402
from maidr.util.iframe_utils import (  # noqa: E402
    FRAME_SVG_CLASS,
    frame_style,
    wrap_in_iframe_matplotlib,
)
from maidr.util.inline_chart import _asset  # noqa: E402


def _rules(css: str) -> dict[str, dict[str, str]]:
    """``selector -> {property: value}``, a selector list split into its parts."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@media[^{]*\{((?:[^{}]*\{[^{}]*\})*)\s*\}", "", css)
    rules: dict[str, dict[str, str]] = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        declarations = dict(
            (part.split(":", 1)[0].strip(), part.split(":", 1)[1].strip())
            for part in body.split(";")
            if ":" in part
        )
        for selector in selectors.split(","):
            rules.setdefault(" ".join(selector.split()), {}).update(declarations)
    return rules


def _attribute(tag, name: str) -> str:
    return str(tag.attrs[name])


@pytest.fixture
def css() -> dict[str, dict[str, str]]:
    return _rules(_asset("frame.css"))


# --- The stylesheet -------------------------------------------------------------


def test_the_chart_starts_at_the_frames_edge(css):
    for selector in ("html", "body"):
        assert css[selector]["margin"] == "0"
    for selector in ('article[id^="maidr-article-"]', 'figure[id^="maidr-figure-"]'):
        assert css[selector]["margin"] == "0"


def test_the_chart_shrinks_with_the_frame_and_keeps_its_shape(css):
    rule = css[f"svg.{FRAME_SVG_CLASS}"]

    assert rule == {"display": "block", "max-width": "100%", "height": "auto"}


def test_focus_rings_are_drawn_inside_the_frame(css):
    chart = css['figure[id^="maidr-figure"] > div[tabindex="0"]:focus']
    field = css["textarea:focus"]

    for rule in (chart, field):
        assert rule["outline-offset"].startswith("-")
        assert rule["outline"].startswith("3px solid")


def test_maidrs_fields_keep_to_the_frame(css):
    for selector in (
        'textarea[id^="maidr-braille-textarea"]',
        'input[id^="maidr-review-input"]',
    ):
        assert css[selector] == {"max-width": "100%", "box-sizing": "border-box"}


def test_the_stylesheet_is_one_style_element():
    style = frame_style()

    assert style.startswith("<style>") and style.endswith("</style>")
    assert style.count("<") == 2, "nothing in the stylesheet may end the element"
    assert "/*" not in style


# --- The matplotlib frame -------------------------------------------------------------


def _frame(**kwargs):
    return wrap_in_iframe_matplotlib(tags.div(tags.p("chart")), "Sales", **kwargs)


def test_a_notebook_frame_carries_the_stylesheet_first():
    srcdoc = _attribute(_frame(in_notebook=True), "srcdoc")

    assert srcdoc.startswith(frame_style())
    assert "<p>chart</p>" in srcdoc


def test_a_notebook_frame_fits_the_output_area():
    script = _attribute(_frame(in_notebook=True), "onload")

    assert "let fitsOutput = true;" in script
    assert f"svg.{FRAME_SVG_CLASS}" in script
    # As wide as the output area, its end padding included, up to the
    # chart's own width.
    assert "iframe.style.width = maidrOutputWidth(iframe, false);" in script
    assert "'calc(100% + ' + pad + 'px)'" in script
    assert "iframe.style.marginRight = pad > 0 ? (-pad) + 'px' : '';" in script
    assert "iframe.style.maxWidth" in script
    # Measured again as the frame's width and its content change.
    assert "addEventListener('resize', scheduleResize)" in script
    assert "childList: true }" in script
    # Room for maidr's dialogs.
    assert "maidrDialogRoom(iframeDocument, window)" in script


def test_any_other_frame_is_left_as_it_was():
    frame = _frame()

    assert not _attribute(frame, "srcdoc").startswith("<style>")
    assert "let fitsOutput = false;" in _attribute(frame, "onload")


def test_a_hostile_title_still_arrives_as_text():
    frame = wrap_in_iframe_matplotlib(
        tags.div("x"), "</iframe><script>alert(1)</script>", in_notebook=True
    )

    assert "<script>alert" not in str(frame).split("srcdoc=")[0]


# --- Through a render ---------------------------------------------------------------


def _bar():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(["a", "b"], [1, 2])
    return fig


def _render(fig) -> str:
    try:
        return str(FigureManager.get_maidr(fig).render())
    finally:
        plt.close(fig)


def test_a_notebook_render_is_framed_for_the_output_area(monkeypatch):
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))

    raw = _render(_bar())
    html = html_module.unescape(raw)

    assert 'srcdoc="&lt;style&gt;' in raw

    assert html.count(".maidr-frame-svg") >= 1
    assert re.search(rf'<svg[^>]*class="{FRAME_SVG_CLASS}"', html)
    assert "let fitsOutput = true;" in html


@pytest.mark.parametrize("host", ["is_shiny", "is_flask"])
def test_an_apps_frame_is_left_as_it_was(monkeypatch, host):
    monkeypatch.setattr(Environment, host, staticmethod(lambda: True))

    html = html_module.unescape(_render(_bar()))

    assert "let fitsOutput = false;" in html
    assert not re.search(rf'<svg[^>]*class="{FRAME_SVG_CLASS}"', html)
    assert 'srcdoc="&lt;style&gt;' not in _render(_bar())
