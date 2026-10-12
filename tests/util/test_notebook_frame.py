"""A chart's frame in a notebook holds it as the output area holds an image.

The frame's document gets ``maidr/assets/frame.css``: the margins a browser
gives a document and a ``<figure>`` are reset, so the chart starts at the
frame's edge as the image starts at the output area's; the chart shrinks
with a narrow output area, keeping its shape; focus rings are drawn inside
the frame, whose edge is now the chart's; and a chart sized by its container
fills the frame. Its script makes the frame as wide as the output area up to
the chart's own width, measures it again only when its width or its content
changes, keeps the notebook where it is scrolled while it measures it, and
makes room for maidr's dialogs.

A Shiny app's frame fits its output the same way, without the padding a
notebook keeps to an output's right, and fits the chart to a box with a height
of its own (``tests/browser/test_shiny_chart_size.py``). Elsewhere -- Flask,
a Pyodide page -- the frame is left as it was. What a browser makes of a
notebook's is ``tests/browser/test_notebook_figure_size.py``.
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
    wrap_in_iframe_plotly,
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


def test_a_chart_sized_by_its_container_fills_the_frame(css):
    assert css['.maidr-frame-fill figure[id^="maidr-figure-"] > div[tabindex]'] == {
        "width": "auto !important"
    }
    assert css['.maidr-frame-fill [id^="maidr-altair-"]'] == {
        "display": "block",
        "width": "100%",
    }


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
    # chart's own width; never fitted to a box, which only Shiny's has.
    assert "let keepsPadding = false;" in script
    assert "let fitsBox = false;" in script
    assert "iframe.style.width = maidrOutputWidth(iframe, keepsPadding);" in script
    assert "'calc(100% + ' + pad + 'px)'" in script
    assert "iframe.style.marginRight = pad > 0 ? (-pad) + 'px' : '';" in script
    assert "iframe.style.maxWidth" in script
    # Until maidr.js has put the chart back, as wide as the output area, not
    # narrowed to nothing.
    assert "}} else if (fitsOutput) {{" not in script
    assert "} else if (fitsOutput) {" in script


def test_a_notebook_frame_is_measured_again_only_when_something_changed():
    """Its own measuring resized its window, which measured it again, forever."""
    script = _attribute(_frame(in_notebook=True), "onload")

    assert "addEventListener('resize', scheduleResize)" not in script
    assert "addEventListener('resize', resizeIframe)" not in script
    assert "if (width !== lastWidth) {" in script
    # A frame out of view, or hidden, keeps its height until it has a width.
    assert "if (fitsOutput && maidrNotLaidOut(iframe)) return;" in script
    # The chart maidr.js puts back as it draws it, which a frame out of view
    # hears of from nothing else.
    assert "chartBack.disconnect();" in script


def test_a_frame_keeps_the_notebook_where_it_is_scrolled():
    for frame in (
        _frame(in_notebook=True),
        wrap_in_iframe_plotly(tags.div("chart"), "Sales", in_notebook=True),
    ):
        script = _attribute(frame, "onload")
        # Kept before the frame is measured, and put back once it is.
        kept = script.index("fitsOutput ? maidrKeepScroll(iframe) : null;")
        measured = script.index("iframe.style.height = fitsOutput ? '0px' : 'auto';")
        restored = script.index("if (restoreScroll) restoreScroll();")
        assert kept < measured < restored


def test_a_notebook_frame_makes_room_for_maidrs_dialogs():
    script = _attribute(_frame(in_notebook=True), "onload")

    assert "maidrDialogRoom(iframeDocument, iframe)" in script
    assert "maidrWatch(iframe.contentWindow.document, scheduleResize)" in script
    assert "iframe.scrollIntoView({block: 'center', inline: 'nearest'})" in script


def test_a_dialog_over_a_tall_chart_keeps_to_the_readers_view(css):
    band = "html[data-maidr-dialog-room]"
    assert css[f"{band} .MuiDialog-container"] == {
        "height": "var(--maidr-dialog-room) !important",
        "margin-top": "calc((100vh - var(--maidr-dialog-room)) / 2) !important",
    }
    assert css[f"{band} .MuiDialog-paper"] == {
        "max-height": "calc(var(--maidr-dialog-room) - 64px) !important"
    }


def test_any_other_frame_is_left_as_it_was():
    frame = _frame()

    assert not _attribute(frame, "srcdoc").startswith("<style>")
    assert "let fitsOutput = false;" in _attribute(frame, "onload")


def test_a_hostile_title_still_arrives_as_text():
    frame = wrap_in_iframe_matplotlib(
        tags.div("x"), "</iframe><script>alert(1)</script>", in_notebook=True
    )

    assert "<script>alert" not in str(frame).split("srcdoc=")[0]


# --- The plotly frame (Bokeh and Altair use it too) -----------------------------------


def test_a_notebook_plotly_frame_carries_the_stylesheet():
    frame = wrap_in_iframe_plotly(tags.div("chart"), "Sales", in_notebook=True)

    srcdoc = _attribute(frame, "srcdoc")
    assert srcdoc.startswith(frame_style())
    # The frame takes its width before plotly.js draws in it, which keeps
    # the width it drew at.
    assert srcdoc.index("window.frameElement") < srcdoc.index("chart")
    script = _attribute(frame, "onload")
    assert "var fitsOutput = true;" in script
    assert "var keepsPadding = false;" in script
    assert "iframe.style.width = maidrOutputWidth(iframe, keepsPadding);" in script
    # The document's own height, which counts margins body.scrollHeight
    # leaves out, and a frame widened to content wider than the output area.
    assert "de.scrollHeight" in script
    assert "iframe.style.width = de.scrollWidth + 'px'" in script
    # Given the output area's width again only when that has changed.
    assert "if (iframe.maidrHostWidth !== hostWidth) {" in script
    assert "maidrWatch(iframe.contentWindow.document, scheduleResize)" in script


def test_any_plotly_frame_is_measured_again_only_when_its_width_changes():
    """Its height is set as it is measured, which resized its window."""
    for in_notebook in (True, False):
        frame = wrap_in_iframe_plotly(
            tags.div("chart"), "Sales", in_notebook=in_notebook
        )
        script = _attribute(frame, "onload")
        assert "addEventListener('resize', resizeIframe)" not in script
        assert "if (width !== lastWidth) {" in script


def test_a_frame_can_keep_clear_of_the_output_areas_padding():
    """As a Bokeh plot, an HTML output itself, keeps clear of it."""
    frame = wrap_in_iframe_plotly(
        tags.div("chart"), "Sales", in_notebook=True, keep_padding=True
    )

    assert "window.frameElement" not in _attribute(frame, "srcdoc")
    assert "var keepsPadding = true;" in _attribute(frame, "onload")


def test_a_chart_sized_by_its_container_is_marked_in_a_notebook():
    frame = wrap_in_iframe_plotly(
        tags.div("chart"), "Sales", in_notebook=True, fill_width=True
    )

    assert 'class="maidr-frame-fill"' in _attribute(frame, "srcdoc")


def test_outside_a_notebook_the_plotly_frame_is_left_as_it_was():
    frame = wrap_in_iframe_plotly(tags.div("chart"), "Sales", fill_width=True)

    srcdoc = _attribute(frame, "srcdoc")
    assert not srcdoc.startswith("<style>")
    assert "maidr-frame-fill" not in srcdoc
    assert "var fitsOutput = false;" in _attribute(frame, "onload")


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


def test_a_flask_apps_frame_is_left_as_it_was(monkeypatch):
    monkeypatch.setattr(Environment, "is_flask", staticmethod(lambda: True))

    html = html_module.unescape(_render(_bar()))

    assert "let fitsOutput = false;" in html
    assert not re.search(rf'<svg[^>]*class="{FRAME_SVG_CLASS}"', html)
    assert 'srcdoc="&lt;style&gt;' not in _render(_bar())


def test_a_shiny_apps_frame_fits_its_output(monkeypatch):
    """Shiny's frame fits its output as a notebook's does, and its box too."""
    monkeypatch.setattr(Environment, "is_shiny", staticmethod(lambda: True))

    raw = _render(_bar())
    html = html_module.unescape(raw)

    assert 'srcdoc="&lt;style&gt;' in raw
    assert re.search(rf'<svg[^>]*class="{FRAME_SVG_CLASS}"', html)
    assert "let fitsOutput = true;" in html
    # No padding to take back, as a notebook's output area has.
    assert "let keepsPadding = true;" in html
    assert "let fitsBox = true;" in html
    assert "maidrWatchBox(iframe, scheduleResize);" in html
    assert "display: block" in html


def test_a_shiny_frame_fits_the_chart_to_a_box_with_a_height():
    """Fitted as object-fit: contain fits an image, a line kept for the text."""
    script = _attribute(_frame(in_shiny=True), "onload")

    for part in (
        "function maidrBoxRoom(iframe)",
        "iframe.style.height = '4000px';",
        "Math.abs(tall - short) >= 1",
        "var scale = Math.min(width / w, Math.max(space, 96) / h);",
        "var space = room - maidrTextLine(doc);",
        "root.setAttribute('data-maidr-fit-box', '');",
    ):
        assert part in script, part
    # Fitted, the frame is as wide as the box; left to its own height, no
    # wider than the chart.
    assert "iframe.style.maxWidth = boxRoom > 0" in script
    # A notebook's frame has none of it.
    assert "function maidrBoxRoom" not in _attribute(_frame(in_notebook=True), "onload")


def test_a_shiny_frames_script_is_compact_but_whole():
    """Sent with every flush, so without comments; the same script otherwise."""
    shiny = _attribute(_frame(in_shiny=True), "onload")
    notebook = _attribute(_frame(in_notebook=True), "onload")

    assert "//" not in shiny
    assert "\n            " not in shiny
    assert len(shiny) < len(notebook)
    for statement in ("resizeIframe();", "maidrShowField(iframeDocument, resized);"):
        assert statement in shiny
