"""Tests for the Shiny integration in ``maidr.widget.shiny``.

These drive the renderer the way Shiny does -- ``_render(renderer)``
inside a session context -- without starting a server.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import sys
import threading
import time
import warnings
from html import unescape
from urllib.parse import unquote

import matplotlib
import pytest
from packaging.version import Version

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

shiny = pytest.importorskip("shiny")

from shiny import module  # noqa: E402
from shiny.render import ui as render_ui  # noqa: E402
from shiny.render.renderer import Renderer  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.dependencies import maidr_js_version, read_bundled_js  # noqa: E402
from maidr.util.iframe_utils import (  # noqa: E402
    SHINY_FRAME_NAME,
    _shiny_frame_css,
    _shiny_frame_version,
    shiny_frame_script,
)
from maidr.util.locale_pack import get_locale_base_url  # noqa: E402
from maidr.util.served_bundle import SERVED_BUNDLE_NAME  # noqa: E402
from maidr.widget.shiny import output_maidr, render_maidr  # noqa: E402

from .conftest import _fake_session_class  # noqa: E402

#: A slice of the real bundle, so "is the bundle inlined?" is answered by
#: looking for the bundle rather than by a size threshold that a large
#: enough chart could cross on its own.
_BUNDLE_HEAD = read_bundled_js()[:200]

#: The tail of the URL a chart document names the served bundle by (#457),
#: from the app root. What precedes it is the climb from the document's
#: route back to that root, which ``test_the_served_bundle_resolves_...``
#: checks separately.
_SERVED_JS = f"lib/maidr-bundle-{maidr_js_version()}/maidr.js"


def _bar_axes():
    """Return the axes of a freshly created two-bar chart."""
    _, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    return ax


def _render(renderer):
    """Drive a renderer the way Shiny does.

    ``asyncio.run`` copies the current context, so the session installed by
    the ``fake_session`` fixture is visible inside the coroutine.  The
    suite already uses this shape in ``tests/core/test_cdn_event_loop.py``
    rather than taking on a pytest-asyncio dependency.
    """
    return asyncio.run(renderer.render())


#: The frame's ``src``: a session route, its nonce, and the render's version.
_FRAME_SRC = re.compile(r'src="session/[^/]+/dynamic_route/([^?"]+)\?([^"]*)"')


def _fetch(session, html: str, *, version: str | None = None):
    """Fetch the chart document a payload's frame points at, as the browser does.

    The frame names a session route; the handler Shiny registered there is
    called with a request for that URL -- the same call Shiny's request
    handler makes -- and its response is returned whole, so a test can
    read the headers as well as the body. ``version`` substitutes another
    ``v`` for the one the frame carries.
    """
    from starlette.requests import Request

    match = _FRAME_SRC.search(html)
    assert match, "the frame does not point at a session route"
    # The name is percent-encoded in the URL and decoded by the server
    # before the lookup, so the same happens here.
    name, query = unquote(unescape(match.group(1))), unescape(match.group(2))
    if version is not None:
        query = re.sub(r"v=\d+", f"v={version}", query)
    request = Request(
        {"type": "http", "method": "GET", "headers": [], "query_string": query.encode()}
    )
    return session._dynamic_routes[name](request)


def _iframe_document(session, html: str) -> str:
    """Return the chart document a payload's frame is served, or the payload itself."""
    if not _FRAME_SRC.search(html):
        return html
    return _fetch(session, html).body.decode()


@pytest.fixture(autouse=True)
def _clean_figures():
    """Leave no figures or FigureManager entries behind between tests."""
    plt.close("all")
    FigureManager.figs.clear()
    yield
    plt.close("all")
    FigureManager.figs.clear()


# ---------------------------------------------------------------------------
# Renderer contract
# ---------------------------------------------------------------------------


def carried_script(onload: str) -> str:
    """The script a string frame's ``onload`` carries."""
    return re.match(r"var f=this;(.*)maidrShinyFrame\(f,", onload, re.S).group(1)


def test_render_maidr_subclasses_renderer_not_a_concrete_renderer():
    """The documented base is ``Renderer``, not another renderer."""
    assert Renderer in render_maidr.__mro__
    assert render_ui not in render_maidr.__mro__


def test_render_maidr_implements_render_and_leaves_transform_alone():
    """``render`` is overridden; ``transform`` is not, so only one is in play."""
    assert "render" in render_maidr.__dict__
    assert "transform" not in render_maidr.__dict__


def test_bare_and_parenthesised_decoration_both_register(fake_session):
    """Both decorator spellings produce a registered renderer."""

    @render_maidr
    def bare():
        return _bar_axes()

    @render_maidr()
    def parenthesised():
        return _bar_axes()

    assert bare.output_id == "bare"
    assert parenthesised.output_id == "parenthesised"
    assert fake_session.outputs == [bare, parenthesised]


def test_options_are_accepted(fake_session):
    """The renderer takes options; previously any keyword was a TypeError."""

    @render_maidr(width="42px", height="7em", use_cdn=True)
    def sized():
        return _bar_axes()

    assert (sized.width, sized.height, sized.use_cdn) == ("42px", "7em", True)


def test_auto_output_ui_delegates_to_output_maidr(fake_session):
    """Express mode places ``output_maidr``'s container.

    The renderer's size is its chart's box's, not the container's, as
    ``render.plot``'s is its image's; see
    ``test_express_gives_the_box_the_renderers_size``.
    """

    @render_maidr(width="42px", height="7em")
    def sized():
        return _bar_axes()

    container = sized.auto_output_ui()
    assert 'id="sized"' in str(container)
    assert (_style(container)["width"], _style(container)["height"]) == (
        "100%",
        "auto",
    )


def test_output_args_reaches_the_container(fake_session):
    """``@output_args`` is Shiny's documented way to size an Express output.

    Shiny splats it into ``auto_output_ui``, so a renderer that takes no
    keywords there raises ``TypeError`` -- which is what this one did, and
    is why ``shiny.render.plot`` accepts ``**kwargs``.  Driven through
    ``_render_auto_output_ui`` rather than ``auto_output_ui`` directly,
    since that splat is the step being tested.
    """
    from shiny.express import output_args

    @output_args(width="50%")
    @render_maidr(width="42px", height="7em")
    def sized():
        return _bar_axes()

    rendered = str(sized._render_auto_output_ui())
    assert "width: 50%" in rendered
    # The decorator's size is the chart's box's, not the output's.
    assert "height: auto" in rendered
    assert "7em" not in rendered


def test_an_unknown_output_arg_names_the_ui_function(fake_session):
    """Forwarded rather than swallowed, so a typo is not silence.

    ``output_maidr`` takes a deliberately narrow set of arguments, and a
    keyword it does not know is a mistake worth raising -- an
    ``**kwargs``-absorbing container would drop it on the floor.
    """
    from shiny.express import output_args

    @output_args(not_an_argument=1)
    @render_maidr
    def sized():
        return _bar_axes()

    with pytest.raises(TypeError, match="output_maidr"):
        sized._render_auto_output_ui()


def test_output_maidr_applies_module_namespacing():
    """A module's output id is namespaced, so modules keep working."""
    with module.namespace_context("mod1"):
        assert 'id="mod1-my_plot"' in str(output_maidr("my_plot"))


# ---------------------------------------------------------------------------
# Size: the output keeps its box, and the chart's box takes the sizes
# ---------------------------------------------------------------------------


def _style(tag) -> dict[str, str]:
    """A tag's inline style, as ``{property: value}``."""
    style = str(tag.attrs.get("style", ""))
    return {
        part.split(":", 1)[0].strip(): part.split(":", 1)[1].strip()
        for part in style.split(";")
        if ":" in part
    }


def test_the_output_keeps_a_box_once_a_chart_is_in_it():
    """Shiny's ``display: contents`` took the output's size with its box.

    ``div:where(.shiny-html-output):has(>*) { display: contents }`` makes a
    UI output a pass-through container as soon as it has children, so the
    width and height it was given applied only while it was empty. A
    ``display`` of its own, inline, wins over that rule. The output is a
    column the chart's box fills, and may shrink below the chart's height.
    """
    style = _style(output_maidr("chart", width="400px", height="300px"))

    assert style["display"] == "flex"
    assert style["flex-direction"] == "column"
    assert (style["width"], style["height"]) == ("400px", "300px")
    assert style["min-height"] == "0"
    assert style["max-width"] == "100%"


@pytest.mark.parametrize(
    ("given", "css"), [(500, "500px"), (300.5, "300.5px"), ("50vh", "50vh")]
)
def test_a_number_is_pixels_as_shiny_takes_it(given, css):
    """``500`` was written as ``width: 500``, which CSS drops."""
    style = _style(output_maidr("chart", width=given, height=given))

    assert (style["width"], style["height"]) == (css, css)


def test_a_size_of_the_wrong_type_fails_where_it_is_written():
    with pytest.raises(TypeError, match="width"):
        output_maidr("chart", width=[500])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="height"):
        render_maidr(height=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="width"):
        render_maidr(width=object())  # type: ignore[arg-type]


def test_a_size_of_none_is_no_size_as_shiny_has_it(fake_session):
    """``as_css_unit(None)`` is no size; it was a ``TypeError`` here."""
    style = _style(output_maidr("chart", width=None, height=None))

    assert "width" not in style and "height" not in style
    assert style["display"] == "flex"

    @render_maidr(width=None, height=None)
    def chart():
        return _bar_axes()

    box = _box(_render(chart)["html"])
    assert "width:" not in box and "height:" not in box


def test_the_output_fills_a_fillable_container_by_default():
    """As ``output_plot`` does; ``fill=False`` keeps it to its own height."""
    filled = output_maidr("chart")
    kept = output_maidr("chart", fill=False)

    assert "html-fill-item" in filled.attrs["class"]
    assert "html-fill-item" not in kept.attrs["class"]
    # Either way a fillable container, for the chart's box to fill.
    for tag in (filled, kept):
        assert "html-fill-container" in tag.attrs["class"]


def _box(html: str) -> str:
    """The opening tag of the box the frame is fitted to."""
    match = re.search(r'<div class="maidr-shiny-box[^"]*"[^>]*>', html)
    assert match, "the frame is not in a box"
    return unescape(match.group(0))


def test_the_frame_is_in_a_box_that_fills_the_output(fake_session):
    """The box the frame's script fits the chart to, and scrolls in."""

    @render_maidr
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]
    box = _box(html)

    assert "html-fill-item" in box
    assert "overflow: auto" in box
    # No size of its own: it fills the output.
    assert "width:" not in box and "height:" not in box
    assert html.index(box[:30]) < html.index("<iframe")


def test_render_maidrs_size_is_the_charts_box(fake_session):
    """``@render_maidr(width=500, height=300)`` sized nothing outside Express.

    It now sizes the box the chart is fitted to, as ``@render.plot``'s
    sizes the image: at most the output's width, and a height that does
    not grow to fill the output.
    """

    @render_maidr(width=500, height=300)
    def chart():
        return _bar_axes()

    box = _box(_render(chart)["html"])

    assert "width: 500px" in box
    assert "max-width: 100%" in box
    assert "height: 300px" in box
    assert "flex: 0 0 auto" in box


def test_express_gives_the_box_the_renderers_size(fake_session):
    """Under Express too the renderer's size is the box's, the output's none.

    Given to the output, a height made a fill output 300px of a card's
    778, grown to the rest, and the chart centred in it, where
    ``@render.plot(height=300)`` draws a 300px image at the top. Given to
    both, a width of 50% would be a quarter. The output takes ``fill``.
    """

    @render_maidr(width="50%", height=300, fill=False)
    def chart():
        return _bar_axes()

    container = chart.auto_output_ui()
    style = _style(container)
    box = _box(_render(chart)["html"])

    assert (style["width"], style["height"]) == ("100%", "auto")
    assert "html-fill-item" not in container.attrs["class"]
    assert "width: 50%" in box and "height: 300px" in box
    assert "html-fill-item" in chart.auto_output_ui(fill=True).attrs["class"]


def test_the_frame_fits_its_box_in_a_shiny_session(fake_session):
    """The chart is sized as a notebook shows the plain figure, and fitted."""

    @render_maidr
    def chart():
        return _bar_axes()

    payload = _render(chart)
    html = unescape(payload["html"])
    document = _iframe_document(fake_session, payload["html"])

    assert "maidrShinyFrame(f,'matplotlib',{})" in html
    assert SHINY_FRAME_NAME in [dep["name"] for dep in payload["deps"]]
    assert 'class="maidr-frame-svg"' in document
    assert document.startswith("<style>")


def test_a_chart_drawn_again_does_not_scroll_the_page():
    """The served script holds the output still; it never scrolls the page.

    Shiny put the new frame in at 150px, the frame was measured at no
    height and at 4000px, and the page was scrolled back by what the frame
    had grown: a reader below a chart whose top was above the window lost
    the chart and the control they were moving, with every redraw.
    """
    script = shiny_frame_script()

    # Held as Shiny is about to draw the output again, and while each frame
    # is measured; let go once a new frame has measured its chart.
    assert "window.jQuery(document).on('shiny:value'" in script
    assert "maidrHoldRedraw(event.target);" in script
    # An element's alone, and never an error in Shiny's message loop: a
    # value for an output not in the page is sent to the document.
    assert "if (event.target && event.target.nodeType === 1) {" in script
    assert "} catch (e) {}" in script
    assert script.count("maidrHoldStill(iframe)") == 3  # defined, and 2 calls
    assert script.count("maidrRedrawn(iframe);") == 2
    # Only the frame's own box is scrolled back after a fitted measure; the
    # page, as a notebook's, only while a dialog is open.
    assert script.count("maidrKeepBoxScroll(iframe)") == 3


def test_a_dialog_lays_the_frame_out_as_a_notebooks():
    """While a dialog of maidr's is open, the frame is laid out as before.

    Room, placement and scrolling of its own for a dialog in a fitted box
    cut one dialog or another off, or moved the page as it closed; laying
    the chart out at its own size, but keeping the box's and the output's
    style, cut a dialog in the lower part of the window, narrowed it, and
    moved the page at its end. While one is open, the box is a
    pass-through container, the output has none of output_maidr's style
    or fill classes (Shiny's own rule makes it a pass-through container
    too), the frame has an iframe's style as it had then, and the frame
    runs a notebook frame's lines, its dialog room and scrolling included.
    All of it comes back once the dialog has gone, or once the frame has
    left the page.
    """
    script = shiny_frame_script()

    assert script.count("let fitted = !maidrSuspendBox(iframe);") == 1
    assert script.count("var fitted = !maidrSuspendBox(iframe);") == 1
    assert "box.setAttribute('style', 'display: contents');" in script
    assert "out.removeAttribute('style');" in script
    assert "['html-fill-container', 'html-fill-item']" in script
    assert (
        "iframe.setAttribute('style', "
        "'background-color: #fff; position: relative; border: none');"
    ) in script
    assert "if (!iframe.isConnected) maidrSuspendBox(iframe);" in script
    # A chart that takes its frame's width is not drawn again wider.
    assert "iframe.style.maxWidth = width + 'px';" in script
    # A notebook frame's width, room and scrolling, as they are in one.
    assert "let room = fitted ? 0 : maidrDialogRoom(iframeDocument, iframe);" in script
    assert "var room = fitted ? 0 : maidrDialogRoom(doc, iframe);" in script
    assert (
        "iframe.style.maxWidth = Math.max(own + side, dialogOpen ? 664 : 0) + 'px';"
    ) in script
    assert script.count("maidrShowDialog(") == 3  # defined, and 2 calls
    assert script.count("? maidrKeepBoxScroll(iframe) : maidrKeepScroll(iframe);") == 2
    # Nothing of the branch's own placement, anchoring or held heights.
    for gone in (
        "maidrNoAnchor",
        "overflowAnchor",
        "maidrBoxDialogRoom",
        "maidrHoldBox",
        "maidrShown",
        "--maidr-dialog-top",
        "maidrPutBack",
        "maidrDialogPlaces",
        "body.style.minHeight",
        "maxWidth = 'none'",
    ):
        assert gone not in script, gone
    # The page is scrolled by a notebook's dialog code and a field of
    # maidr's own, and nothing else.
    assert script.count("scrollIntoView(") == 2
    # At once: a Shiny page scrolls smoothly, and the next measure stopped
    # a smooth scroll halfway.
    assert (
        "iframe.scrollIntoView(\n"
        "                    {block: 'center', inline: 'nearest', behavior: 'instant'}"
    ) in script
    # Below a header fixed or sticky at the window's top.
    assert "iframe.maidrCover = scroller ? 0 : maidrCover(iframe);" in script
    assert "height -= iframe.maidrCover;" in script
    assert "iframe.style.scrollMarginTop = iframe.maidrCover + 'px';" in script
    assert "el.scrollTo({top: top, left: kept[i][2], behavior: 'instant'});" in script
    assert "el.scrollTop = top;" not in script
    # The page, and every element round the frame, put back where they
    # were as the dialog opened, as it closes and once the browser has
    # scrolled to the chart given the focus back, unless the reader
    # scrolled or the window changed size.
    assert "kept: maidrKeepPlace(iframe)" in script
    assert "was.kept();" in script
    assert "                kept.push([el, el.scrollTop, el.scrollLeft]);\n" in script
    assert "win.addEventListener('scroll', put, true);" in script
    assert "doc.addEventListener('focusin', suspended.back, true);" in script
    assert "field.scrollIntoView({block: 'nearest', inline: 'nearest'});" in script
    # A chart drawn again under a dialog is left to Shiny.
    assert "if (old[i].maidrSuspended) return;" in script


def test_a_frame_holds_a_height_only_at_the_scrollbars_threshold():
    """The two heights of a frame at the classic scrollbars' threshold.

    Any height, then another, then the first again, at one window width
    was taken for the threshold's flip, and the taller held until the
    reader did something in the chart: after full screen and back, a
    window made shorter and taller, and a Bokeh plot scaled both ways
    drawn at 1256px, 450px, 1256px as it loads. It is held now only when
    the box's width flips with it, by no more than the scrollbars that came
    and went round it took, whatever their width (a 24px limit let a 25px
    one resize the frame without end), the narrower giving the shorter
    height, and let go at any other change.
    """
    script = shiny_frame_script()

    assert script.count("height = maidrSteady(iframe, height);") == 2
    assert "Math.abs(b.width - a.width) <= Math.abs(b.bars - a.bars) + 1" in script
    assert "(b.width < a.width) === (b.bars > a.bars)" in script
    assert "(b.width < a.width) === (b.height < a.height)" in script
    assert "var size = win.innerWidth + 'x' + win.innerHeight;" in script
    for gone in ("maidrSteadyReset", "iframe.maidrSteady"):
        assert gone not in script, gone


def test_the_frame_script_is_served_once_rather_than_sent(fake_session):
    """The script that sizes the frame rides no flush; the app serves it.

    It was 11 KB of every flush of every chart's output, most of what the
    websocket carried for it. A frame's ``onload`` now names only its kind
    and its options, and the script is a dependency Shiny loads once per
    page, before it puts the frame in it.
    """
    from pathlib import Path

    @render_maidr
    def chart():
        return _bar_axes()

    payload = _render(chart)
    onload = unescape(re.search(r'onload="([^"]*)"', payload["html"]).group(1))

    assert len(onload) < 300, onload
    # The flush brings the dependency, so the frame names no route to load
    # the script from itself (``test_a_frame_made_into_a_string_...``).
    assert "createElement" not in onload
    # The frame and the focus restore: a fraction of the 16 KB that marks a
    # chart's document riding the flush
    # (``test_the_payload_references_the_chart_rather_than_carrying_it``).
    assert len(payload["html"]) < 6_000, len(payload["html"])
    assert "resizeIframe" not in onload
    [sent] = [dep for dep in payload["deps"] if dep["name"] == SHINY_FRAME_NAME]
    assert [script["src"].rsplit("/", 1)[-1] for script in sent["script"]] == [
        "frame.js"
    ]
    [served] = [
        dep for dep in fake_session.app.registered if dep.name == SHINY_FRAME_NAME
    ]
    source = Path(served.source_path_map()["source"]) / "frame.js"
    assert source.read_text(encoding="utf-8") == shiny_frame_script()
    # Versioned by its content, so a browser never keeps a stale copy.
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    assert str(served.version).endswith("+g" + digest), served.version
    # A local label packaging keeps as written, whatever the digits.
    assert str(Version(_shiny_frame_version())) == _shiny_frame_version()
    assert str(Version("1.26.0+g012345678901")) == "1.26.0+g012345678901"


@pytest.mark.parametrize("plotly", [False, True])
def test_a_frame_made_into_a_string_carries_its_script(fake_session, plotly):
    """``ui.HTML(str(maidr.render(fig)))`` in a ``render.ui``: no dependency.

    ``str()`` drops a frame's dependency, which Shiny then neither loads
    nor serves, and the frame, on a page with no other chart, stayed 150px
    tall and cut the chart off. A frame made outside ``render_maidr``
    carries the script, as frames did before it was served, so that it is
    sized wherever it is shown: a later session, a file, another process.
    """
    if plotly:
        go = pytest.importorskip("plotly.graph_objects")
        figure = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
    else:
        figure = _bar_axes()

    html = str(maidr.render(figure))
    onload = unescape(re.search(r'onload="([^"]*)"', html).group(1))

    script = carried_script(onload)
    assert "window.maidrShinyFrame=function(frame,kind,options)" in script
    kind = "plotly" if plotly else "matplotlib"
    # Its own kind's script alone.
    assert f"kinds.{kind}=" in script.replace(" ", "")
    other = "matplotlib" if plotly else "plotly"
    assert f"kinds.{other}" not in script
    assert re.search(rf"maidrShinyFrame\(f,'{kind}',\{{[^}}]*\}}\)", onload)
    if plotly:
        assert '"fillHeight":450' in onload
    # Nothing to load, route to register or size to guess at.
    for gone in (".src=", "maidrShinyFrameSrc", "++k>6"):
        assert gone not in onload, gone
    assert SHINY_FRAME_NAME not in html
    assert not fake_session._dynamic_routes
    assert not [
        dep for dep in fake_session.app.registered if dep.name == SHINY_FRAME_NAME
    ]


def test_a_frame_made_in_express_s_page_carries_its_script():
    """A string made as Shiny Express builds the page, outside a render.

    Express runs the app's file with a stand-in session to build its page,
    which has no app to register the dependency with and serves nothing:
    the frame had no URL to load its script from, and stayed 150px tall.
    It carries the script instead, in its ``onload``, compacted.
    """
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context

    with session_context(ExpressStubSession()):  # type: ignore[arg-type]
        html = str(maidr.render(_bar_axes()))
    onload = unescape(re.search(r'onload="([^"]*)"', html).group(1))

    assert ".src=" not in onload
    assert "maidrShinyFrame(f,'matplotlib',{})" in onload
    script = carried_script(onload)
    assert "window.maidrShinyFrame=function(frame,kind,options)" in script
    assert "\n//" not in script
    assert len(onload) < len(shiny_frame_script()) * 0.4, len(onload)


def test_a_shiny_frame_starts_with_the_rules_it_is_laid_out_by():
    """Its document has the rules it is laid out by; its script adds the rest.

    Focus rings, a dialog's band and a fitted chart's centring apply once
    the frame's script runs, and travel in it, once per page, rather than
    in every frame's document with every flush.
    """
    import json

    first, later = _shiny_frame_css()
    assert "html,body{margin:0;padding:0}" in first
    assert ".maidr-frame-fill" in first and "svg.maidr-frame-svg{" in first
    for rule in (":focus", "forced-colors", "data-maidr-dialog-room", "fit-box"):
        assert rule not in first and rule in later, rule
    script = shiny_frame_script()
    assert f"style.textContent = {json.dumps(later)};" in script
    assert script.count("maidrFrameStyle(frame);") == 2


#: What a frame made into a string carried for its sizing before charts were
#: fitted to their outputs (3ac3a5db): its ``onload`` attribute, the script
#: that sized it, as HTML writes it; its document had no stylesheet of its
#: own. The same for every chart of a kind.
_ONLOAD_BEFORE = {"matplotlib": 10_467, "plotly": 9_151}


@pytest.mark.parametrize("plotly", [False, True])
def test_a_string_frame_carries_its_script_compacted_as_plain_text(plotly):
    """A string frame's script and stylesheet, against its old script alone.

    The script it carried, its comments left out, was 22 KB of every flush,
    20 KB more than before charts were fitted. It carries its own kind's
    alone now, compacted, and its stylesheet compacted: 22-24 KB as HTML
    writes it, a little over twice what it carried then (``_ONLOAD_BEFORE``),
    as plain text, which every browser runs. Packed, it was less than that,
    but a browser that could not unpack it left the frame 150px tall, the
    chart cut off
    (``test_a_string_frame_is_sized_in_a_browser_that_cannot_unpack``).
    """
    from shiny.express._stub_session import ExpressStubSession
    from shiny.session import session_context

    if plotly:
        go = pytest.importorskip("plotly.graph_objects")
        figure = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
    else:
        figure = _bar_axes()
    with session_context(ExpressStubSession()):  # type: ignore[arg-type]
        html = str(maidr.render(figure))
    onload = re.search(r'onload="([^"]*)"', html).group(1)
    style = re.search(r'srcdoc="(&lt;style&gt;.*?&lt;/style&gt;)', html).group(1)
    kind = "plotly" if plotly else "matplotlib"
    for gone in ("DecompressionStream", "atob(", "createElement('script')"):
        assert gone not in onload, gone
    assert len(onload) + len(style) <= 25_000, (
        len(onload),
        len(style),
    )


def test_a_plotly_figure_has_a_height_of_its_own_in_shiny(fake_session):
    """Plotly's ``height: 100%`` was the frame's, which grew with maidr's text."""
    go = pytest.importorskip("plotly.graph_objects")

    def chart_of(fig):
        @render_maidr
        def chart():
            return fig

        return _iframe_document(fake_session, _render(chart)["html"])

    plain = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
    assert "height:450px" in chart_of(plain).replace(" ", "")

    tall = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]), layout={"height": 700})
    assert "height:700px" in chart_of(tall).replace(" ", "")


def _frame_options(fake_session, value) -> dict:
    """The options a chart's frame hands the served sizing script."""
    import json

    @render_maidr
    def chart():
        return value

    onload = unescape(re.search(r'onload="([^"]*)"', _render(chart)["html"]).group(1))
    return json.loads(
        re.search(r"maidrShinyFrame\(f,'plotly',(\{.*?\})\)", onload).group(1)
    )


def test_a_plotly_figure_is_sized_by_its_box_only_when_plotly_would(fake_session):
    """With no size of its own it fills the box; ``autosize=False`` is fixed.

    plotly.js draws a figure whose layout turns ``autosize`` off at 700 by
    450 pixels whatever its div is; taken for one that fills its container,
    its frame never widened to it, and its right half was out of reach.
    """
    go = pytest.importorskip("plotly.graph_objects")
    bar = go.Bar(x=["a", "b"], y=[1, 2])

    assert _frame_options(fake_session, go.Figure(bar)) == {
        "widens": False,
        "fillHeight": 450,
    }
    fixed = go.Figure(bar, layout={"autosize": False})
    assert _frame_options(fake_session, fixed) == {"widens": True}
    tall = go.Figure(bar, layout={"height": 700})
    assert _frame_options(fake_session, tall) == {"widens": False}


@pytest.mark.parametrize(
    ("mode", "fills"),
    [
        ("stretch_both", True),
        ("stretch_height", True),
        ("scale_both", True),
        ("stretch_width", False),
        ("fixed", False),
    ],
)
def test_a_bokeh_plot_that_takes_its_containers_height_is_given_one(
    fake_session, mode, fills
):
    """``stretch_both`` collapsed to a 51px frame with nothing drawn in it."""
    bokeh_plotting = pytest.importorskip("bokeh.plotting")
    plot = bokeh_plotting.figure(x_range=["a", "b"], sizing_mode=mode, title="Sales")
    plot.vbar(x=["a", "b"], top=[1, 2], width=0.5)

    options = _frame_options(fake_session, plot)
    assert ("fillHeight" in options) is fills, options
    if fills:
        assert options["fillHeight"] == 450
    # Scaled both ways, it keeps its shape within that height too: Bokeh
    # sizes it by its container's width alone.
    assert options.get("keepsShape", False) is (mode == "scale_both"), options


@pytest.mark.parametrize(
    ("height", "fills"), [("container", True), (300, False), (None, False)]
)
def test_an_altair_chart_as_tall_as_its_container_is_given_a_height(
    fake_session, height, fills
):
    """``height="container"`` was drawn 0px tall: its container had none."""
    alt = pytest.importorskip("altair")
    pd = pytest.importorskip("pandas")
    chart = (
        alt.Chart(pd.DataFrame({"x": ["a", "b"], "y": [1, 2]}))
        .mark_bar()
        .encode(x="x", y="y")
    )
    if height is not None:
        chart = chart.properties(height=height)

    options = _frame_options(fake_session, chart)
    assert options.get("fillHeight") == (450 if fills else None), options


# ---------------------------------------------------------------------------
# Rendered payload
# ---------------------------------------------------------------------------


def test_payload_has_the_shape_shiny_expects(fake_session):
    """``_process_ui`` returns ``{"deps", "html"}``; fail loudly if that moves."""

    @render_maidr
    def chart():
        return _bar_axes()

    payload = _render(chart)
    assert set(payload) == {"deps", "html"}


def test_the_payload_carries_the_focus_restore_script(fake_session):
    """Every render ships the hook that survives a re-render (#484).

    Shiny replaces the output container on each reactive flush, taking the
    focused element with it, which drops a reader out of the chart they
    were navigating. The script rides with the chart rather than with the
    container because ``output_maidr`` is not always what places the
    output -- Express mode goes through ``auto_output_ui``, and an app may
    write its own ``ui.output_ui`` -- but every chart comes through the
    renderer.
    """

    @render_maidr
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]
    assert "__maidrShinyFocusRestore" in html


def test_the_rendered_iframe_is_marked_as_maidrs_own(fake_session):
    """The focus script must be able to tell our frame from anyone else's.

    Keying off a bare ``iframe`` would let the restore force focus onto an
    unrelated embed an app happened to put in the same output container.
    The marker is what makes the selector precise, so both sides of it are
    pinned here.
    """
    from maidr.widget._focus import FOCUS_RESTORE_JS

    @render_maidr
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]
    assert "data-maidr-chart" in html
    assert "data-maidr-chart" in FOCUS_RESTORE_JS


def test_the_container_class_the_focus_script_looks_for_still_exists():
    """The script finds its container by a Shiny-internal class.

    ``.shiny-html-output`` is an implementation detail of
    ``ui.output_ui``, not a documented contract. If Shiny renames it, the
    script finds no containers and the fix goes silently inert -- no
    exception, no warning, and the only thing that would notice is the
    browser suite, which is opt-in and so not what a contributor runs.

    This ties the two sides together in the default suite, so a Shiny
    upgrade that moves the class fails here instead.
    """
    from maidr.widget._focus import FOCUS_RESTORE_JS

    assert "shiny-html-output" in FOCUS_RESTORE_JS
    assert "shiny-html-output" in str(output_maidr("chart"))


def test_the_focus_script_only_installs_once_per_page(fake_session):
    """It arrives on every render, so it has to be idempotent.

    Without the guard, N flushes would leave N samplers and N observers
    running, each restoring focus -- the cost of shipping it per render
    rather than per container.
    """

    @render_maidr
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]
    assert "if (window.__maidrShinyFocusRestore) return;" in html


@pytest.mark.parametrize(
    ("use_cdn", "expect_cdn", "expect_served"),
    [(True, True, False), ("auto", True, True), (False, False, True)],
)
def test_each_cdn_mode_ships_the_source_it_promises(
    fake_session, use_cdn, expect_cdn, expect_served
):
    """Every mode must put a real source for maidr.js in the document.

    Regression test for the silent failure this replaces: an iframed
    ``use_cdn=False`` render emitted neither a script tag nor the bundle,
    so the chart arrived as a picture with no sonification, no braille and
    no keyboard navigation -- and no error to say so.

    Each mode is asserted exactly rather than as a disjunction. A single
    "some source is present" check would pass on the wrong source.

    The bundled copy is never inline any more (#457): the document names
    the copy the app serves, and the payload carries the dependency that
    makes the app serve it. ``use_cdn=False`` loads it; ``"auto"`` loads
    the CDN and falls back to it, which is what gives ``"auto"`` an
    offline fallback under Shiny at all; ``True`` names neither and
    registers nothing.

    Read from the document the route serves, since that -- not the
    payload -- is what the frame loads (#534).
    """

    @render_maidr(use_cdn=use_cdn)
    def chart():
        return _bar_axes()

    payload = _render(chart)
    document = _iframe_document(fake_session, payload["html"])

    # The maidr loader URL rather than the bare host: the bundle names
    # jsDelivr itself, for the DotPad SDK it fetches on first connect
    # (#771), so the host alone is in every offline document too. And an
    # offline document names where its locale packs are there (#819).
    loader = document.replace(get_locale_base_url(), "")
    assert ("cdn.jsdelivr.net/npm/maidr" in loader) is expect_cdn
    assert _BUNDLE_HEAD not in document, "the bundle is still inlined"
    assert (_SERVED_JS in document) is expect_served
    names = [dep["name"] for dep in _bundle_deps(payload)]
    assert names == ([SERVED_BUNDLE_NAME] if expect_served else []), names
    assert [dep.name for dep in _registered_bundles(fake_session)] == names


# ---------------------------------------------------------------------------
# The chart travels out of band (#534)
# ---------------------------------------------------------------------------


def _bars(n: int):
    """The axes of a chart with ``n`` bars, so two renders can be told apart."""
    _, ax = plt.subplots()
    ax.bar([chr(97 + i) for i in range(n)], range(1, n + 1))
    return ax


def _src_of(html: str) -> str:
    return re.search(r'src="([^"]*)"', html).group(1)


def _bundle_deps(payload: dict) -> list:
    """The served bundle among a payload's dependencies.

    Every chart frame also names the script Shiny's frames size themselves
    with (``maidr-shiny-frame``), whatever ``use_cdn`` is; see
    ``test_the_frame_script_is_served_once_rather_than_sent``.
    """
    return [dep for dep in payload["deps"] if dep["name"] == SERVED_BUNDLE_NAME]


def _registered_bundles(session) -> list:
    """The served bundle among what a session's app was asked to serve."""
    return [dep for dep in session.app.registered if dep.name == SERVED_BUNDLE_NAME]


def test_the_payload_references_the_chart_rather_than_carrying_it(fake_session):
    """The document leaves the websocket: the frame points at a session route.

    Before this, every reactive flush pushed the whole chart through the
    output payload -- ~25 KB on the default ``use_cdn``, ~2 MB with the
    bundle inlined -- on the one channel every input and output shares.
    The payload is now the frame and its scripts, whatever the chart
    weighs.
    """

    @render_maidr(use_cdn=False)
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]

    assert "srcdoc" not in html
    assert _FRAME_SRC.search(html), html[:300]
    assert _BUNDLE_HEAD not in html, "the bundle still rides the websocket"
    assert len(html) < 16_000, f"{len(html)} bytes per flush is not out of band"


def test_the_served_document_is_the_one_maidr_rendered(fake_session, monkeypatch):
    """Every door still ships the same chart: the route serves the srcdoc.

    The document the browser fetches has to be exactly what ``maidr.render``
    put in the frame -- not a re-render, not a trimmed copy. Captured off
    the frame before the renderer detaches it, since detaching is what
    is under test.
    """
    import maidr.widget.shiny as shiny_module

    captured: list[str] = []
    real_render = shiny_module.maidr.render

    def spy(value, **kwargs):
        rendered = real_render(value, **kwargs)
        captured.append(rendered.attrs["srcdoc"])
        return rendered

    monkeypatch.setattr(shiny_module.maidr, "render", spy)

    @render_maidr
    def chart():
        return _bar_axes()

    served = _iframe_document(fake_session, _render(chart)["html"])

    assert captured, "the render never ran"
    assert served == captured[0]
    assert "maidr=" in served, "no MAIDR schema in the served document"


def test_the_frame_stays_on_the_hosts_origin(fake_session):
    """A relative ``src``, so the frame is same-origin with its page.

    ``srcdoc`` kept the frame same-origin, and two things depend on that:
    the resize script reaches into the frame's document, and the ``allow``
    attribute grants a device to the origin the frame loads from. A
    ``data:`` or cross-origin URL would silently lose both.
    """

    @render_maidr
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]

    assert _src_of(html).startswith("session/"), _src_of(html)
    assert "allow=" in html
    assert "onload=" in html


def test_one_route_per_output_and_a_new_version_per_render(fake_session):
    """Renders share a route, and the URL changes with every one.

    A route per render would leave every past handler registered for the
    life of the session. The version is what makes each render a new
    address, so nothing between the reader and the app can answer a
    flush with the chart before it.
    """

    @render_maidr
    def chart():
        return _bar_axes()

    srcs = [_src_of(_render(chart)["html"]) for _ in range(3)]

    assert len(fake_session._dynamic_routes) == 1
    routes = {src.split("?")[0] for src in srcs}
    assert len(routes) == 1, routes
    versions = [re.search(r"v=(\d+)", src).group(1) for src in srcs]
    assert versions == ["1", "2", "3"], versions


def test_the_route_is_named_for_the_output(fake_session):
    """Two outputs in one session must not serve each other's chart."""

    @render_maidr
    def first():
        return _bar_axes()

    @render_maidr
    def second():
        return _bar_axes()

    _render(first)
    _render(second)

    assert set(fake_session._dynamic_routes) == {"maidr_first", "maidr_second"}


def test_a_chart_renders_inside_a_module(fake_session):
    """A module's session names the route as an id, and a hyphen is not one.

    ``SessionProxy.dynamic_route`` namespaces the name with ``ns()``, which
    takes letters, digits and underscores only; ``maidr-<id>`` raised there,
    so no ``render_maidr`` ever rendered inside a module. Shiny's own proxy
    method is borrowed, over the fake root session, so the check is Shiny's.
    """
    from shiny import module
    from shiny.session import session_context
    from shiny.session._session import SessionProxy

    class ModuleSession:
        """A module's view of ``fake_session``, as ``SessionProxy`` gives it."""

        def __init__(self, root) -> None:
            self._root_session = root
            self.id = root.id
            self.app = root.app
            self.ns = module.ResolvedId("mod")

        dynamic_route = SessionProxy.dynamic_route

        def on_ended(self, fn):
            return self._root_session.on_ended(fn)

        def _process_ui(self, ui):
            return self._root_session._process_ui(ui)

    @render_maidr
    def chart():
        return _bar_axes()

    with session_context(ModuleSession(fake_session)):  # type: ignore[arg-type]
        html = _render(chart)["html"]

    assert set(fake_session._dynamic_routes) == {"mod-maidr_chart"}
    assert "dynamic_route/mod-maidr_chart?" in html
    assert "<svg" in _fetch(fake_session, html).body.decode()


def test_the_route_serves_the_latest_render_and_holds_no_other(fake_session):
    """A render replaces the document, and it is the new chart that is served.

    Two visibly different charts, so this cannot pass on a route that kept
    the first document forever. Holding one document per output is also
    the memory bound: keeping each one would grow a session by a chart
    per flush -- and by ~2 MB per flush wherever the bundle still has to
    travel inside the document (#457).
    """
    n = [2]

    @render_maidr
    def chart():
        return _bars(n[0])

    first = _iframe_document(fake_session, _render(chart)["html"])
    n[0] = 5
    second = _iframe_document(fake_session, _render(chart)["html"])

    assert first != second
    assert (
        "&quot;e&quot;" not in first and "&quot;e&quot;" in second
    ), "the second render did not serve the five-bar chart"

    served = chart._served[fake_session.id]
    assert served.version == 2
    assert served.document == second


def test_every_response_is_no_store(fake_session):
    """Nothing caches the chart: not the browser's disk, not a proxy.

    ``srcdoc`` content was never cached anywhere, and a chart may carry
    one reader's data; a long-lived cache entry would leave it on disk
    for the next user of that browser. So the current version and a
    stale one alike are served ``no-store`` -- the stale one gets the
    current chart, since the only frame that can ask for it is one a
    newer flush is already replacing.
    """

    @render_maidr
    def chart():
        return _bar_axes()

    html = _render(chart)["html"]
    _render(chart)  # version 2 replaces the document the frame above named

    stale = _fetch(fake_session, html)
    current = _fetch(fake_session, html, version="2")

    for response in (stale, current):
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
    assert current.body == stale.body


def test_a_fetch_with_nothing_rendered_is_a_404(fake_session):
    """The route tolerates a request the output has nothing for."""
    from starlette.requests import Request

    from maidr.widget.shiny import _ServedChart

    response = _ServedChart().serve(
        Request({"type": "http", "method": "GET", "headers": [], "query_string": b""})
    )
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


def test_a_blank_render_drops_the_document(fake_session):
    """Returning ``None`` empties the output, so the chart is let go too.

    The frame that would have fetched it is gone with the output; holding
    a document nobody can reach is the leak this avoids.
    """
    value = [_bar_axes()]

    @render_maidr
    def chart():
        return value[0]

    html = _render(chart)["html"]
    value[0] = None
    assert _render(chart) is None

    assert chart._served[fake_session.id].document is None
    assert _fetch(fake_session, html).status_code == 404


def test_state_is_per_session_so_one_reader_never_gets_anothers_chart():
    """One renderer instance in two sessions serves two charts, not one.

    Shiny does not stop an app from attaching a renderer built at module
    scope to every session with ``@output``. State kept on the instance
    alone would then point session B's frame at session A's route -- and
    serve B whatever A last rendered.
    """
    from shiny.session import session_context

    FakeSession = _fake_session_class()
    a, b = FakeSession("session-a"), FakeSession("session-b")

    n = [2]

    @render_maidr
    def chart():
        return _bars(n[0])

    with session_context(a):
        html_a = _render(chart)["html"]
    n[0] = 5
    with session_context(b):
        html_b = _render(chart)["html"]

    assert "session-a" in _src_of(html_a) and "session-b" in _src_of(html_b)
    doc_a = _iframe_document(a, html_a)
    doc_b = _iframe_document(b, html_b)
    assert "&quot;e&quot;" not in doc_a, "session A was served session B's chart"
    assert "&quot;e&quot;" in doc_b


def test_the_document_is_let_go_when_the_session_ends(fake_session):
    """The session ending is what bounds the memory an output holds."""

    @render_maidr
    def chart():
        return _bar_axes()

    _render(chart)
    assert fake_session.id in chart._served

    fake_session.end()

    assert chart._served == {}


def test_a_session_that_registers_no_route_keeps_the_document_in_the_frame(
    fake_session,
):
    """An empty URL from ``dynamic_route`` leaves the chart where it was.

    Shiny's stub session returns ``""`` from ``dynamic_route``. Pointing a
    frame at that would be a chart that silently loads nothing, and the
    document would already have been popped off the frame, so it is
    better to fall back to ``srcdoc`` than to detach.

    With no route there is also nothing to name the served bundle
    relative to (#457), so a ``srcdoc`` document carries it inline, as it
    always has, and nothing is registered.
    """
    fake_session.dynamic_route = lambda name, handler: ""

    @render_maidr(use_cdn=False)
    def chart():
        return _bar_axes()

    payload = _render(chart)
    html = payload["html"]

    assert "srcdoc=" in html
    assert not _FRAME_SRC.search(html)
    assert chart._served == {}
    assert _BUNDLE_HEAD[:40] in unescape(html)
    assert _SERVED_JS not in html
    assert _bundle_deps(payload) == []


def test_a_render_that_is_not_a_frame_is_passed_through(fake_session, monkeypatch):
    """Nothing to detach: a fallback tag or a bare chart goes out as it is.

    The route is registered before the render, since the render needs its
    URL to name the served bundle (#457); with no document behind it, it
    answers 404 exactly as it does after a blank render, and nothing asks
    the app to serve the bundle.
    """
    from htmltools import tags

    import maidr.widget.shiny as shiny_module

    monkeypatch.setattr(
        shiny_module.maidr, "render", lambda value, **kw: tags.div("a chart")
    )

    @render_maidr
    def chart():
        return _bar_axes()

    payload = _render(chart)

    assert "<div>a chart</div>" in payload["html"]
    assert not _FRAME_SRC.search(payload["html"])
    assert chart._served[fake_session.id].document is None
    assert payload["deps"] == []
    assert fake_session.app.registered == []


# ---------------------------------------------------------------------------
# The bundle is served once per app, not carried by every chart (#457)
# ---------------------------------------------------------------------------

#: The ``<script src>`` a chart document loads the served bundle with.
_SERVED_SCRIPT = re.compile(r'<script src="([^"]*/maidr\.js)"')


def test_an_offline_document_loads_the_bundle_by_url_instead_of_carrying_it(
    fake_session,
):
    """``use_cdn=False`` no longer puts ~2.2 MB into every chart document.

    The bundle and the KaTeX stylesheet that travelled with it were most
    of every offline document -- fetched again for every chart on the
    page, on every render. Loaded by URL, the runtime finds
    ``maidr-math.css`` beside itself when it needs it, so neither the
    stylesheet nor the marker that stood in for its ``<link>`` is left.
    """

    @render_maidr(use_cdn=False)
    def chart():
        return _bar_axes()

    document = _iframe_document(fake_session, _render(chart)["html"])

    assert _BUNDLE_HEAD not in document
    assert "data-maidr-math" not in document, "KaTeX is still inlined"
    assert _SERVED_SCRIPT.search(document), "the document loads no maidr.js"
    assert len(document) < 64 * 1024, f"{len(document)} bytes is not a chart"


@pytest.mark.parametrize("lib_prefix", ["lib", "lib/"])
@pytest.mark.parametrize(
    "page", ["http://host/", "http://host/deep/prefix/"], ids=["root", "mounted"]
)
def test_the_served_bundle_resolves_to_what_the_app_serves(
    fake_session, lib_prefix, page
):
    """The frame's URL for ``maidr.js`` is the one Shiny mounts, under any prefix.

    An app is often served under a prefix it never sees -- Posit Connect,
    shinyapps.io, a proxy -- so the document cannot name the bundle by an
    absolute path. It names it relative to its own URL, a session route
    three levels below the page, and has to climb back to exactly where
    Shiny serves the dependency: the page's URL plus the dependency's
    ``href``. Resolved here the way a browser resolves it, from a page at
    the root and from one under a prefix, and for both spellings of
    Shiny's ``lib_prefix``.
    """
    from urllib.parse import urljoin

    fake_session.app.lib_prefix = lib_prefix

    @render_maidr(use_cdn=False)
    def chart():
        return _bar_axes()

    payload = _render(chart)
    frame_url = urljoin(page, unescape(_src_of(payload["html"])))
    document = _iframe_document(fake_session, payload["html"])
    loaded = urljoin(frame_url, _SERVED_SCRIPT.search(document).group(1))

    [dep] = _registered_bundles(fake_session)
    href = dep.source_path_map(lib_prefix=lib_prefix)["href"]
    assert loaded == urljoin(page, f"{href}/maidr.js"), (loaded, frame_url)
    assert loaded.startswith(page), "the URL climbed out of the app's prefix"


def test_the_app_serves_what_the_runtime_asks_for_and_loads_nothing(fake_session):
    """The served directory is the whole bundle; the page itself gets no script.

    ``maidr.js`` fetches ``maidr-math.css`` from beside itself, so the
    directory has to hold both. The dependency places no ``<script>`` and
    no ``<link>`` in the page it arrives on -- the frames load the
    runtime, and a copy running in the host page would find the charts'
    containers there. Versioned by the bundle, which is what puts the
    version in the URL a browser caches.
    """
    from pathlib import Path

    @render_maidr(use_cdn=False)
    def chart():
        return _bar_axes()

    payload = _render(chart)

    [dep] = _registered_bundles(fake_session)
    source = Path(dep.source_path_map()["source"])
    assert (source / "maidr.js").is_file()
    assert (source / "maidr-math.css").is_file()
    assert dep.all_files
    assert str(dep.version) == maidr_js_version()

    [sent] = _bundle_deps(payload)
    assert (sent["script"], sent["stylesheet"]) == ([], [])


def test_a_missing_bundle_is_not_named(fake_session, monkeypatch):
    """A broken install renders as it always did rather than naming a 404.

    With no ``maidr.js`` in the package the app would serve nothing at the
    URL, and the chart would load no runtime and say nothing. Offering no
    served copy leaves the render its old path, which warns that the
    bundle is unreadable and falls back to the CDN.
    """
    import maidr.widget.shiny as shiny_module

    def missing():
        raise FileNotFoundError("maidr.js")

    monkeypatch.setattr(shiny_module, "bundled_js_path", missing)

    @render_maidr(use_cdn=False)
    def chart():
        return _bar_axes()

    payload = _render(chart)
    document = _iframe_document(fake_session, payload["html"])

    assert _SERVED_JS not in document
    assert _bundle_deps(payload) == []


@pytest.mark.parametrize("use_cdn", [False, "auto"])
def test_plotly_and_bokeh_charts_name_the_served_bundle_too(fake_session, use_cdn):
    """Every renderer asks the same question, so none keeps inlining.

    Plotly and Bokeh load ``maidr.js`` through
    :mod:`maidr.util.bundle_loader` rather than the matplotlib path, so a
    change that reached only one of them would leave the other shipping
    ~2 MB per chart -- or, under ``"auto"``, still falling back to a path
    nothing serves.
    """
    go = pytest.importorskip("plotly.graph_objects")
    bokeh_plotting = pytest.importorskip("bokeh.plotting")

    plotly_fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
    bokeh_fig = bokeh_plotting.figure(x_range=["a", "b"], title="Sales")
    bokeh_fig.vbar(x=["a", "b"], top=[1, 2], width=0.5)

    def renderer(value):
        @render_maidr(use_cdn=use_cdn)
        def chart():
            return value

        return chart

    for value in (plotly_fig, bokeh_fig):
        payload = _render(renderer(value))
        document = _iframe_document(fake_session, payload["html"])

        name = type(value).__module__
        assert _BUNDLE_HEAD not in document, f"{name} still inlines the bundle"
        assert _SERVED_JS in document, f"{name} does not name the served bundle"
        assert [d["name"] for d in _bundle_deps(payload)] == [SERVED_BUNDLE_NAME]


def test_an_altair_chart_registers_no_served_bundle(fake_session):
    """Altair loads from the CDN whatever ``use_cdn`` says (#521).

    So it never names the served bundle, and nothing asks the app to serve
    one; its frame's own ``maidr-shiny-frame`` is another matter. Pinned so
    that a later change to that adapter decides this deliberately rather
    than by accident.
    """
    alt = pytest.importorskip("altair")
    import pandas as pd

    @render_maidr
    def chart():
        return (
            alt.Chart(pd.DataFrame({"x": ["a", "b"], "y": [1, 2]}))
            .mark_bar()
            .encode(x="x", y="y")
        )

    payload = _render(chart)
    document = _iframe_document(fake_session, payload["html"])

    assert "maidrVegaLite" in document
    assert _SERVED_JS not in document
    assert _bundle_deps(payload) == []


def test_the_served_bundle_is_scoped_to_the_render(fake_session):
    """Only ``render_maidr``'s own render names it; every other door is as it was.

    ``maidr.render`` called directly under a live session -- a
    ``@render.ui`` of the app's own, say -- has no route to name the
    bundle relative to, so it still carries the bundle inline. Asserted
    after a ``render_maidr`` render, so a served copy that leaked out of
    that render's context would show up here.
    """
    import maidr
    from maidr.util.served_bundle import served_bundle_url

    @render_maidr(use_cdn=False)
    def chart():
        return _bar_axes()

    _render(chart)

    assert served_bundle_url() is None
    direct = unescape(str(maidr.render(_bar_axes(), use_cdn=False)))
    assert _BUNDLE_HEAD[:40] in direct
    assert _SERVED_JS not in direct


# ---------------------------------------------------------------------------
# Value handling
# ---------------------------------------------------------------------------


def test_none_renders_nothing(fake_session):
    """Returning ``None`` leaves the output blank, per the Renderer contract.

    Also asserts that nothing is *created* on the way. ``render()`` returns
    before ``_render_off_loop``, so a ``None`` never reaches the figure
    resolution -- which since #531 goes through ``_get_plot_or_current``
    and would answer ``plt.gcf()``, opening a blank figure for an output
    the app asked to leave empty. That short-circuit is load-bearing for
    two reasons now, and only one of them was pinned.
    """

    @render_maidr
    def blank():
        return None

    open_before = set(plt.get_fignums())
    assert _render(blank) is None
    assert set(plt.get_fignums()) == open_before, "rendering nothing opened a figure"


@pytest.mark.parametrize(
    ("value", "type_name"),
    [
        ("not a plot", "str"),
        (42, "int"),
        # ``FigureManager.get_axes`` is a resolver, not a validator. An
        # empty container makes it raise a bare ``StopIteration``, which
        # the async render turns into ``RuntimeError: coroutine raised
        # StopIteration``; a list of non-artists makes it raise
        # ``AttributeError``. Both used to escape as themselves.
        ([], "list"),
        ({}, "dict"),
        ([1, 2], "list"),
    ],
)
def test_unsupported_return_value_names_the_function_and_the_type(
    fake_session, value, type_name
):
    """The error says what came back and from where, whatever came back."""

    @render_maidr
    def wrong():
        return value

    with pytest.raises(TypeError, match=rf"'wrong'.*\b{type_name}\b"):
        _render(wrong)


# ---------------------------------------------------------------------------
# Figure lifetime
# ---------------------------------------------------------------------------


def test_repeated_renders_do_not_accumulate_open_figures(fake_session):
    """A figure per flush must not stay open for the life of the app.

    Twenty-five is past matplotlib's ``figure.max_open_warning``, so
    before this the suite itself would have shown the warning an app
    would.
    """

    @render_maidr
    def chart():
        return _bar_axes()

    for _ in range(25):
        _render(chart)

    assert plt.get_fignums() == []


def test_figures_are_closed_even_when_rendering_fails(fake_session, monkeypatch):
    """A failed render must not leak the figure it opened."""
    import maidr.widget.shiny as widget

    def boom(*args, **kwargs):
        raise RuntimeError("render failed")

    monkeypatch.setattr(widget.maidr, "render", boom)

    @render_maidr
    def chart():
        return _bar_axes()

    with pytest.raises(RuntimeError):
        _render(chart)

    assert plt.get_fignums() == []


def test_a_figure_the_app_owns_is_left_open_and_still_accessible(fake_session):
    """Only figures this render opened are closed.

    An app that builds one figure at module scope and returns it on every
    flush must keep working.  Closing it would drop its
    :class:`FigureManager` entry, and the next render would quietly fall
    back to a static image -- an accessible chart turning into a picture.
    """
    ax = _bar_axes()
    opened_before = plt.get_fignums()

    @render_maidr
    def chart():
        return ax

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for _ in range(3):
            _render(chart)

    assert plt.get_fignums() == opened_before
    assert not [w for w in caught if "not yet supported" in str(w.message)]


def test_a_figure_built_lazily_and_cached_stays_accessible(fake_session):
    """The ``@reactive.calc`` shape: built on the first flush, reused after.

    This figure IS new during the first render, so anything that treats
    "not open beforehand" as "safe to forget" will drop maidr's record of
    it. Every later flush then renders a static image instead of a chart,
    with only a server-side warning to show for it -- which is the failure
    this whole cleanup path exists to avoid, not to cause.
    """
    cached = []

    @render_maidr
    def chart():
        if not cached:
            cached.append(_bar_axes())
        return cached[0]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        documents = [
            _iframe_document(fake_session, _render(chart)["html"]) for _ in range(3)
        ]

    assert not [w for w in caught if "not yet supported" in str(w.message)]
    for index, document in enumerate(documents):
        # ``subplots`` is a key of the MAIDR schema, so it is present only
        # while maidr still holds the data it extracted at plotting time.
        # The static-image fallback carries an ``<img>`` and no schema.
        assert "subplots" in document, f"render {index} lost the MAIDR schema"
        assert "<img" not in document, f"render {index} fell back to an image"


# ---------------------------------------------------------------------------
# Import-time errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ModuleNotFoundError("No module named 'shiny'", name="shiny"), "maidr[shiny]"),
        # The skew this repository actually hit: shiny installed, but its
        # import chain reaches an htmltools too old to satisfy it.
        (
            ImportError("cannot import name 'TagifiedTag' from 'htmltools'"),
            "version skew",
        ),
    ],
)
def test_import_error_advice_matches_the_failure(monkeypatch, error, expected):
    """ "Install the extra" is wrong advice for a package already installed."""
    import builtins
    import importlib

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name.startswith("shiny"):
            raise error
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    monkeypatch.delitem(sys.modules, "maidr.widget.shiny", raising=False)

    with pytest.raises(ImportError, match=re.escape(expected)):
        importlib.import_module("maidr.widget.shiny")


# ---------------------------------------------------------------------------
# Not holding the event loop (#454)
# ---------------------------------------------------------------------------


def test_the_render_runs_off_the_event_loop(fake_session, monkeypatch):
    """The whole point of #454: ``maidr.render`` must not run on the loop.

    Asserted by identity of the running thread rather than by timing, which
    would be a flake on a loaded machine. ``asyncio.run`` drives the loop on
    *this* thread, so the render must land on a different one.

    Driven through ``_render`` rather than as an ``async def`` test: this
    suite has no ``pytest-asyncio``, and an ``async def`` here is collected,
    silently **skipped**, and reported as a pass. The first version of this
    test was exactly that -- it did not fail when the render was put back on
    the loop, because it never ran.
    """
    import maidr.widget.shiny as shiny_module

    loop_thread = threading.get_ident()
    seen: list[int] = []

    real_render = shiny_module.maidr.render

    def spy(value, **kwargs):
        seen.append(threading.get_ident())
        return real_render(value, **kwargs)

    monkeypatch.setattr(shiny_module.maidr, "render", spy)

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    try:

        @render_maidr
        def chart():
            return ax

        _render(chart)
    finally:
        plt.close(fig)

    assert seen, "the render never ran"
    assert loop_thread not in seen, (
        "maidr.render ran on the event loop's thread; every other session "
        "on that worker is blocked for its full duration"
    )


def test_two_renders_of_one_figure_do_not_overlap(monkeypatch):
    """The scenario this whole change exists to make safe.

    ``tests/util/test_figure_lock.py`` checks that ``figure_lock`` hands
    back matching objects; none of them shows that two renders actually
    serialize through this door. That is the one thing a race here would
    break, so it is worth exercising end to end.

    The stub is ``Maidr._build_html_tag`` rather than ``maidr.render``
    because since #532 the lock is taken in ``_create_html_tag``, one
    level above the body: stubbing ``render`` would replace the lock
    along with the work and leave this asserting nothing.

    Detects **overlap** rather than measuring duration, so it cannot flake
    into a false pass on a loaded machine: if the lock works, the second
    render cannot enter while the first is inside, at any speed. The sleep
    only widens the window a broken lock would have to miss.

    Overlapping renders are not a theoretical concern. ``savefig`` writes
    ``fig.dpi`` for the duration of the write, so the loser of that race
    emits a valid SVG of the whole chart at the wrong scale -- measured at
    460.8x345.6 for a 640x480 figure, on 1 of 6 concurrent attempts.
    """
    from maidr.core.maidr import Maidr

    inside = 0
    overlapped = False
    bookkeeping = threading.Lock()

    def slow_build(self, *args, **kwargs):
        nonlocal inside, overlapped
        with bookkeeping:
            inside += 1
            if inside > 1:
                overlapped = True
        time.sleep(0.05)
        with bookkeeping:
            inside -= 1
        return "rendered"

    monkeypatch.setattr(Maidr, "_build_html_tag", slow_build)

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    try:
        renderer = render_maidr(lambda: ax)
        workers = [
            # Daemon, so that the deadlock this test exists to catch fails
            # the test rather than wedging the interpreter at shutdown: a
            # timed-out join leaves the thread alive and still holding the
            # figure's lock.
            threading.Thread(target=renderer._render_off_loop, args=(ax,), daemon=True)
            for _ in range(4)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            # Bounded: an unbounded join turns a broken lock into a hung
            # suite rather than a failed test (#506).
            worker.join(timeout=60)
            assert not worker.is_alive(), "a render deadlocked on the lock"
    finally:
        plt.close(fig)

    assert not overlapped, (
        "two renders of the same figure ran at once; they race on fig.dpi "
        "and one of them emits the chart at the wrong scale"
    )


def test_a_value_that_resolves_to_no_figure_still_renders(fake_session, monkeypatch):
    """A value that names no matplotlib figure still renders.

    Both shapes are covered because they are not the same shape: a foreign
    figure -- plotly, altair -- **returns** ``None`` from ``get_axes`` and
    never raises, while an empty container raises ``StopIteration``. The
    Shiny door used to resolve the figure itself, to decide which lock to
    take, and had to survive both; since #532 the lock is taken in the core
    render path by the figure it already holds, and neither shape reaches
    a matplotlib render at all. This pins that they still come back with a
    chart rather than an exception.
    """
    import maidr.widget.shiny as shiny_module

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    monkeypatch.setattr(shiny_module.maidr, "render", lambda value, **kw: "rendered")
    monkeypatch.setattr(shiny_module, "_check_supported", lambda value, name: None)
    try:
        for resolver, label in (
            (lambda value: None, "returns None, as a foreign figure does"),
            (lambda value: next(iter([])), "raises, as an empty container does"),
        ):
            monkeypatch.setattr(
                shiny_module.FigureManager, "get_axes", staticmethod(resolver)
            )

            @render_maidr
            def chart():
                return ax

            assert _render(chart) is not None, label
    finally:
        plt.close(fig)


def test_two_different_figures_rendering_at_once_keep_their_selectors():
    """The per-figure lock does not cover process-global highlight state.

    ``HighlightContextManager`` carries a render's element-to-selector
    wiring, and the artist ``draw`` methods and ``XMLWriter.start`` are
    patched *class-wide*, so every render in the process reads it while
    ``savefig`` walks its figure. A lock keyed by figure deliberately does
    not serialize **distinct** figures -- that parallelism is the point of
    rendering off the loop -- so nothing stopped two renders from
    overwriting each other's wiring.

    Measured with that state as plain class attributes: four concurrent
    renders of distinct figures went from 61 selectors each to
    ``[7, 1, 1, 1]``. Valid SVGs, with the interactive layer silently
    gone -- and only on concurrent traffic, so it would not reproduce from
    a bug report.

    Counts selectors rather than comparing whole documents, because ids
    are per-render uuids; the count is what goes missing.
    """
    from maidr.core.figure_manager import FigureManager

    def build():
        figure, axes = plt.subplots()
        axes.bar([str(i) for i in range(20)], list(range(1, 21)))
        return figure

    def selectors(figure):
        html = FigureManager.get_maidr(figure)._create_html_tag(
            use_iframe=False, use_cdn=True
        )
        return len(re.findall(r'maidr="[^"]+"', str(html)))

    figures = [build() for _ in range(4)]
    try:
        alone = [selectors(figure) for figure in figures]
        assert all(count == alone[0] for count in alone), alone

        together: dict[int, int] = {}

        def render(index, figure):
            together[index] = selectors(figure)

        workers = [
            threading.Thread(target=render, args=(index, figure), daemon=True)
            for index, figure in enumerate(figures)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=60)
            assert not worker.is_alive(), "a render deadlocked"

        assert [together[i] for i in range(len(figures))] == alone, (
            "a concurrent render of another figure stripped this one's "
            "selectors; the highlight wiring is process-global state"
        )
    finally:
        plt.close("all")


#: Attributes that differ between two renders of the same chart by design --
#: fresh uuids per layer, and the timestamp matplotlib stamps into the SVG.
_VOLATILE_IN_SVG = re.compile(
    r'(\bid="[^"]*"|url\(#[^)]*\)|<dc:date>[^<]*</dc:date>'
    r'|xlink:href="#[^"]*"|maidr="[^"]*")'
)


@pytest.mark.parametrize("hand_back", ["axes", "figure"])
def test_concurrent_renders_of_one_figure_agree(hand_back):
    """Concurrent renders of one figure must produce the same chart.

    Narrower than it first looks, and worth stating plainly:
    ``test_two_renders_of_one_figure_do_not_overlap`` above already fails
    without the lock, so this is not filling an unguarded gap. That one
    monkeypatches ``maidr.render`` to a sleeping stub, so it proves the
    lock *excludes* but cannot see what the exclusion is protecting. This
    runs the real render and asserts the consequence.

    ``savefig`` writes ``fig.dpi`` for its duration and restores it
    afterwards, so two renders of the **same** figure at once race on one
    mutable attribute and the loser draws the whole chart at the other
    call's dpi (#454). Distinct figures do not race; that is why the lock
    is per figure rather than process-wide.

    The failure is the kind this project treats as worst: not garbled
    markup and not an exception, but a complete, well-formed SVG of the
    same chart at the wrong size. Geometry is what the highlight overlay
    and the tactile export are positioned against, so a chart rendered at
    72% scale is wrong in the modality a sighted reviewer checks least.

    Asserted as agreement between renders rather than against a fixed size,
    since the wrong-dpi output is internally consistent -- it is only wrong
    relative to what every other render produced.

    The barrier synchronises the *start*, not the duration. On a runner
    slow or oversubscribed enough that each ``savefig`` finishes before
    the next thread is scheduled, this would pass with a broken lock --
    a false negative rather than a flaky failure, so it would show up as
    quietly reduced coverage rather than as CI noise. Measured 8 of 8
    detections here with the lock removed; the sibling test above detects
    overlap regardless of speed and is the one to trust on a bad day.

    Scope: **geometry, not data.** ``_VOLATILE_IN_SVG`` strips every
    ``maidr="..."`` attribute, and the one on the root ``<svg>`` carries
    the whole embedded schema, so a race that scrambled the announced
    values without moving a coordinate would pass this. The bug it guards
    is about ``fig.dpi``, which lives entirely in the ``<path d="...">``
    data the regex leaves alone.

    Measured 10 of 10 runs mismatching with the lock stubbed out and 10 of
    10 identical with it, so this runs in CI rather than under
    ``--run-benchmark``.

    The renders start from a barrier rather than from whenever each thread
    happens to be scheduled. Review raised the right worry -- a quiet or
    single-core runner could let six staggered renders complete without
    ever landing inside each other's ``dpi`` window, which would reduce
    this to a no-op that still passes. Raising the chart size does not
    address that (detection was 8 of 8 at 30, 100 and 200 bars alike, so
    the margin was never the variable); starting them together does,
    because it does not depend on the scheduler being busy.

    Parametrised over what the render function returns because the two
    used to be different: a ``Figure`` resolves to a *list* of axes, and
    the old resolver read ``.figure`` off that list, got ``None``, and
    took a fresh unshared lock -- so an app whose render function returned
    ``fig`` rather than ``ax`` raced exactly as if there were no lock. Both
    now resolve to the same figure, and so to the same lock.
    """
    fig, ax = plt.subplots()
    ax.bar([str(i) for i in range(30)], list(range(30)))
    returned = ax if hand_back == "axes" else fig
    renderer = render_maidr(lambda: returned)

    # Appended from several threads without a lock, which is safe because
    # `list.append` is atomic under the GIL, and read only after every
    # worker has been joined. Written down because this file documents its
    # other concurrency decisions.
    outputs: list[str] = []
    failures: list[Exception] = []
    # One constant for the barrier and the thread count, because they must
    # agree: a barrier expecting more arrivals than there are threads waits
    # forever (#506).
    racers = 6
    start = threading.Barrier(racers)

    def render_once():
        try:
            start.wait(timeout=10)
            rendered = str(renderer._render_off_loop(returned))
            outputs.append(_VOLATILE_IN_SVG.sub("", rendered))
        except Exception as exc:  # reported below, not swallowed
            # Narrow enough to cover everything expected --
            # `BrokenBarrierError` is a `RuntimeError` -- while leaving
            # `KeyboardInterrupt` and `SystemExit` free to end the thread.
            failures.append(exc)

    workers = [threading.Thread(target=render_once, daemon=True) for _ in range(racers)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            # Longer than the barrier's own deadline above, so a thread
            # still legitimately waiting there is not reported as a
            # deadlocked render. A healthy run of this test is ~1.7s.
            worker.join(timeout=30)
            assert not worker.is_alive(), "a render deadlocked on the lock"

        assert not failures, f"a render raised: {failures[:2]}"
        assert len(outputs) == len(workers)
        assert len(set(outputs)) == 1, (
            "concurrent renders of one figure disagreed; one of them drew "
            "the chart at another render's dpi, which produces a valid SVG "
            "at the wrong scale rather than an error"
        )
    finally:
        plt.close(fig)
