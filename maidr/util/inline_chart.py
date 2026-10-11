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
* **Its size.** A chart is given the box and size of the figure Quarto
  shows in its place without maidr (:func:`size_like_plain_figure`), and
  ``inline.js`` fills a dashboard card with it as Quarto fills one with
  that figure.

A notebook, Shiny, Streamlit, Gradio, Flask and a Pyodide page keep their
iframes: in each, a key pressed in an inline chart reaches a shortcut of the
host that nothing on the page can hold off (#108, #457, #460).
"""

from __future__ import annotations

import contextlib
import contextvars
import io
import json
import logging
import re
import uuid
from functools import lru_cache
from importlib import resources
from typing import Any, Iterator, Literal

from htmltools import HTML, Tag, tags

from maidr.util.environment import Environment

_logger = logging.getLogger(__name__)

_SVG = "{http://www.w3.org/2000/svg}"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

#: ``url(#id)``, quoted or not, as an attribute or a style declaration says it.
_URL = re.compile(r"""url\(\s*(['"]?)\s*#([^'")\s]+)\s*\1\s*\)""")

#: ``[id='x']`` and ``[maidr='x']``, quoted either way: how py-maidr's
#: selectors name a group, by its id or by the mark py-maidr gives a layer's.
_ID_ATTRIBUTE = re.compile(r"""\[(id|maidr)=(['"])(.*?)\2\]""")

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


def in_standalone_document() -> bool:
    """Whether charts are being rendered as documents of their own just now.

    See :func:`standalone_document`.
    """
    return _STANDALONE.get()


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


#: The figure formats IPython shows as a raster, which the page shows a dot
#: to a CSS pixel (``retina`` at half its dots): a figure ``w`` inches wide
#: at ``fig-dpi`` is ``w * fig-dpi`` pixels wide there.
_RASTER_FORMATS = frozenset({"retina", "png", "jpeg"})

#: CSS pixels to the inch, which an SVG figure, sized in points, is shown at.
_CSS_PX_PER_INCH = 96.0

#: SVG user units, which matplotlib's are points, to the inch.
_POINTS_PER_INCH = 72.0


def size_like_plain_figure(
    fig: Any, svg: Any, shown_as: tuple[str | None, dict[str, Any]] | None = None
) -> None:
    """Give a chart's ``<svg>`` the size and shape the page gives a plain figure.

    A Quarto render shows a plain matplotlib figure through the kernel's
    display formatter, which saves it with ``InlineBackend.print_figure_kwargs``:
    ``bbox_inches="tight"`` by default, so the figure is cut to what is drawn
    and padded by ``savefig.pad_inches``, growing past the canvas where an
    axis label or a legend lies outside it. A raster (``fig-format``
    ``retina``, the default, ``png`` or ``jpeg``) is shown at the figure's
    dpi, which Quarto sets to ``fig-dpi``, in CSS pixels to the inch; an
    ``svg`` or ``pdf`` one at 96. matplotlib's SVG is the whole canvas at 96
    pixels to the inch: another size and shape than the plain figure, and
    without what is drawn outside the canvas.

    Only the root's ``viewBox``, ``width`` and ``height`` change, so the
    user-space coordinates every selector, highlight and
    :func:`maidr.util.svg_utils.data_to_svg_coords` point is written in stay
    as they are. Where the box grows past the canvas it is painted in the
    colour the SVG painted the canvas, as the plain figure is. A formatter
    that does not cut the figure (``bbox_inches=None``) shows the canvas,
    and one given a box of its own that box; its ``dpi`` and ``pad_inches``
    count as they do for the plain figure.

    Left as matplotlib wrote it when the box cannot be measured, or the SVG
    is not the whole canvas in points (``savefig.bbox`` cut it already): its
    coordinates would not be the figure's then.

    A notebook shows a plain figure the same way, and a chart in its frame
    is sized here too, from what :func:`maidr.util.notebook_figure.notebook_figure_format`
    reads of the kernel's inline backend.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure the SVG was saved from, after the save.
    svg : lxml.etree._Element
        Its root ``<svg>``.
    shown_as : tuple of (str or None, dict), optional
        The format the plain figure is shown in and the ``savefig``
        arguments it is shown with, as IPython's ``print_figure`` takes them.
        By default those of the kernel's figure formatter, in the page of a
        Quarto render.
    """
    try:
        width_in, height_in = (float(v) for v in fig.get_size_inches())
        canvas = (0.0, 0.0, width_in * _POINTS_PER_INCH, height_in * _POINTS_PER_INCH)
        if not _is_view_box(svg.get("viewBox"), canvas):
            return
        figure_format, keywords = (
            _plain_figure_format() if shown_as is None else shown_as
        )
        box = _shown_box(fig, figure_format, keywords)
        if box is None:
            x0, y1, width, height = 0.0, height_in, width_in, height_in
        else:
            x0, y1, width, height = box.x0, box.y1, box.width, box.height
        values = (x0, y1, width, height)
        if not all(v == v and abs(v) != float("inf") for v in values):
            return
        if not (width > 0 and height > 0):
            return
        per_inch = _px_per_inch(fig, figure_format, keywords)
        # In points, with y down from the canvas's top as SVG has it.
        view = (
            x0 * _POINTS_PER_INCH,
            (height_in - y1) * _POINTS_PER_INCH,
            width * _POINTS_PER_INCH,
            height * _POINTS_PER_INCH,
        )
        backdrop = _backdrop(fig, view, canvas)
    except Exception:
        # The chart works at matplotlib's size; a measurement must never be
        # why a render fails. Logged, for whoever asks why it kept that size.
        _logger.debug(
            "maidr: kept the chart at matplotlib's size; measuring the plain "
            "figure's failed",
            exc_info=True,
        )
        return
    svg.set("viewBox", " ".join(_number(v) for v in view))
    svg.set("width", f"{_number(width * per_inch)}px")
    svg.set("height", f"{_number(height * per_inch)}px")
    if backdrop is not None:
        svg.insert(0, svg.makeelement(f"{_SVG}path", backdrop))


def _number(value: float) -> str:
    """A length for an SVG attribute: three decimals at most, no ``-0``."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _is_view_box(value: str | None, expected: tuple[float, ...]) -> bool:
    """Whether a ``viewBox`` attribute is ``expected``, to within a hundredth."""
    try:
        numbers = [float(part) for part in (value or "").replace(",", " ").split()]
    except ValueError:
        return False
    return len(numbers) == 4 and all(
        abs(a - b) < 0.01 for a, b in zip(numbers, expected)
    )


def _plain_figure_format() -> tuple[str | None, dict[str, Any]]:
    """The format the page shows a plain figure in, and its ``savefig`` arguments.

    The arguments are the ``keywords`` of the kernel's figure formatter, a
    ``functools.partial`` of IPython's ``print_figure`` or ``retina_figure``.
    """
    from maidr.util.environment import _figure_printer

    try:
        printer = _figure_printer()
    except Exception:
        printer = None
    # The formatter wins: it is what shows the plain figure in this kernel.
    # With none registered, ``quarto_figure_format`` probes for it once more
    # and then answers from Quarto's execute info (``fig-format``).
    if printer is None:
        return Environment.quarto_figure_format(), {}
    keywords = getattr(printer[1], "keywords", None)
    return printer[0], dict(keywords) if isinstance(keywords, dict) else {}


def _shown_box(fig: Any, figure_format: str | None, keywords: dict[str, Any]) -> Any:
    """The part of the figure, in inches, a plain figure shows; None for the canvas.

    As ``FigureCanvasBase.print_figure`` decides it, from the arguments
    IPython's ``print_figure`` passes it: ``bbox_inches`` defaults to
    ``"tight"`` there, and ``None`` falls back to ``savefig.bbox``.
    """
    import matplotlib as mpl
    from matplotlib.layout_engine import ConstrainedLayoutEngine
    from matplotlib.transforms import BboxBase

    bbox_inches = keywords.get("bbox_inches", "tight")
    if bbox_inches is None:
        bbox_inches = mpl.rcParams["savefig.bbox"]
    if isinstance(bbox_inches, BboxBase):
        return bbox_inches
    if not (isinstance(bbox_inches, str) and bbox_inches == "tight"):
        return None
    box = _tight_box(fig, figure_format, keywords)
    pad = keywords.get("pad_inches")
    engine = fig.get_layout_engine()
    if isinstance(engine, ConstrainedLayoutEngine) and pad == "layout":
        w_pad, h_pad = engine.get()["w_pad"], engine.get()["h_pad"]
    else:
        if pad is None or pad == "layout":
            pad = mpl.rcParams["savefig.pad_inches"]
        w_pad = h_pad = pad
    return box.padded(w_pad, h_pad)


def _tight_box(fig: Any, figure_format: str | None, keywords: dict[str, Any]) -> Any:
    """The figure's tight box, in inches, measured as the plain figure's save does.

    At the dpi a raster is saved at, twice the figure's for ``retina``, and
    with the SVG renderer for ``svg``, at 72: hinted text, matplotlib's
    default, measures differently at another dpi or in another renderer, by
    a pixel or so. The figure's dpi is changed while it is measured, as
    ``savefig`` changes it while it saves.
    """
    renderer = None
    if figure_format in _RASTER_FORMATS:
        dpi = _save_dpi(fig, figure_format, keywords)
    elif figure_format == "svg":
        from matplotlib.backends.backend_svg import RendererSVG

        dpi = _POINTS_PER_INCH
        width, height = fig.get_size_inches() * _POINTS_PER_INCH
        renderer = RendererSVG(width, height, io.StringIO())
    else:
        dpi = fig.dpi
    extra = keywords.get("bbox_extra_artists")
    # Changed for the measurement only. The render holds the figure's lock
    # (``figure_lock`` in ``Maidr._create_html_tag``), so nothing else draws
    # it at this dpi meanwhile.
    original = fig.dpi
    try:
        if dpi != original:
            fig.dpi = dpi
        return fig.get_tightbbox(renderer, bbox_extra_artists=extra)
    finally:
        if fig.dpi != original:
            fig.dpi = original


def _save_dpi(fig: Any, figure_format: str | None, keywords: dict[str, Any]) -> float:
    """The dpi IPython saves a raster figure at.

    The figure's, twice it for ``retina``, unless the formatter's arguments
    name a ``dpi`` of their own.
    """
    dpi = keywords.get("dpi")
    if isinstance(dpi, (int, float)) and not isinstance(dpi, bool) and dpi > 0:
        return float(dpi)
    return float(fig.dpi) * (2 if figure_format == "retina" else 1)


def _px_per_inch(
    fig: Any, figure_format: str | None, keywords: dict[str, Any]
) -> float:
    """CSS pixels to the inch the page shows a plain figure at.

    A raster at a pixel to a dot, which Quarto shows a ``retina`` one at
    half of; anything else at 96, as an SVG's points are.
    """
    if figure_format not in _RASTER_FORMATS:
        return _CSS_PX_PER_INCH
    dpi = _save_dpi(fig, figure_format, keywords)
    return dpi / 2 if figure_format == "retina" else dpi


def _backdrop(
    fig: Any, view: tuple[float, ...], canvas: tuple[float, ...]
) -> dict[str, str] | None:
    """The attributes of a path painting the box where it grows past the canvas.

    In the colour the SVG painted the canvas -- the figure's face colour,
    unless ``savefig.facecolor`` or ``savefig.transparent`` say otherwise --
    as the plain figure paints all of its box. An opaque colour paints the
    whole box, under the canvas: left out of the path, the canvas's edge and
    the path's, each drawn smoothed, let a hairline of the page show between
    them. A colour that is not opaque leaves the canvas out, so that it is
    not laid over itself. None when
    the box lies within the canvas or the colour is transparent, or when the
    figure's patch is hidden, which leaves the canvas unpainted in the SVG
    and the whole box in the plain figure.
    """
    import matplotlib as mpl
    from matplotlib.colors import to_hex, to_rgba

    left, top, width, height = view
    right, bottom = left + width, top + height
    _, _, canvas_w, canvas_h = canvas
    if left >= 0 and top >= 0 and right <= canvas_w and bottom <= canvas_h:
        return None
    if mpl.rcParams["savefig.transparent"] or not fig.patch.get_visible():
        return None
    colour = mpl.rcParams["savefig.facecolor"]
    if isinstance(colour, str) and colour == "auto":
        colour = fig.get_facecolor()
    rgba = to_rgba(colour)
    if rgba[3] <= 0:
        return None
    # The canvas, as far as it lies within the box.
    inner = (max(left, 0.0), max(top, 0.0), min(right, canvas_w), min(bottom, canvas_h))
    outer = (left, top, right, bottom)
    subpaths = [outer]
    if rgba[3] < 1 and inner[0] < inner[2] and inner[1] < inner[3]:
        subpaths.append(inner)
    d = " ".join(
        f"M {_number(x0)} {_number(y0)} H {_number(x1)} V {_number(y1)} "
        f"H {_number(x0)} Z"
        for x0, y0, x1, y1 in subpaths
    )
    style = f"fill: {to_hex(rgba)}; fill-rule: evenodd; stroke: none"
    if rgba[3] < 1:
        style += f"; fill-opacity: {_number(rgba[3])}"
    return {"d": d, "style": style}


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

    Every id but the svg's own gets the suffix ``-m<12 hex digits>``, fresh
    per chart, and so does the ``maidr`` mark py-maidr gives a layer's
    group; every reference follows: ``url(#id)``, ``href="#id"``, ARIA id
    lists, and the selectors in the chart's schema. py-maidr's own
    ``maidr-<uuid>`` ids are suffixed too: they are minted once per figure,
    not per render, and one figure can be shown twice on a page. The svg's
    id is the schema's, which maidr.js finds the chart by, and is minted
    per render. A suffix rather than r-maidr's prefix, because
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

    def __init__(self, name: str, alt: str | None = None) -> None:
        #: What the chart is called until maidr.js names it.
        self.name = name
        #: The author's alt text, from the cell's ``fig-alt``: the chart's name
        #: until maidr.js names it, and the first of its description after.
        self.alt = alt
        self.key = "m" + uuid.uuid4().hex[:12]
        #: The chart's own class, which its lifted ``<style>`` is scoped to.
        self.css_class = f"maidr-inline-{self.key}"
        #: The scoped rules of the SVG's ``<style>``; "" when it had none.
        self.css = ""
        #: The ``<svg>``'s id, which is the schema's.
        self.svg_id = ""
        self._renamed: dict[str, str] = {}
        self._marks: dict[str, str] = {}
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
            if element_id and element_id != self.svg_id
        }
        self._marks = {
            mark: f"{mark}-{self.key}"
            for mark in (element.get("maidr") for element in svg.iter())
            if mark and not mark.startswith("{")
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
                # The schema on the svg itself is written afterwards.
                if value in self._marks:
                    element.set(attribute, self._marks[value])
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
            name, quote, value = match.groups()
            names = renamed if name == "id" else self._marks
            return f"[{name}={quote}{names.get(value, value)}{quote}]"

        def hash_id(match: re.Match) -> str:
            value = match.group(1)
            return "#" + renamed.get(value, value)

        return _ID_HASH.sub(hash_id, _ID_ATTRIBUTE.sub(attribute, selector))

    def _anchored(self, part: str) -> bool:
        """Whether a selector names an element by a value only this chart has.

        That is an id, or py-maidr's ``maidr`` mark, tested for an exact value
        that carries this chart's suffix, or for the svg's own id. Anything
        else -- a prefix test, another attribute -- does not make it the
        chart's own.
        """
        for match in _ANCHOR.finditer(part):
            value = match.group(2) if match.group(2) is not None else match.group(3)
            if value.endswith(f"-{self.key}") or value == self.svg_id:
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
        """The rules of the SVG's ``<style>``, each scoped to this chart.

        Written for the ``<style>`` matplotlib puts in every SVG -- plain
        rules, no at-rules -- and refusing anything else rather than growing
        into a CSS parser: a refusal costs the chart its place in the page,
        not its working, since the iframe carries it.
        """
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
    """One of ``maidr/assets/``, its comments and indents dropped.

    Every chart carries ``inline.{js,css}``, so that a chart whose cell hides
    its output takes nothing from the charts after it; they run once per
    page. Every notebook frame carries ``frame.css``; see
    :func:`maidr.util.iframe_utils.frame_style`.
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
    alt = (scope.alt or "").strip()
    children: list[Any] = [
        # Marked so that inline.js keeps one copy of it in the page's head.
        tags.style(HTML(_asset("inline.css")), **{"data-maidr-inline-css": ""})
    ]
    if scope.css:
        children.append(tags.style(HTML(scope.css)))
    children.append(svg)
    if alt:
        # What the chart shows, in the author's words: inline.js describes the
        # chart by it first once maidr.js names the chart, as r-maidr does
        # with ``fig.alt``.
        children.append(
            tags.span(
                alt,
                id=f"{scope.svg_id}-alt",
                class_="maidr-inline-alt",
                hidden=True,
            )
        )
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
    # ``data-lm-suppress-shortcuts``: Quarto writes the outputs of an html
    # render into notebooks too -- ``keep-ipynb``, a manuscript's notebook
    # download -- and JupyterLab and Notebook 7 keep their shortcuts off any
    # key pressed in an element inside one carrying it.
    return tags.div(
        *children,
        class_="maidr-inline",
        role="img",
        aria_label=scope.name,
        **{"data-maidr-inline": "", "data-lm-suppress-shortcuts": ""},
    )
