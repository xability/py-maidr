"""A chart written into the page a Quarto render builds, rather than an iframe.

In a document Quarto renders with its Jupyter engine, a matplotlib or seaborn
chart used to reach the page in an iframe of its own, as in a notebook. When
the render builds a web page -- an ``html`` document, website, book or
dashboard, or a ``revealjs`` deck -- it is now written into the page itself,
as r-maidr writes an R chart into the same pages (#895), and the page loads
``maidr.js`` once for every chart on it.

The frame gave a chart a document of its own, and the page gives it none of
that, so this module carries it over:

* **Ids.** Every chart had its ids to itself. matplotlib numbers its groups
  (``figure_1``, ``axes_1``, ``text_3``) and names its glyphs alike in every
  figure, and a user's ``gid`` is whatever they called it, so two charts on
  one page share ids, and a selector naming one finds the other chart's
  marks. Each chart's ids get a suffix of their own, and everything that
  names them follows (:class:`InlineScope`).
* **CSS.** matplotlib's ``<style>`` restyles every element of the page once
  it is in it, and its ``<metadata>`` is text a reveal.js deck reads aloud
  and a website indexes for search. The style is scoped to the chart and the
  metadata dropped.
* **Keys, focus, name and colours.** ``maidr/assets/inline.js`` and
  ``inline.css`` keep the page's shortcuts away from a chart while the focus
  is in it, draw its focus ring, name it, and keep high contrast to it.
* **The runtime.** Quarto puts require.js on these pages, and the UMD
  ``maidr.js`` hands itself to it and never runs unless kept from it; see
  :func:`loader_js`.

A notebook, Shiny, Streamlit, Gradio, Flask and a Pyodide page keep their
iframes: in each, a key pressed in an inline chart reaches a shortcut of the
host that nothing on the page can hold off (#108, #457, #460).
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import re
import uuid
from functools import lru_cache
from importlib import resources
from typing import Any, Iterator, Literal

from htmltools import HTML, Tag, tags

from maidr.util.environment import Environment

_SVG = "{http://www.w3.org/2000/svg}"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

#: The shape of every id py-maidr mints, ``str(uuid.uuid4())``.
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

#: An id py-maidr minted, which is unique on any page already: the svg's own,
#: which is the schema's, and a group's ``maidr-<uuid>``. Matched whole, so
#: a user's ``gid`` that only contains a uuid is still made the chart's own.
_MINTED_ID = re.compile(rf"(?:maidr-(?:[a-z]+-)*)?{_UUID.pattern}")

#: ``url(#id)``, quoted or not, as an attribute or a style declaration says it.
_URL = re.compile(r"""url\(\s*(['"]?)\s*#([^'")\s]+)\s*\1\s*\)""")

#: ``[id='x']`` and ``[id="x"]``: how py-maidr's selectors name a group.
_ID_ATTRIBUTE = re.compile(r"""\[id=(['"])(.*?)\1\]""")

#: ``#x``, the other way a selector can name an element. It also matches a
#: colour in an attribute test, ``[fill="#ff0000"]``, which is left alone
#: unless it happens to be one of the chart's ids; py-maidr's selectors test
#: none.
_ID_HASH = re.compile(r"#((?:[A-Za-z0-9_-]|\\.)+)")

#: An exact test of an id, or of py-maidr's ``maidr`` attribute, in a selector:
#: ``[id='x']``, ``[maidr='x']`` or ``#x``. ``[id^='x']`` is not one.
_ANCHOR = re.compile(r"""\[(?:id|maidr)=(['"])(.*?)\1\]|#((?:[A-Za-z0-9_-]|\\.)+)""")

#: The SVG elements whose text, whitespace included, is drawn.
_TEXT_ELEMENTS = frozenset(
    f"{_SVG}{tag}" for tag in ("text", "tspan", "textPath", "title", "desc")
)

#: The attributes that hold a list of ids.
_ARIA_ID_LISTS = (
    "aria-activedescendant",
    "aria-controls",
    "aria-describedby",
    "aria-details",
    "aria-errormessage",
    "aria-flowto",
    "aria-labelledby",
    "aria-owns",
)

#: Set while a chart is rendered as a document of its own, which a page
#: never sees; see :func:`standalone_document`.
_STANDALONE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "maidr_standalone_document", default=False
)


#: Set while ``show()`` renders a chart it is about to display.
_SHOWING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "maidr_showing", default=False
)


@contextlib.contextmanager
def showing() -> Iterator[None]:
    """Render charts that are displayed in the page as soon as they are made.

    ``show()`` displays what it renders; ``render()`` returns it, and its
    caller may never put it in the page. Only a chart rendered here may
    count as the one that put the bundle in the page for the rest of a
    render (``maidr.api._quarto_stash``).
    """
    token = _SHOWING.set(True)
    try:
        yield
    finally:
        _SHOWING.reset(token)


def is_showing() -> bool:
    """Whether the chart being rendered is displayed as soon as it is made."""
    return _SHOWING.get()


class InlineUnsupported(Exception):
    """A chart's SVG holds something that cannot be scoped to it on a page."""


@contextlib.contextmanager
def standalone_document() -> Iterator[None]:
    """Render charts as documents of their own, whatever the environment.

    Streamlit, Gradio and an MLflow artifact take a chart as the HTML of a
    frame or page of its own (:mod:`maidr.widget._document`). Such a
    chart is never part of the page a Quarto render builds, even when one is
    made during a render, so it neither carries the bundle for that page nor
    is written as one of its charts.
    """
    token = _STANDALONE.set(True)
    try:
        yield
    finally:
        _STANDALONE.reset(token)


def in_quarto_render(use_iframe: bool) -> bool:
    """Whether a chart rendered now becomes a cell output of a Quarto render.

    Parameters
    ----------
    use_iframe : bool
        False for a document of its own (``save_html``), which is not a cell
        output wherever it is made.

    Returns
    -------
    bool
        True in the kernel of a Quarto render, outside the hosts that keep
        their own iframe and outside :func:`standalone_document`.
    """
    return (
        use_iframe
        and not _STANDALONE.get()
        and Environment.is_quarto()
        and Environment.is_notebook()
        and not Environment.is_flask()
        and not Environment.is_shiny()
        and not Environment.is_pyodide_page()
    )


def inline_applies(use_iframe: bool) -> bool:
    """Whether a chart rendered now is written into the page, not a frame.

    Parameters
    ----------
    use_iframe : bool
        As for :func:`in_quarto_render`.

    Returns
    -------
    bool
        True for a cell output of a Quarto render that builds a web page.
    """
    return in_quarto_render(use_iframe) and Environment.is_quarto_page()


def _split_selector(selector: str) -> list[str]:
    """Split a selector list at its own commas, not those inside ``()`` or ``[]``."""
    parts: list[str] = []
    depth = 0
    quote = ""
    start = 0
    for index, char in enumerate(selector):
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(selector[start:index])
            start = index + 1
    parts.append(selector[start:])
    return parts


class InlineScope:
    """Makes one chart's SVG safe to share a page with other charts.

    Every id that is not one of py-maidr's uuids gets the suffix
    ``-m<12 hex digits>``, fresh per chart, and every reference to it
    follows: ``url(#id)``, ``href="#id"``, ARIA id lists, and the selectors
    in the chart's schema. A suffix rather than r-maidr's prefix, because
    maidr.js finds a matplotlib panel by ``g[id^="axes_"]``, and a panel
    whose id no longer starts so loses its outline. The suffix never reads
    as axis furniture to maidr.js's tactile renderer either: that splits an
    id into words, and none of its words starts with ``m``.

    A selector that names nothing unique to the chart once that is done --
    ``g[id^='maidr-'] path``, the fallback of a violin or regression layer
    with no group of its own -- is scoped to the chart's own ``<svg>``, so it
    cannot find another chart's marks.

    The SVG's ``<metadata>`` is dropped, and its ``<style>`` moves out of it,
    each rule scoped to the chart by a class of its own (:attr:`css`).
    """

    def __init__(self, name: str) -> None:
        #: What the chart is called until maidr.js names it.
        self.name = name
        self.key = "m" + uuid.uuid4().hex[:12]
        #: The chart's own class, which its lifted ``<style>`` is scoped to.
        self.css_class = f"maidr-inline-{self.key}"
        #: The scoped rules of the SVG's ``<style>``; "" when it had none.
        self.css = ""
        #: The ``<svg>``'s id, which is the schema's.
        self.svg_id = ""
        self._renamed: dict[str, str] = {}
        #: Why the chart could not be scoped, once :meth:`scope` refused it.
        self.refused: InlineUnsupported | None = None

    def scope(self, svg: Any, schema: dict) -> dict:
        """Scope ``svg`` in place and return the schema that goes with it.

        Everything is checked before anything is changed, so an SVG this
        refuses is left exactly as it was, for the iframe to carry.

        Parameters
        ----------
        svg : lxml.etree._Element
            The chart's root ``<svg>``, its id already the schema's.
        schema : dict
            The schema the SVG's ``maidr`` attribute is written from.

        Returns
        -------
        dict
            ``schema`` with its selectors following the renamed ids.

        Raises
        ------
        InlineUnsupported
            When the SVG holds a ``<script>`` or ``<foreignObject>``, or a
            ``<style>`` whose rules cannot be scoped.
        """
        for tag in ("script", "foreignObject"):
            if next(svg.iter(f"{_SVG}{tag}"), None) is not None:
                raise InlineUnsupported(f"the chart's SVG holds a <{tag}>")
        styles = list(svg.iter(f"{_SVG}style"))
        style_text = "\n".join(style.text or "" for style in styles)

        self.svg_id = svg.get("id") or ""
        self._renamed = {
            element_id: f"{element_id}-{self.key}"
            for element_id in (element.get("id") for element in svg.iter())
            if element_id and not _MINTED_ID.fullmatch(element_id)
        }
        # Before anything changes: this is the one check left that can refuse.
        self.css = self._scope_css(style_text)

        for element in list(svg.iter(f"{_SVG}metadata")) + styles:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
        for element in svg.iter():
            # matplotlib's indentation is text in the page, which a site's
            # search indexes: about 2 KB of whitespace a chart. The text of
            # a label, which svg.fonttype "none" writes, is kept. So are
            # the comments it writes each label's text in, which no search
            # reads, but not the whitespace after them.
            parent = element.getparent()
            if element.tail is not None and not element.tail.strip():
                if parent is None or parent.tag not in _TEXT_ELEMENTS:
                    element.tail = None
            if not isinstance(element.tag, str):
                continue
            self._rename(element)
            if element.tag not in _TEXT_ELEMENTS:
                if element.text is not None and not element.text.strip():
                    element.text = None

        svg.set(
            "class",
            " ".join(
                filter(None, [svg.get("class"), "maidr-inline-svg", self.css_class])
            ),
        )
        # Hidden from the start: a deck reads a slide's text aloud, and a
        # chart drawn with svg.fonttype "none" has its labels as text. The
        # wrapper is named in its place until maidr.js names the chart.
        svg.set("aria-hidden", "true")
        return self._scope_value(schema)

    def _rename(self, element: Any) -> None:
        renamed = self._renamed
        element_id = element.get("id")
        if element_id in renamed:
            element.set("id", renamed[element_id])
        for attribute, value in list(element.attrib.items()):
            if attribute == "maidr":
                continue
            if "url(" in value:
                element.set(attribute, _URL.sub(self._url, value))
            if attribute in ("href", _XLINK_HREF) and value.startswith("#"):
                element.set(attribute, "#" + renamed.get(value[1:], value[1:]))
            elif attribute in _ARIA_ID_LISTS:
                element.set(
                    attribute,
                    " ".join(renamed.get(ref, ref) for ref in value.split()),
                )

    def _url(self, match: re.Match) -> str:
        quote, target = match.group(1), match.group(2)
        return f"url({quote}#{self._renamed.get(target, target)}{quote})"

    def _rename_in_selector(self, selector: str) -> str:
        renamed = self._renamed

        def attribute(match: re.Match) -> str:
            quote, value = match.group(1), match.group(2)
            return f"[id={quote}{renamed.get(value, value)}{quote}]"

        def hash_id(match: re.Match) -> str:
            value = match.group(1)
            return "#" + renamed.get(value, value)

        return _ID_HASH.sub(hash_id, _ID_ATTRIBUTE.sub(attribute, selector))

    def _anchored(self, part: str) -> bool:
        """Whether a selector names an element by a value only this chart has.

        That is an id, or py-maidr's ``maidr`` attribute, tested for an exact
        value that py-maidr minted or that carries this chart's suffix. A
        uuid elsewhere in the selector -- a prefix test, another attribute --
        does not make it the chart's own.
        """
        for match in _ANCHOR.finditer(part):
            value = match.group(2) if match.group(2) is not None else match.group(3)
            if _UUID.search(value) or value.endswith(f"-{self.key}"):
                return True
        return False

    def _scope_selector(self, selector: str) -> str:
        parts = []
        for part in _split_selector(self._rename_in_selector(selector)):
            stripped = part.strip()
            if stripped and not self._anchored(stripped):
                part = f'[id="{self.svg_id}"] {stripped}'
            parts.append(part)
        return ",".join(parts)

    def _scope_value(self, value: Any) -> Any:
        """The schema with every ``selector``/``selectors`` value scoped."""
        if isinstance(value, dict):
            return {
                key: self._scope_selectors(item)
                if key in ("selector", "selectors")
                else self._scope_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._scope_value(item) for item in value]
        return value

    def _scope_selectors(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._scope_selector(value)
        if isinstance(value, list):
            return [self._scope_selectors(item) for item in value]
        if isinstance(value, dict):
            return {key: self._scope_selectors(item) for key, item in value.items()}
        return value

    def _scope_css(self, text: str) -> str:
        """The rules of the SVG's ``<style>``, each scoped to this chart."""
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        if "@" in text:
            raise InlineUnsupported("the chart's <style> holds an at-rule")
        rules = []
        position = 0
        for match in re.finditer(r"([^{}]*)\{([^{}]*)\}", text):
            if text[position : match.start()].strip():
                break
            position = match.end()
            scoped = []
            for part in _split_selector(match.group(1)):
                part = self._rename_in_selector(part.strip())
                if not part:
                    continue
                if part == "*":
                    scoped.append(f".{self.css_class}")
                scoped.append(f".{self.css_class} {part}")
            if scoped:
                body = _URL.sub(self._url, match.group(2).strip())
                rules.append(f"{', '.join(scoped)} {{{body}}}")
        if text[position:].strip():
            raise InlineUnsupported("the chart's <style> could not be read")
        return "\n".join(rules)


@lru_cache(maxsize=None)
def _asset(name: str) -> str:
    """One of ``maidr/assets/inline.{js,css}``, its comments and indents dropped.

    Every chart carries them, so that a chart whose cell hides its output
    takes nothing from the charts after it; they run once per page.
    """
    text = resources.files("maidr").joinpath("assets", name).read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line and not line.startswith("//"))


#: How the loader says it could not load ``maidr.js``.
_REPORT = """
  function fail(why) {
    window.__maidrInlineLoader = false;
    console.error('[maidr] The chart loaded but its runtime did not: ' + why +
      '. Re-render with use_cdn=False to carry maidr.js in the page, which ' +
      'works without network access.');
  }
"""

#: Runs the bundled source a chart output stashed on the page.
_FROM_STASH = """
  function fromStash(why) {
    %(locale)s
    var source = window.__maidrJsSource;
    if (!source) { fail(why); return; }
    var css = window.__maidrMathCssSource;
    if (css) {
      var style = document.createElement('style');
      style.textContent = css;
      document.head.appendChild(style);
      // maidr.js looks for a <link> with this attribute before it fetches
      // maidr-math.css itself, which it cannot here.
      var mark = document.createElement('link');
      mark.setAttribute('data-maidr-math', '');
      document.head.appendChild(mark);
    }
    var script = document.createElement('script');
    script.text = source;
    noAmd(script);
    document.head.appendChild(script);
  }
"""

#: Loads ``maidr.js`` by URL.
_FROM_URL = """
  function fromUrl(url, onError) {
    var script = document.createElement('script');
    script.src = url;
    script.onerror = onError;
    noAmd(script);
    document.head.appendChild(script);
  }
"""


def loader_js(
    use_cdn: bool | Literal["auto"], cdn_url: str | None, locale_fallback: str
) -> str:
    """The script, in every chart, that loads ``maidr.js`` for the page once.

    Every chart carries one, so a chart whose cell hides its output takes
    nothing from the charts after it; the first that runs loads
    ``maidr.js``, and the rest find it there. ``maidr.js`` binds every chart
    on the page itself, then and as more arrive, so nothing is called per
    chart.

    Parameters
    ----------
    use_cdn : bool or {"auto"}
        ``False`` runs the stashed bundle. ``True`` loads ``cdn_url``.
        ``"auto"`` loads ``cdn_url`` and runs the stashed bundle when that
        fails.
    cdn_url : str or None
        The URL ``maidr.js`` is loaded from; unused under ``False``.
    locale_fallback : str
        The statement that points the bundled copy at its locale packs, run
        before it under ``"auto"``.

    Returns
    -------
    str
        The script's source.
    """
    body = [
        "(function () {",
        # A copy of an output already on the page is given ids of its own
        # first; see inline.js. This script comes after the chart's svg.
        "  if (window.__maidrInlineClaim) "
        "window.__maidrInlineClaim(document.currentScript);",
        "  if (window.maidrLive || window.__maidrInlineLoader) return;",
        "  window.__maidrInlineLoader = true;",
        "  var noAmd = window.__maidrInlineWithoutAmd || function () {};",
        _REPORT,
        _FROM_STASH % {"locale": "" if use_cdn is False else locale_fallback},
    ]
    url = json.dumps(cdn_url or "").replace("<", "\\u003c")
    if use_cdn is False:
        body.append("  fromStash('the page has no copy of the bundle');")
    else:
        # Under ``True`` too: a page holds a copy only because one of its
        # charts asked for it, and that chart must not be left without it by
        # a chart before it that loads from the CDN alone.
        body.append(_FROM_URL)
        body.append(
            f"  fromUrl({url}, function () {{ fromStash('it did not load from ' + "
            f"{url} + ' and the page has no copy of the bundle'); }});"
        )
    body.append("})();")
    return "\n".join(body)


def chart_tag(
    svg: HTML,
    scope: InlineScope,
    chart_title: str | None,
    *,
    before_runtime: list[Any],
    loader: str,
) -> Tag:
    """One chart, as the single output a Quarto cell writes into the page.

    One output, not several: Quarto makes a figure of each output of a
    ``fig-`` cell, and a script displayed on its own became a subfigure that
    took the caption.

    Parameters
    ----------
    svg : htmltools.HTML
        The scoped SVG.
    scope : InlineScope
        What scoped it.
    chart_title : str or None
        The chart's title, which describes it once maidr.js names it.
    before_runtime : list
        Tags that must run before ``maidr.js``: the configuration it reads
        when it loads, and the stashed bundle.
    loader : str
        :func:`loader_js`.

    Returns
    -------
    htmltools.Tag
        The chart's ``<div class="maidr-inline">``.
    """
    title = (chart_title or "").strip()
    children: list[Any] = [
        # Marked so that inline.js keeps one copy of it in the page's head.
        tags.style(HTML(_asset("inline.css")), **{"data-maidr-inline-css": ""})
    ]
    if scope.css:
        children.append(tags.style(HTML(scope.css)))
    children.append(svg)
    if title:
        children.append(
            tags.span(
                title,
                id=f"{scope.svg_id}-title",
                class_="maidr-inline-title",
                hidden=True,
            )
        )
    children.append(tags.script(HTML(_asset("inline.js"))))
    children.extend(child for child in before_runtime if child is not None)
    children.append(tags.script(HTML(loader)))
    # Named until maidr.js names the chart; inline.js takes the name off then.
    return tags.div(
        *children,
        class_="maidr-inline",
        role="img",
        aria_label=scope.name,
        **{"data-maidr-inline": ""},
    )
