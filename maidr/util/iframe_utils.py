"""
Utility functions for wrapping HTML content in auto-resizing iframes.

These functions are used by both matplotlib and Plotly renderers to embed
plots in Jupyter notebooks, Google Colab, VSCode, Flask, and Shiny environments.
"""

# Python 3.9 -- which pyproject.toml supports -- evaluates annotations at
# definition time, so a bare `str | None` in a signature here raises
# TypeError on import rather than failing a type check. This module is
# imported by `maidr/core/maidr.py`, so that would break `import maidr`
# outright on the oldest supported interpreter.
from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from htmltools import HTMLDependency, Tag, tags

from maidr.util.compact import compact_css, compact_js, css_blocks

# What the frame is called when the chart it holds has no title of its own.
_UNTITLED_NAME = "Accessible chart"

# Permissions-Policy features the chart frame is allowed to use.
#
# These let maidr.js reach a tactile graphics display and draw the chart on
# its pins: a Dot Pad over Bluetooth or over USB, and a Monarch, in its Braille
# Terminal, over WebHID.  All three are listed because maidr offers all three
# and they are gated independently; granting one would leave the others dead
# with nothing on the page to explain it.
#
# Two different default allowlists meet here.  A feature the container policy
# does not name falls back to the *feature's* default, ``self`` -- which a
# same-origin frame satisfies, so this attribute changes nothing for one.  A
# feature named here without its own allowlist takes the *attribute's*
# default, ``'src'``: the origin the frame was loaded from.  They coincide
# only because the frame stays same-origin: these wrappers use ``srcdoc``,
# whose document inherits the embedder's origin, which is why
# ``test_the_frame_still_carries_its_own_document`` guards that choice; the
# Shiny renderer then swaps the ``srcdoc`` for a relative ``src`` on the
# app's own origin (#534), which ``test_the_frame_stays_on_the_hosts_origin``
# in ``tests/widget/test_shiny.py`` guards in turn.  What the attribute buys
# is the cross-origin case, where the fallback would deny both.
#
# This delegates capabilities, it does not create them: a frame cannot receive
# a feature the embedding page lacks, and the browser still requires a user
# gesture and its own device picker.  It does widen what an injection into the
# framed document would reach, so it leans on an assumption worth stating.  The
# document is executable by design -- it carries the chart's own scripts -- so
# what has to hold is that the strings a caller supplies, the title above all,
# land in it as text and never as markup.  ``htmltools`` escapes them today --
# a title of ``</iframe><script>`` stays inside its attribute -- and
# ``test_a_hostile_title_arrives_as_text`` fails if that stops being true.
_ALLOWED_FEATURES = "bluetooth; serial; hid"


def _generate_unique_id() -> str:
    """Generate a unique iframe ID."""
    return "iframe_" + str(uuid.uuid4())


def iframe_title(chart_title: str | None = None, alt: str | None = None) -> str:
    """
    Build the accessible name for the frame holding a chart.

    An ``iframe`` with no ``title`` is announced as an unnamed frame, so a
    reader arriving at one is told only that a frame is there -- not that it
    holds a chart, and not which chart. Every iframed render goes through
    here, so this is the one place that decides (#453).

    The chart's own title leads, because that is the part that distinguishes
    one frame from the next. A page carrying three charts named alike gives a
    reader tabbing between them no way to tell which they have reached, which
    is the failure a generic name would still leave in place.

    The qualifier follows so the name also says what kind of thing the frame
    is: an interactive chart to enter rather than a picture to skip. It is
    the shape ``Description.tsx`` uses for its own table -- a name for the
    chart when there is one, a bare label when there is not.

    An author's alt text names the frame instead: their own words for the
    chart, as it names a chart written into the page of a Quarto render.

    Parameters
    ----------
    chart_title : str, optional
        The chart's title. Whitespace-only counts as absent, matching the
        MAIDR engine's trimmed "authored" check.
    alt : str, optional
        The alt text of the Quarto cell the chart is drawn in (``fig-alt``).
        Whitespace-only counts as absent.

    Returns
    -------
    str
        The accessible name for the ``iframe``.
    """
    if alt and alt.strip():
        return alt.strip()
    name = (chart_title or "").strip()
    return f"{name}, accessible chart" if name else _UNTITLED_NAME


def chart_title_of(schema: dict) -> str:
    """
    The name a rendered figure is known by, or ``""`` when it has none.

    Read back off the emitted schema rather than off the figure object, for
    two reasons. It is the one shape matplotlib, Plotly and Altair all
    produce, so the rule lives here once instead of drifting between three
    renderers; and it names the frame the same thing the chart announces
    itself as, where reading the figure separately could let the two come
    apart and leave a reader hunting for a frame whose name no chart says.

    A figure-level title wins where there is one. Failing that, a single
    title shared by every layer is the figure's name too: a one-axes figure
    carries its title on the layer, which is where ``ax.set_title()`` puts it
    and much the commoner spelling.

    A multi-panel figure whose panels are titled differently has no one name.
    Naming the frame after the first panel would name it after a part of what
    it holds, so those fall back to the bare label.

    Parameters
    ----------
    schema : dict
        A flattened MAIDR schema.

    Returns
    -------
    str
        The title, or an empty string when the figure has no single one.
    """
    figure_title = str(schema.get("title", "") or "").strip()
    if figure_title:
        return figure_title

    titles = {
        str(layer.get("title", "") or "").strip()
        for row in schema.get("subplots", [])
        for panel in row
        for layer in panel.get("layers", [])
    }
    titles.discard("")
    return titles.pop() if len(titles) == 1 else ""


# Where a rendered tag keeps the title its chart is known by, for a host that
# builds the chart's frame itself and so needs the name handed to it.
_CHART_TITLE_ATTR = "_maidr_chart_title"


def with_chart_title(tag: Tag, chart_title: str) -> Tag:
    """
    Record on a rendered tag the title its chart is known by.

    Streamlit builds the chart's frame itself, so the name the wrappers
    below put on their own frames has to be handed to it instead. The
    renderer is the one place that has the title in hand -- recovering it
    afterwards would mean building the schema a second time -- so it leaves
    it here. A Python attribute rather than an HTML one, so the markup every
    other host receives is unchanged.

    Parameters
    ----------
    tag : htmltools.Tag
        The rendered chart.
    chart_title : str
        The title, or ``""`` when the chart has none.

    Returns
    -------
    htmltools.Tag
        ``tag`` itself, for chaining.
    """
    setattr(tag, _CHART_TITLE_ATTR, chart_title)
    return tag


def chart_title_on(tag: object) -> str:
    """
    The title :func:`with_chart_title` recorded, or ``""`` when none was.

    Parameters
    ----------
    tag : object
        A rendered chart.

    Returns
    -------
    str
        The title.
    """
    return str(getattr(tag, _CHART_TITLE_ATTR, "") or "")


#: The class of the root ``<svg>`` of a matplotlib chart in a notebook's
#: frame, sized as the notebook shows the plain figure; the frame's stylesheet
#: and script find the chart by it.
FRAME_SVG_CLASS = "maidr-frame-svg"


def frame_style() -> str:
    """The stylesheet of a chart's frame in a notebook, as a ``<style>`` element.

    See ``maidr/assets/frame.css``: the frame's margins and the figure's are
    reset, the chart shrinks with a narrow output area, focus rings are drawn
    inside the frame, and a chart sized by its container fills the frame.

    Returns
    -------
    str
        The ``<style>`` element, first in the frame's ``srcdoc``.
    """
    from maidr.util.inline_chart import _asset

    return f"<style>{_asset('frame.css')}</style>"


#: The rules of ``frame.css`` a Shiny app's frame needs only once its script
#: runs: focus rings, a dialog's band, a fitted chart's centring. Not the
#: ones its document is laid out by as it loads.
_LATER_RULES = re.compile(r":focus|forced-colors|data-maidr-dialog-room|data-maidr-fit-box")


@lru_cache(maxsize=1)
def _shiny_frame_css() -> tuple:
    """``frame.css`` compacted, as rules a Shiny frame's document starts with
    and rules its script adds (:data:`_LATER_RULES`)."""
    from maidr.util.inline_chart import _asset

    blocks = css_blocks(compact_css(_asset("frame.css")))
    later = [block for block in blocks if _LATER_RULES.search(block)]
    first = [block for block in blocks if block not in later]
    return "".join(first), "".join(later)


def _frame_style(in_shiny: bool) -> str:
    """:func:`frame_style`, or, in a Shiny app, whose frame is sent with every
    flush of its output, the part of it the frame's document is laid out
    by as it loads, compacted; the frame's script adds the rest."""
    if not in_shiny:
        return frame_style()
    return f"<style>{_shiny_frame_css()[0]}</style>"


#: The width a notebook's frame may take: its output area's, and the padding
#: the area keeps on its right too. JupyterLab, Notebook 7 and an nbconvert
#: export pad an HTML output on its right (20px) and an image output not, so
#: a chart narrower than the output area came out 20px narrower than the
#: figure's image would. The frame takes that padding back, and its margin
#: gives it back to the area, which therefore does not scroll. A frame that
#: ``keepPadding`` keeps clear of it, as the library's own chart does.
_OUTPUT_WIDTH_JS = """
        function maidrOutputWidth(iframe, keepPadding) {
            var host = iframe.parentElement;
            var pad = host && !keepPadding
                ? parseFloat(window.getComputedStyle(host).paddingRight) || 0
                : 0;
            iframe.style.marginRight = pad > 0 ? (-pad) + 'px' : '';
            return pad > 0 ? 'calc(100% + ' + pad + 'px)' : '100%';
        }
"""

#: The same width, taken by the frame's own document as it starts, before
#: anything in it draws: plotly.js draws a chart without a width of its own
#: as wide as the frame is then, and keeps it once maidr.js has bound it.
_OUTPUT_WIDTH_FIRST = (
    "<script>(function () { try {"
    " var frame = window.frameElement;"
    " var host = frame && frame.parentElement;"
    " if (!host) return;"
    " var pad = parseFloat(window.parent.getComputedStyle(host).paddingRight) || 0;"
    " if (pad > 0) {"
    " frame.style.width = 'calc(100% + ' + pad + 'px)';"
    " frame.style.marginRight = (-pad) + 'px';"
    " }"
    " } catch (e) {} })();</script>"
)

#: ``maidrShowField`` shows the whole of a field of maidr's that has the
#: focus once its frame has grown to hold it: a notebook's frame, and a
#: Shiny app's, call it.
_SHOW_FIELD_JS = """        function maidrShowField(doc, resized) {
            // maidr's braille or review field, opened below the chart, took
            // the focus before the frame grew to hold it: the browser then
            // showed what it could of it, the frame's bottom edge.
            var field = doc.activeElement;
            if (resized && field && field.matches && field.matches(
                '[id^="maidr-braille-textarea"], [id^="maidr-review-input"], '
                + '.maidr-review-input, .maidr-review-input *'
            )) {
                field.scrollIntoView({block: 'nearest', inline: 'nearest'});
            }
        }
"""

#: The scroll positions of the boxes a frame scrolls in, kept while it is
#: measured. A frame is measured at no height, and a Plotly, Bokeh or Altair
#: one at the output area's width, for a moment; the boxes around it clamp
#: their scroll positions to what then fits, and a reader scrolled down a
#: notebook, or across a chart wider than its output area, was moved back to
#: its top or left edge every time the frame was measured.
#: ``maidrKeepScroll`` returns what puts them back. A frame wholly above what
#: a box shows moves what it shows by as much as the frame grew, as the
#: browser's scroll anchoring would have, so the reader's place stays put.
_KEEP_SCROLL_ONLY_JS = """
        function maidrKeepScroll(iframe) {
            var page = iframe.ownerDocument;
            var frame = iframe.getBoundingClientRect();
            var kept = [];
            for (var el = iframe.parentElement; el; el = el.parentElement) {
                if (el.scrollTop || el.scrollLeft) {
                    var whole = el === page.documentElement || el === page.body;
                    var shown = whole ? 0 : el.getBoundingClientRect().top + el.clientTop;
                    kept.push([el, el.scrollTop, el.scrollLeft, frame.bottom <= shown]);
                }
            }
            return function() {
                var grew = iframe.getBoundingClientRect().height - frame.height;
                for (var i = 0; i < kept.length; i++) {
                    var el = kept[i][0];
                    var top = kept[i][1] + (kept[i][3] ? grew : 0);
                    if (el.scrollTop !== top) el.scrollTop = top;
                    if (el.scrollLeft !== kept[i][2]) el.scrollLeft = kept[i][2];
                }
            };
        }
"""
_KEEP_SCROLL_JS = _KEEP_SCROLL_ONLY_JS + _SHOW_FIELD_JS

#: Whether a notebook's frame is not laid out: in an output the notebook
#: hides, or in a cell JupyterLab does not draw while it is out of view. Such
#: a frame has no width, and measured as nothing; it keeps its height until it
#: has one again, which its window's resize reports.
_NOT_LAID_OUT_JS = """
        function maidrNotLaidOut(iframe) {
            return !!(iframe && iframe.contentWindow && !iframe.contentWindow.innerWidth);
        }
"""

#: Room for maidr's dialogs -- help, settings, chat -- which MUI fixes in the
#: frame's viewport, centred, and scrolls within, or squeezes, when the
#: viewport is shorter than they are. While one is open, a notebook's frame is
#: as tall as the part of the notebook a reader sees: the box the notebook
#: scrolls in (JupyterLab's and Notebook 7's), or the window (an nbconvert
#: export). Not the dialog's own height, which changes with each settings tab
#: and which the chat's has none of. A chart taller than that keeps its
#: height. Measured before the frame is, while the notebook still scrolls as
#: it did. A window that is a frame itself, of an output of its own, is as
#: tall as that output; there the room is 480px at least. Once the frame has
#: the room, it is scrolled to the middle of the reader's view, and with it
#: the dialog, centred in it: growing the frame had moved the dialog down,
#: below the part of the notebook the reader sees. ``maidrWatch`` tells when
#: one comes or goes.
_DIALOG_ROOM_JS = """
        function maidrDialogRoom(doc, iframe) {
            if (!doc.querySelector('.MuiDialog-root')) return 0;
            var win = iframe.ownerDocument.defaultView;
            var height = win.innerHeight || 0;
            var scroller = null;
            for (var el = iframe.parentElement; el; el = el.parentElement) {
                var y = win.getComputedStyle(el).overflowY;
                if ((y === 'auto' || y === 'scroll' || y === 'overlay')
                        && el.scrollHeight > el.clientHeight + 1) {
                    scroller = el;
                }
            }
            if (scroller) {
                height = Math.min(height, scroller.clientHeight);
            } else if (win !== win.top) {
                height = Math.max(height, 480);
            }
            return Math.floor(height);
        }
        function maidrShowDialog(doc, iframe, room, resized) {
            var opened = room > 0;
            var was = iframe.maidrDialogOpen;
            iframe.maidrDialogOpen = opened;
            // Over a chart taller than the reader's view, the dialog is kept
            // to a band of that height in the middle of the frame (frame.css).
            var root = doc.documentElement;
            if (opened && iframe.clientHeight > room) {
                root.style.setProperty('--maidr-dialog-room', room + 'px');
                root.setAttribute('data-maidr-dialog-room', '');
            } else if (root.hasAttribute('data-maidr-dialog-room')) {
                root.style.removeProperty('--maidr-dialog-room');
                root.removeAttribute('data-maidr-dialog-room');
            }
            if (opened && (!was || resized)) {
                // The dialog is centred in the frame: centring the frame in
                // the reader's view shows it whole.
                iframe.scrollIntoView({block: 'center', inline: 'nearest'});
            }
        }
"""

#: How much of the window's top a Shiny page's header covers: an element
#: fixed or sticky there, over the frame's middle, and any below it in turn,
#: half the window at most. Not one the frame is inside.
_COVER_JS = """
        function maidrCover(iframe) {
            var page = iframe.ownerDocument;
            var win = page.defaultView;
            var rect = iframe.getBoundingClientRect();
            var x = Math.min(Math.max((rect.left + rect.right) / 2, 0), win.innerWidth - 1);
            var top = 0;
            for (var i = 0; i < 4; i++) {
                var el = page.elementFromPoint(x, top);
                while (el && el !== page.body && el !== page.documentElement) {
                    var position = win.getComputedStyle(el).position;
                    if (position === 'fixed' || position === 'sticky') break;
                    el = el.parentElement;
                }
                if (!el || el === page.body || el === page.documentElement
                        || el.contains(iframe)) break;
                var bottom = Math.ceil(el.getBoundingClientRect().bottom);
                if (!(bottom > top)) break;
                top = bottom;
            }
            return Math.min(top, Math.floor(win.innerHeight / 2));
        }
"""


def _replace_once(text: str, old: str, new: str) -> str:
    """``text`` with ``old``, which it holds once, made ``new``."""
    assert text.count(old) == 1, old
    return text.replace(old, new)


#: What changes a frame's height that its body's size does not show: maidr's
#: text, braille and review fields, which can lie past the body's box (a
#: Plotly or Bokeh chart's do), coming, going or changing, and a dialog of
#: maidr's, which it draws into the chart's own container, not the body, and
#: takes away only once it has faded out, after the focus has gone back to
#: the chart. Their frame was measured again on every frame, which this
#: replaces: its text came out below a Plotly chart's frame without it.
_WATCH_JS = """
        function maidrWatch(doc, onChange) {
            var parts = '.MuiModal-root, #maidr-text-container, #maidr-rotor-area, '
                + '[id^="maidr-braille-textarea"], [id^="maidr-review-input"], '
                + '.maidr-review-input';
            function counts(node) {
                return node.nodeType === 1
                    && (node.matches(parts) || !!node.querySelector(parts));
            }
            new MutationObserver(function(records) {
                for (var i = 0; i < records.length; i++) {
                    var target = records[i].target;
                    var el = target.nodeType === 1 ? target : target.parentElement;
                    if (el && el.closest(parts)) {
                        onChange();
                        return;
                    }
                    var nodes = Array.prototype.slice.call(records[i].addedNodes)
                        .concat(Array.prototype.slice.call(records[i].removedNodes));
                    for (var j = 0; j < nodes.length; j++) {
                        if (counts(nodes[j])) {
                            onChange();
                            return;
                        }
                    }
                }
            }).observe(doc.body, {childList: true, subtree: true, characterData: true});
        }
"""

#: What only a notebook's frame calls. A frame elsewhere leaves it out; a
#: Shiny app's frame has a script of its own (:func:`shiny_frame_script`).
_NOTEBOOK_JS = _OUTPUT_WIDTH_JS + _KEEP_SCROLL_JS + _NOT_LAID_OUT_JS + _DIALOG_ROOM_JS

#: How a Shiny app's frame fits the box it is shown in: the box
#: :class:`maidr.widget.shiny.render_maidr` puts around it, which is the
#: output's whole box unless the renderer was given a size of its own.
#:
#: A box with a height of its own -- an output given one, or one that fills
#: a fillable container (a card, ``page_fillable``) -- holds a matplotlib
#: chart as ``object-fit: contain`` holds an image: as large as the box
#: allows, larger or smaller than the chart's own size, keeping its shape,
#: centred, less a line kept below it for maidr's text. As
#: ``maidr/assets/inline.js`` (``fitCard``) fits a chart to a Quarto
#: dashboard's card, and told apart the same way: a box that keeps its
#: height with the frame at none and at 4000px has one of its own. A Plotly
#: figure or a Bokeh plot that takes its height from its container is as
#: tall as the box less that line (``maidrFillHeight``). A box that takes
#: its height from the frame leaves the chart as a notebook's frame has it:
#: as wide as the box, up to its own width, shrinking with a narrower one.
#:
#: The line kept for maidr's text is as many lines as its text takes, the
#: most so far (``maidrTextRoom``). The box scrolls to whatever does not
#: fit -- maidr's braille field, a text longer than half the box -- rather
#: than cutting it off. A fitted chart is given a width alone, and is never
#: wider than its frame (``frame.css``), so that a scrollbar the box takes
#: (Windows' are 15px wide) narrows it, and the box's ResizeObserver fits it
#: again, rather than cutting its right edge, and its focus ring, off.
#: maidr's text is scrolled into the box as it changes (``maidrShowText``),
#: the box alone, never the page.
#:
#: While a dialog of maidr's is open -- help, settings, chat -- none of this
#: applies (``maidrSuspendBox``): the box and the output round it are
#: pass-through containers, as Shiny makes an output that has children, the
#: frame has an iframe's own style, and the frame is laid out by a notebook
#: frame's lines: a matplotlib chart at its own size, or the frame's width
#: where that is less, a chart that takes its height from its container at
#: the height it had, not drawn again nor made wider, and the frame as tall
#: as the window below a header fixed or sticky at its top (``maidrCover``),
#: or the box that scrolls it, and scrolled to its middle
#: (``maidrDialogRoom``, ``maidrShowDialog``), so that the dialog is shown
#: whole. As the dialog closes, or the frame leaves the page, all of it is
#: given back. Nothing about the page or a box round the frame is kept as
#: the dialog opens, and nothing is put back as it closes: the chart, given
#: the focus back, is scrolled into view, the nearest way, only where none
#: of its frame shows in the window or in a box round it that scrolls
#: (``maidrBringIn``); where any of it shows, nothing is scrolled.
#:
#: A chart drawn again -- an input it reads moved, live data -- keeps its
#: output at the height it had until the new chart's frame has measured its
#: chart (``maidrHoldRedraw``): Shiny takes the old frame out and puts the
#: new one in at 150px, and the page round the output moved, so that a
#: reader below a chart whose top was above the window lost the chart and
#: the control they were moving. Nothing scrolls the page for it. Not under
#: a dialog, whose box is not there to hold, and nothing scrolls the page
#: then either. ``maidrWatchBox`` fits the
#: chart again whenever the box changes size: a window resized, a card taken
#: full screen or back, a sidebar closed, with nothing sent to the server.
_BOX_JS = """
        function maidrBoxRoom(iframe) {
            var box = iframe.parentElement;
            if (!box || !box.clientWidth) return 0;
            iframe.style.height = '0px';
            var short = box.clientHeight;
            iframe.style.height = '4000px';
            var tall = box.clientHeight;
            iframe.style.height = '0px';
            if (!(short > 0) || Math.abs(tall - short) >= 1) return 0;
            var style = iframe.ownerDocument.defaultView.getComputedStyle(box);
            return short - (parseFloat(style.paddingTop) || 0)
                - (parseFloat(style.paddingBottom) || 0);
        }
        function maidrBoxWidth(iframe) {
            var box = iframe.parentElement;
            var style = iframe.ownerDocument.defaultView.getComputedStyle(box);
            return box.clientWidth - (parseFloat(style.paddingLeft) || 0)
                - (parseFloat(style.paddingRight) || 0);
        }
        // The room kept below the chart for a line of maidr's text: one
        // line of the frame's text (line-height normal, about 1.15em; 1.25
        // to be safe) and the margins of the paragraph maidr.js sets it in,
        // 1em above and below. 52px at the frame's 16px; maidr.js 3.x takes
        // 50px for it.
        function maidrTextLine(doc) {
            var style = doc.defaultView.getComputedStyle(doc.body);
            var size = parseFloat(style.fontSize) || 16;
            var line = parseFloat(style.lineHeight);
            if (!(line > 0)) line = 1.25 * size;
            return Math.ceil(line + 2 * size);
        }
        // Whether a dialog of maidr's is open in the frame. While one is,
        // the frame is laid out as before charts were fitted to their
        // outputs, by construction: the box render_maidr puts round it is
        // a pass-through container (display: contents), as if it were not
        // there; the output round that has none of the style or fill
        // classes output_maidr gives it, so that Shiny's own rule makes it
        // one too; the frame has an iframe's style as it had then; and the
        // frame's script sizes it, gives the dialog room and scrolls it
        // into view as a notebook's frame does (the lines marked for
        // every frame but a Shiny app's, and maidrDialogRoom). All of it
        // is given back once the dialog closes -- as MUI gives the chart
        // the focus back, before the browser scrolls to it -- or once the
        // frame has left the page: its chart drawn again, or its output
        // emptied, with the dialog open. The chart is then fitted again.
        function maidrSuspendBox(iframe) {
            var doc = iframe && iframe.contentWindow && iframe.contentWindow.document;
            var roots = doc ? doc.querySelectorAll('.MuiDialog-root') : [];
            var open = false;
            for (var r = 0; r < roots.length; r++) open = open || !roots[r].maidrClosed;
            var active = doc && doc.activeElement;
            if (open && iframe.maidrSuspended && active && active !== doc.body
                    && !active.closest('.MuiModal-root')) {
                // Closing, though it has yet to fade out: the focus has
                // left it, for the chart.
                for (var c = 0; c < roots.length; c++) roots[c].maidrClosed = true;
                open = false;
            }
            if (!iframe || open === !!iframe.maidrSuspended) return open;
            var box = iframe.parentElement;
            iframe.maidrHostWidth = undefined;
            if (open) {
                var width = iframe.getBoundingClientRect().width;
                var suspended = iframe.maidrSuspended = {
                    frame: iframe.getAttribute('style'), held: []
                };
                if (box && box.classList.contains('maidr-shiny-box')) {
                    suspended.held.push([box, box.getAttribute('style'), []]);
                    box.setAttribute('style', 'display: contents');
                    var out = box.parentElement;
                    if (out && out.classList.contains('shiny-html-output')) {
                        var fill = ['html-fill-container', 'html-fill-item']
                            .filter(function(name) { return out.classList.contains(name); });
                        suspended.held.push([out, out.getAttribute('style'), fill]);
                        out.removeAttribute('style');
                        for (var i = 0; i < fill.length; i++) out.classList.remove(fill[i]);
                    }
                }
                iframe.setAttribute('style', 'FRAME_STYLE');
                var chart = doc.querySelector('svg.FRAME_SVG_CLASS');
                if (chart) {
                    chart.style.width = '';
                    chart.style.height = '';
                } else {
                    // A chart that takes its frame's width is not made
                    // wider: drawn again under a dialog, a Plotly chart
                    // threw ('mo'). Narrower, it follows the window.
                    iframe.style.maxWidth = width + 'px';
                }
                if (doc.body) doc.body.style.paddingTop = '';
                doc.documentElement.removeAttribute('data-maidr-fit-box');
                doc.documentElement.setAttribute('data-maidr-suspended', '');
                var win = iframe.ownerDocument.defaultView;
                if (win.MutationObserver) {
                    suspended.gone = new win.MutationObserver(function() {
                        if (!iframe.isConnected) maidrSuspendBox(iframe);
                    });
                    suspended.gone.observe(
                        iframe.ownerDocument.body, {childList: true, subtree: true}
                    );
                }
                // The focus coming back to the chart, before the browser
                // scrolls to it.
                suspended.back = function() { maidrSuspendBox(iframe); };
                doc.addEventListener('focusin', suspended.back, true);
                suspended.focus = maidrFocusInPlace(doc.defaultView);
            } else {
                var was = iframe.maidrSuspended;
                iframe.maidrSuspended = null;
                if (was.gone) was.gone.disconnect();
                if (doc) doc.removeEventListener('focusin', was.back, true);
                was.focus();
                for (var j = 0; j < was.held.length; j++) {
                    var el = was.held[j][0];
                    if (was.held[j][1] === null) el.removeAttribute('style');
                    else el.setAttribute('style', was.held[j][1]);
                    for (var k = 0; k < was.held[j][2].length; k++) {
                        el.classList.add(was.held[j][2][k]);
                    }
                }
                if (was.frame === null) iframe.removeAttribute('style');
                else iframe.setAttribute('style', was.frame);
                iframe.maidrDialogOpen = false;
                if (doc) doc.documentElement.removeAttribute('data-maidr-suspended');
                maidrBringIn(iframe);
            }
            return open;
        }
        // Focus given in the frame while a dialog is open, and until it has
        // gone, moves nothing: maidr.js and MUI give the chart the focus
        // back as the dialog closes, MUI once more as it takes the dialog
        // away, and the browser scrolled the page to the element that took
        // it where that was out of view, centring it -- a Plotly chart's,
        // a line at its top, which showing the dialog had scrolled above
        // the window: the chart 450px down, its highlight 18-45% shown.
        // Returns what gives focus() its own way back once no dialog is
        // left, or 2s after, whichever is first.
        function maidrFocusInPlace(win) {
            var held = win.maidrFocusHeld;
            if (!held) {
                held = win.maidrFocusHeld = {count: 0, own: []};
                [win.HTMLElement, win.SVGElement].forEach(function(type) {
                    var proto = type && type.prototype;
                    if (!proto || !Object.prototype.hasOwnProperty.call(proto, 'focus')) {
                        return;
                    }
                    var focus = proto.focus;
                    held.own.push([proto, focus]);
                    proto.focus = function(options) {
                        var still = {preventScroll: true};
                        if (options && options.focusVisible !== undefined) {
                            still.focusVisible = options.focusVisible;
                        }
                        return focus.call(this, still);
                    };
                });
            }
            held.count++;
            var asked = false, gone = false, watch = null, timer = 0;
            function letGo() {
                if (gone) return;
                gone = true;
                if (watch) watch.disconnect();
                win.clearTimeout(timer);
                if (--held.count > 0) return;
                for (var i = 0; i < held.own.length; i++) {
                    held.own[i][0].focus = held.own[i][1];
                }
                win.maidrFocusHeld = null;
            }
            return function() {
                if (asked) return;
                asked = true;
                try {
                    var doc = win.document;
                    if (!doc.body || !doc.querySelector('.MuiModal-root')) return letGo();
                    watch = new win.MutationObserver(function() {
                        if (!doc.querySelector('.MuiModal-root')) letGo();
                    });
                    watch.observe(doc.body, {childList: true, subtree: true});
                    timer = win.setTimeout(letGo, 2000);
                } catch (_) {
                    letGo();
                }
            };
        }
        // The chart, given the focus back as its dialog closes, its frame
        // fitted to its box again, brought into view where none of its
        // frame shows: in the window, or in a box round it that scrolls.
        // The nearest way, below a header fixed at the window's top. Where
        // any of it shows, nothing is scrolled: the page, and every box
        // round the frame, are left where they are, and the browser does
        // not scroll to the element given the focus (maidrFocusInPlace).
        // Nothing is kept from as the dialog opened: a page put back to
        // where it was then undid what had moved it since -- content above
        // the chart that grew, a script, a reader's own scroll -- and left
        // the chart hundreds of pixels from where it had been.
        function maidrBringIn(iframe) {
            var page = iframe.ownerDocument;
            if (!iframe.isConnected || page.activeElement !== iframe) return;
            var win = page.defaultView;
            var frame = iframe.getBoundingClientRect();
            var out = frame.bottom <= 0 || frame.top >= win.innerHeight
                || frame.right <= 0 || frame.left >= win.innerWidth;
            for (var el = iframe.parentElement; !out && el && el !== page.body
                    && el !== page.documentElement; el = el.parentElement) {
                if (el.scrollHeight <= el.clientHeight + 1
                        && el.scrollWidth <= el.clientWidth + 1) continue;
                var style = win.getComputedStyle(el);
                if (style.overflowY === 'visible' && style.overflowX === 'visible') continue;
                var box = el.getBoundingClientRect();
                var top = box.top + el.clientTop;
                var left = box.left + el.clientLeft;
                out = frame.bottom <= top || frame.top >= top + el.clientHeight
                    || frame.right <= left || frame.left >= left + el.clientWidth;
            }
            if (!out) return;
            var margin = iframe.style.scrollMarginTop;
            iframe.style.scrollMarginTop = maidrCover(iframe) + 'px';
            iframe.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'instant'});
            iframe.style.scrollMarginTop = margin;
        }
        // A frame whose height flips between two as a scrollbar comes and
        // goes round it -- the page's, or a box's, coming as the frame grows
        // and going as it shrinks, and the chart fitted to the width it
        // leaves -- keeps the taller of the two: at the classic scrollbars'
        // threshold it was resized without end. That alone: each of the two
        // heights measured at its own width, the box narrower by no more
        // than the scrollbars that came took (maidrBars), whatever their
        // width, the narrower width giving the shorter height, each within
        // a second of the last, the window the same size. The hold lets go
        // as soon as the window changes size, or the box a width other than
        // those two, or the chart a height other than those two: a card
        // taken full screen and back, a window made shorter, a plot drawn
        // again at another size.
        function maidrBars(box) {
            var page = box.ownerDocument;
            var bars = page.defaultView.innerWidth - page.documentElement.clientWidth;
            for (var el = box; el && el !== page.documentElement; el = el.parentElement) {
                // An inline element has no client width, nor scrollbar.
                if (el.clientWidth) bars += el.offsetWidth - el.clientWidth;
            }
            return bars;
        }
        function maidrSteady(iframe, height) {
            var win = iframe.ownerDocument.defaultView;
            var box = iframe.parentElement;
            var width = box ? box.clientWidth : 0;
            var bars = box ? maidrBars(box) : 0;
            var size = win.innerWidth + 'x' + win.innerHeight;
            var flip = iframe.maidrFlip;
            if (!flip || flip.size !== size) {
                flip = iframe.maidrFlip = {size: size, seen: [], hold: 0};
            }
            var seen = flip.seen;
            if (flip.hold) {
                if ((height === seen[0].height || height === seen[1].height)
                        && (width === seen[0].width || width === seen[1].width)) {
                    return flip.hold;
                }
                flip.hold = 0;
                seen.length = 0;
            }
            var now = win.performance.now();
            var last = seen[seen.length - 1];
            if (last && last.height === height) return height;
            seen.push({height: height, width: width, bars: bars, at: now});
            while (seen.length > 3 || now - seen[0].at > 2000) seen.shift();
            if (seen.length === 3) {
                var a = seen[0], b = seen[1], c = seen[2];
                if (c.height === a.height && c.width === a.width
                        && b.width !== a.width && b.bars !== a.bars
                        && Math.abs(b.width - a.width) <= Math.abs(b.bars - a.bars) + 1
                        && (b.width < a.width) === (b.bars > a.bars)
                        && (b.width < a.width) === (b.height < a.height)
                        && c.at - b.at <= 1000 && b.at - a.at <= 1000) {
                    flip.seen = [a, b];
                    flip.hold = Math.max(a.height, b.height);
                    return flip.hold;
                }
            }
            return height;
        }
        // Holds on an element's height, each for a reason: the most of
        // them is its min-height, and its own comes back once none is left.
        function maidrHold(el, why, px) {
            if (!el) return;
            var holds = el.maidrHolds;
            if (!holds) {
                if (!(px > 0)) return;
                holds = el.maidrHolds = {own: el.style.minHeight, by: {}};
            }
            if (px > 0) holds.by[why] = px; else delete holds.by[why];
            var most = 0;
            for (var k in holds.by) most = Math.max(most, holds.by[k]);
            var want = most > 0 ? most + 'px' : holds.own;
            if (el.style.minHeight !== want) el.style.minHeight = want;
            if (!(most > 0)) el.maidrHolds = null;
        }
        // The element whose height the page sees round a frame's box: the
        // output, or, where that is a pass-through container (Shiny makes
        // an output that has children one, display: contents), the
        // nearest container round it that has a box.
        function maidrHolder(el) {
            var page = el && el.ownerDocument;
            while (el && el !== page.body
                    && page.defaultView.getComputedStyle(el).display === 'contents') {
                el = el.parentElement;
            }
            return el;
        }
        function maidrHeight(el) {
            var style = el.ownerDocument.defaultView.getComputedStyle(el);
            var height = el.getBoundingClientRect().height;
            if (style.boxSizing !== 'border-box') {
                height -= (parseFloat(style.paddingTop) || 0)
                    + (parseFloat(style.paddingBottom) || 0)
                    + (parseFloat(style.borderTopWidth) || 0)
                    + (parseFloat(style.borderBottomWidth) || 0);
            }
            return height;
        }
        // The output at the height it has while the frame is measured, at
        // no height and at 4000px for a moment: the page then stays as it
        // is. It had been clamped to what fitted, the containers round the
        // output with it, and scrolled back after. Returns what lets go.
        function maidrHoldStill(iframe) {
            var box = iframe.parentElement;
            var el = box && maidrHolder(box.parentElement);
            if (!el || el.maidrHolds) return null;
            maidrHold(el, 'measure', maidrHeight(el));
            return function() { maidrHold(el, 'measure', 0); };
        }
        // The box's scroll position, kept while the frame is measured: the
        // box alone, the output round it being held still.
        function maidrKeepBoxScroll(iframe) {
            var box = iframe.parentElement;
            if (!box || !(box.scrollTop || box.scrollLeft)) return null;
            var top = box.scrollTop;
            var left = box.scrollLeft;
            return function() {
                if (box.scrollTop === top && box.scrollLeft === left) return;
                box.scrollTo({top: top, left: left, behavior: 'instant'});
            };
        }
        // An output whose chart is about to be drawn again is held at the
        // height it has (Shiny's shiny:value comes before it is), until a
        // new frame in it has measured its chart (maidrRedrawn), until
        // there is no frame of maidr's in it, or for 10s at most. Not one
        // whose chart has a dialog open: its box is suspended.
        function maidrHoldRedraw(out) {
            var old = out.querySelectorAll('iframe[data-maidr-chart]');
            for (var i = 0; i < old.length; i++) {
                if (old[i].maidrSuspended) return;
            }
            var el = old.length && maidrHolder(out);
            if (!el) return;
            var win = out.ownerDocument.defaultView;
            // Measured before an earlier hold is let go: a chart drawn again
            // before the frame drawn last had measured its own was held at
            // that frame's 150px, and the page below it moved up.
            var px = maidrHeight(el);
            if (!(px > 0)) return;
            maidrLetGo(el);
            var redraw = el.maidrRedraw = {old: Array.prototype.slice.call(old)};
            maidrHold(el, 'redraw', px);
            redraw.timer = win.setTimeout(function() { maidrLetGo(el); }, 10000);
            if (win.MutationObserver) {
                redraw.watch = new win.MutationObserver(function() {
                    if (!out.querySelector('iframe[data-maidr-chart]')) maidrLetGo(el);
                });
                redraw.watch.observe(out, {childList: true, subtree: true});
            }
        }
        function maidrLetGo(el) {
            var redraw = el.maidrRedraw;
            if (!redraw) return;
            el.maidrRedraw = null;
            el.ownerDocument.defaultView.clearTimeout(redraw.timer);
            if (redraw.watch) redraw.watch.disconnect();
            maidrHold(el, 'redraw', 0);
        }
        // A frame that has measured its chart lets go of the output held
        // for it, the frame it replaced having gone.
        function maidrRedrawn(iframe) {
            for (var el = iframe.parentElement; el; el = el.parentElement) {
                if (el.maidrRedraw && el.maidrRedraw.old.indexOf(iframe) < 0) {
                    maidrLetGo(el);
                    return;
                }
            }
        }
        // The room kept below a fitted chart for maidr's text: a line, or
        // the lines its text takes, the most it has taken in a box of this
        // size (half the box at most; longer text is scrolled to). The
        // three lines it says as the chart takes the focus, kept to one,
        // scrolled the box 18-36px and the top of the chart, and of its
        // focus ring, out of it; kept to the most so far, the chart is not
        // resized with each announcement.
        function maidrTextRoom(doc, iframe, room, width) {
            var line = maidrTextLine(doc);
            var size = room + 'x' + width;
            if (iframe.maidrTextFor !== size) {
                iframe.maidrTextFor = size;
                iframe.maidrTextRoom = line;
            }
            var text = doc.getElementById('maidr-text-container');
            if (text && text.textContent.trim()) {
                var font = parseFloat(
                    doc.defaultView.getComputedStyle(doc.body).fontSize) || 16;
                var need = Math.ceil(text.getBoundingClientRect().height + 2 * font);
                iframe.maidrTextRoom = Math.max(iframe.maidrTextRoom,
                    Math.min(need, Math.floor(room / 2)));
            }
            return iframe.maidrTextRoom;
        }
        function maidrFitChart(doc, chart, room, width, iframe) {
            var root = doc.documentElement;
            chart.style.width = '';
            chart.style.height = '';
            chart.style.maxWidth = '';
            doc.body.style.paddingTop = '';
            if (!(room > 0) || !(width > 0)) {
                root.removeAttribute('data-maidr-fit-box');
                return;
            }
            root.setAttribute('data-maidr-fit-box', '');
            var w = chart.width.baseVal.value;
            var h = chart.height.baseVal.value;
            var space = room - maidrTextRoom(doc, iframe, room, width);
            var scale = Math.min(width / w, Math.max(space, 96) / h);
            // Its width alone: its height follows its shape, and it is never
            // wider than the frame (frame.css).
            chart.style.width = (w * scale) + 'px';
            if (space > h * scale) {
                doc.body.style.paddingTop = ((space - h * scale) / 2) + 'px';
            }
        }
        // A chart that takes its height from its container -- a Plotly
        // figure with no height of its own, a Bokeh plot stretched or
        // scaled to it, a Vega-Lite chart of height "container" -- given
        // this height. plotly.js draws it again at
        // that height later, after a debounce: the frame was measured
        // before it had, and kept the old plot's height until something
        // else measured it -- full screen left a Plotly chart's text below
        // its frame, out of sight. ``redrawn`` measures it once plotly.js, or
        // Vega, has drawn it; the height is then the one set, so that measuring
        // resizes nothing.
        function maidrFillHeight(doc, height, redrawn, keepsShape) {
            var plot = doc.querySelector(
                '.js-plotly-plot, [id^="maidr-bokeh-"][id$="-plot"], .vega-embed'
            );
            if (!plot) return;
            height = Math.max(Math.floor(height), 96);
            if (keepsShape) height = maidrKeepShape(plot, height);
            var px = height + 'px';
            if (plot.style.height === px) return;
            plot.style.height = px;
            if (plot.classList.contains('vega-embed')) {
                // Vega reads a container's height on the window's resize,
                // and draws the chart again later. Measured once it has:
                // a chart drawn shorter left the frame at its old height,
                // which nothing else measured, blank below the text.
                try {
                    var win = doc.defaultView;
                    plot.maidrRedrawn = redrawn;
                    var marks = plot.querySelector('.marks');
                    if (marks && !plot.maidrMarks && win.ResizeObserver) {
                        plot.maidrMarks = new win.ResizeObserver(function() {
                            if (plot.maidrRedrawn) plot.maidrRedrawn();
                        });
                        plot.maidrMarks.observe(marks);
                    }
                    win.dispatchEvent(new win.Event('resize'));
                } catch (_) {}
            }
            var plotly = doc.defaultView.Plotly;
            if (plot.classList.contains('js-plotly-plot') && plotly && plotly.Plots
                    && plot._fullLayout) {
                try {
                    var done = plotly.Plots.resize(plot);
                    if (done && done.then) done.then(redrawn, redrawn);
                } catch (_) {}
            }
        }
        // A Bokeh plot scaled both ways (sizing_mode="scale_both") keeps
        // its shape, and takes its size from its container's width alone:
        // given the box's height, it was as tall as it was wide, 1256px in
        // a 450px plot, and painted over maidr's text. Once Bokeh has drawn
        // it, it is kept as wide as that height allows at its shape, and
        // centred; the height it is then given is the one its width
        // allows, where that is less.
        function maidrKeepShape(plot, height) {
            var drawn = plot.firstElementChild;
            var rect = drawn && drawn.getBoundingClientRect();
            if (!rect || !(rect.width > 0) || !(rect.height > 0)) return height;
            var shape = rect.width / rect.height;
            var px = Math.floor(height * shape) + 'px';
            if (plot.style.maxWidth !== px) {
                plot.style.maxWidth = px;
                plot.style.marginLeft = 'auto';
                plot.style.marginRight = 'auto';
            }
            return Math.max(Math.min(height, Math.floor(plot.clientWidth / shape)), 96);
        }
        // A chart that takes its width from a box of a height of its own
        // keeps the box's scrollbar's room, whether the box scrolls or not.
        // Where scrollbars take room (Windows'), maidr's braille and review
        // fields and a long announcement made the box scroll and stop as
        // they came and went, and plotly.js drew the chart again at each
        // width, throwing ("reading 'mo'") while a bar was highlighted.
        function maidrKeepGutter(iframe, keep) {
            var box = iframe.parentElement;
            var gutter = keep ? 'stable' : '';
            if (box && box.style.scrollbarGutter !== gutter) {
                box.style.scrollbarGutter = gutter;
            }
        }
        // maidr's text, once it changed, in the box, which alone is
        // scrolled: as maidrShowField shows a field, without moving the page.
        function maidrShowText(doc, iframe) {
            var box = iframe.parentElement;
            var text = doc.getElementById('maidr-text-container');
            var said = text ? text.textContent : '';
            if (!box || said === iframe.maidrSaid) return;
            iframe.maidrSaid = said;
            if (!said.trim() || box.scrollHeight <= box.clientHeight + 1) return;
            var frame = iframe.getBoundingClientRect();
            var rect = text.getBoundingClientRect();
            var top = box.getBoundingClientRect().top + box.clientTop;
            var over = frame.top + rect.bottom - (top + box.clientHeight);
            var under = top - (frame.top + rect.top);
            if (under > 0) {
                box.scrollTop -= under;
            } else if (over > 0) {
                box.scrollTop += Math.min(over, -under);
            }
        }
"""

#: How a Shiny app's frame hears that the box it is shown in changed size,
#: which its own window does not report when the frame keeps its width or
#: height: a box that grew taller, or wider than a frame a fixed-width chart
#: had widened. Every Shiny frame has it; see :data:`_BOX_JS`.
_WATCH_BOX_JS = """
        function maidrWatchBox(iframe, onChange) {
            var box = iframe.parentElement;
            var win = iframe.ownerDocument.defaultView;
            if (!box || !win.ResizeObserver) return;
            // One observer per box: a frame loaded again replaces its own.
            if (box.maidrBoxObserver) box.maidrBoxObserver.disconnect();
            box.maidrBoxObserver = new win.ResizeObserver(onChange);
            box.maidrBoxObserver.observe(box);
        }
"""

#: How a notebook's matplotlib frame hears that it needs measuring again; see
#: :func:`wrap_in_iframe_matplotlib`. ``FRAME_SVG_CLASS`` stands for the class.
_NOTEBOOK_LISTENERS_JS = """
            var lastWidth = iframe.contentWindow.innerWidth;
            iframe.contentWindow.addEventListener('resize', function() {
                var width = iframe.contentWindow.innerWidth;
                if (width !== lastWidth) {
                    lastWidth = width;
                    scheduleResize();
                }
            });
            iframe.contentWindow.document.addEventListener('focusin', scheduleResize, true);
            iframe.contentWindow.document.addEventListener('focusout', scheduleResize, true);
            maidrWatch(iframe.contentWindow.document, scheduleResize);
            var chartBack = new MutationObserver(function() {
                if (iframe.contentWindow.document.querySelector('svg.FRAME_SVG_CLASS')) {
                    chartBack.disconnect();
                    scheduleResize();
                }
            });
            chartBack.observe(
                iframe.contentWindow.document.body, { childList: true, subtree: true }
            );
"""


#: Where a Shiny app's frames find their script: see :func:`shiny_frame_script`.
SHINY_FRAME_DIR = Path(__file__).resolve().parent.parent / "assets" / "shiny"
SHINY_FRAME_FILE = "frame.js"

#: The dependency that serves it, under ``lib/<name>-<version>/``.
SHINY_FRAME_NAME = "maidr-shiny-frame"


def shiny_frame_script(kinds: tuple = ("matplotlib", "plotly")) -> str:
    """The script every chart frame in a Shiny app sizes itself with.

    A Shiny app sends a frame, ``onload`` and all, over its websocket with
    every flush of the output, and the script that sizes it was most of
    what it sent: 11 KB, every chart, every time an input moved. It is
    served once instead, as :func:`shiny_frame_dependency`, which the
    browser keeps, and a frame's ``onload`` only names its kind and its
    options (:func:`_shiny_onload`). It fits the frame to its output as a
    notebook's frame fits the output area, and the chart to the output's
    box; while a dialog of maidr's is open, it lays the frame out as a
    notebook's frame is. See :data:`_BOX_JS` and :func:`_for_host`.

    ``maidr/assets/shiny/frame.js`` is this, written out; a test keeps the
    two the same. After changing what goes into it, write it again::

        python -c "from maidr.util.iframe_utils import write_shiny_frame_script; write_shiny_frame_script()"

    Parameters
    ----------
    kinds : tuple of str, default ("matplotlib", "plotly")
        The kinds of frame it sizes: the served script sizes both, and a
        frame that carries its script carries its own kind's.

    Returns
    -------
    str
        The script.
    """
    # A Shiny page's own stylesheet (Bootstrap's) scrolls it smoothly, a
    # scroll the script makes included: the page was put back where it was
    # scrolled to over a quarter of a second, and the frame's next measure
    # stopped that halfway, the dialog cut, the page at its top.
    keep_scroll = _KEEP_SCROLL_JS.replace(
        """                    if (el.scrollTop !== top) el.scrollTop = top;
                    if (el.scrollLeft !== kept[i][2]) el.scrollLeft = kept[i][2];""",
        """                    if (el.scrollTop !== top || el.scrollLeft !== kept[i][2]) {
                        el.scrollTo({top: top, left: kept[i][2], behavior: 'instant'});
                    }""",
    )
    assert keep_scroll != _KEEP_SCROLL_JS
    # A Shiny page's header fixed at the window's top (a navbar of
    # position="fixed-top") or sticky there covers what is scrolled under
    # it, the top of the dialog among them: the dialog's room is what the
    # window shows below it (maidrCover), and the frame is scrolled to
    # below it (its scroll margin).
    dialog_room = _replace_once(
        _replace_once(
            _DIALOG_ROOM_JS,
            """            if (scroller) {
                height = Math.min(height, scroller.clientHeight);""",
            """            iframe.maidrCover = scroller ? 0 : maidrCover(iframe);
            height -= iframe.maidrCover;
            if (scroller) {
                height = Math.min(height, scroller.clientHeight);""",
        ),
        """                iframe.scrollIntoView({block: 'center', inline: 'nearest'});""",
        """                iframe.style.scrollMarginTop = iframe.maidrCover + 'px';
                iframe.scrollIntoView(
                    {block: 'center', inline: 'nearest', behavior: 'instant'}
                );""",
    )
    helpers = (
        _OUTPUT_WIDTH_JS
        + keep_scroll
        + _NOT_LAID_OUT_JS
        + _COVER_JS
        + dialog_room
        + _WATCH_JS
        + _BOX_JS.replace("FRAME_SVG_CLASS", FRAME_SVG_CLASS).replace(
            "FRAME_STYLE", _frame_css(in_shiny=False)
        )
        + _WATCH_BOX_JS
    )
    matplotlib = _matplotlib_resizer("frame", fits_output=True, in_shiny=True)
    plotly = _plotly_resizer("frame", fits_output=True, in_shiny=True)
    has = " && ".join(f"kinds.{kind}" for kind in kinds)
    register = "\n".join(
        f"    if (!kinds.{kind}) kinds.{kind} = {kind}Frame;" for kind in kinds
    )
    script = f"""// The script that sizes a maidr chart's frame in a Shiny app, served
// once rather than sent with every flush of the output. Written by
// maidr/util/iframe_utils.py (shiny_frame_script); do not edit by hand.
(function () {{
    // One copy per kind of chart is enough: a frame that carries its
    // script (_shiny_onload) brings its own kind's alone.
    var kinds = window.maidrShinyKinds = window.maidrShinyKinds || {{}};
    if ({has}) return;
{helpers}
    // The rest of frame.css, which the frame's document starts without:
    // focus rings, a dialog's band, a fitted chart's centring.
    function maidrFrameStyle(frame) {{
        var doc = frame.contentWindow && frame.contentWindow.document;
        if (!doc || doc.getElementById('maidr-frame-style')) return;
        var style = doc.createElement('style');
        style.id = 'maidr-frame-style';
        style.textContent = {json.dumps(_shiny_frame_css()[1])};
        (doc.head || doc.documentElement).appendChild(style);
    }}
    function matplotlibFrame(frame, options) {{
        maidrFrameStyle(frame);
{matplotlib}
    }}
    function plotlyFrame(frame, options) {{
        maidrFrameStyle(frame);
{plotly}
    }}
{register}
    if (window.maidrShinyFrame) return;
    window.maidrShinyFrame = function (frame, kind, options) {{
        kinds[kind](frame, options || {{}});
    }};
    if (window.jQuery) {{
        // Shiny runs this in its message loop, where an error stops the
        // outputs after this one from updating; and an output Shiny has no
        // binding for sends its value to the document itself.
        window.jQuery(document).on('shiny:value', function (event) {{
            try {{
                if (event.target && event.target.nodeType === 1) {{
                    maidrHoldRedraw(event.target);
                }}
            }} catch (e) {{}}
        }});
    }}
}})();
"""
    lines = (line.rstrip() for line in script.splitlines())
    return "\n".join(lines).replace("\n\n\n", "\n\n") + "\n"


def write_shiny_frame_script() -> None:
    """Write :func:`shiny_frame_script` to ``maidr/assets/shiny/frame.js``."""
    (SHINY_FRAME_DIR / SHINY_FRAME_FILE).write_text(
        shiny_frame_script(), encoding="utf-8"
    )


@lru_cache(maxsize=1)
def _shiny_frame_version() -> str:
    """The served script's version: the package's, and its content's digest.

    The digest is in the URL Shiny serves it from, so that a browser holding
    an older copy fetches the new one even where the package's version has
    not moved, as it does not between development builds. It is a local
    version label led by ``g``, as setuptools-scm writes a commit's: twelve
    hex digits that happened to be all numbers with a leading zero would
    otherwise be normalised -- ``0123`` to ``123`` -- and the version Shiny
    serves it under would not be the one written here.
    """
    from maidr import __version__

    text = (SHINY_FRAME_DIR / SHINY_FRAME_FILE).read_bytes()
    local = "." if "+" in __version__ else "+"
    return f"{__version__}{local}g{hashlib.sha256(text).hexdigest()[:12]}"


def shiny_frame_dependency() -> HTMLDependency:
    """The dependency that serves :func:`shiny_frame_script` to a Shiny page.

    A child of every chart frame :class:`maidr.widget.shiny.render_maidr`
    sends, so that its output loads it. Shiny loads a dependency's scripts
    before it puts the output's HTML in the page, and then once per page
    however many charts name it. A frame made in a Shiny app any other way
    carries the script instead; see :func:`_shiny_onload`.

    Returns
    -------
    htmltools.HTMLDependency
        The dependency.
    """
    return HTMLDependency(
        name=SHINY_FRAME_NAME,
        version=_shiny_frame_version(),
        source={"package": "maidr", "subdir": "assets/shiny"},
        script={"src": SHINY_FRAME_FILE},
    )


#: Set while :class:`maidr.widget.shiny.render_maidr` renders a chart: the
#: output it sends carries the frame's dependency, so the frame names its
#: kind and options alone. Any other frame made in a Shiny app carries its
#: script; see :func:`_shiny_onload`.
_DEPENDENCY_SENT: ContextVar[bool] = ContextVar(
    "maidr_shiny_frame_dependency_sent", default=False
)


@contextmanager
def shiny_frame_dependency_sent() -> Iterator[None]:
    """Render frames that reach the page with their dependency, for certain.

    :class:`maidr.widget.shiny.render_maidr` renders inside it: what it
    sends is the frame as a tag, dependency and all, so the frame's
    ``onload`` only names its kind and options, and the flush is as small
    as before.
    """
    token = _DEPENDENCY_SENT.set(True)
    try:
        yield
    finally:
        _DEPENDENCY_SENT.reset(token)


@lru_cache(maxsize=2)
def _shiny_frame_inline(kind: str) -> str:
    """:func:`shiny_frame_script` as a frame of ``kind`` carries it.

    Its own kind's alone, compacted (:func:`maidr.util.compact.compact_js`):
    about 21 KB, where the served script is 56 KB. Plain text, which every
    browser runs, as a frame's ``onload`` always carried its script: packed,
    it was smaller, but a browser that could not unpack it (before Safari
    16.4, Firefox 113 or Chrome 103) left the frame 150px tall, its chart
    cut off.
    """
    return compact_js(shiny_frame_script((kind,)))


def _shiny_onload(kind: str, options: dict | None = None, carried: bool = False) -> str:
    """A Shiny app's frame's ``onload``: its kind and options, and maybe its script.

    A frame :class:`maidr.widget.shiny.render_maidr` sends comes with
    :func:`shiny_frame_dependency`, which Shiny loads before it puts the
    output's HTML in the page; its ``onload`` names its kind and options for
    the served script, and waits for it, briefly, should anything put the
    frame in a page another way, saying so in the console if it waited in
    vain. Any other frame -- :func:`maidr.render` returned from
    ``render.ui``, turned into a string, kept for another session, written
    to a file -- carries the script itself (``carried``), as a frame's
    ``onload`` always had: such a frame can lose a dependency on its way to
    the page, and needs nothing served. It carries it compacted
    (:func:`_shiny_frame_inline`); the script registers its kind once per
    page, and returns at once wherever that kind is registered already, by
    the served script or by another frame.

    Parameters
    ----------
    kind : {"matplotlib", "plotly"}
        Which script sizes the frame: a matplotlib chart's, or the one
        Plotly, Bokeh and Altair charts share.
    options : dict, optional
        What differs from one such chart to the next.
    carried : bool, default False
        Whether the frame carries the script (:func:`_shiny_frame_inline`).

    Returns
    -------
    str
        The ``onload`` attribute's script.
    """
    given = json.dumps(options or {}, separators=(",", ":"))
    if carried:
        return (
            f"var f=this;{_shiny_frame_inline(kind)}"
            f"maidrShinyFrame(f,'{kind}',{given})"
        )
    return (
        "var f=this;(function g(n){var k=window.maidrShinyKinds;if(k&&k."
        f"{kind})maidrShinyFrame(f,'{kind}',{given});"
        "else if(n<200)setTimeout(function(){g(n+1)},50);"
        "else console.warn('maidr: maidr-shiny-frame did not load; "
        "this chart is not sized')})(0)"
    )


def _frame_css(in_shiny: bool) -> str:
    """The frame's own style; a block in a Shiny app's box, so that no line's
    descent is left below it, which made the box taller than the frame."""
    style = "background-color: #fff; position: relative; border: none"
    return style + "; display: block" if in_shiny else style


#: Marks a line of a frame's script as a Shiny app's alone (``@S``) or as
#: every other frame's alone (``@N``); see :func:`_for_host`.
_HOST_LINE = re.compile(r"^(\s*)@([SN]) ")


def _mark(host: str, lines: str) -> str:
    """``lines`` marked as one host's (``@S`` or ``@N``); see :func:`_for_host`."""
    return "\n".join(
        re.sub(r"^(\s*)", rf"\g<1>@{host} ", line, count=1)
        for line in lines.split("\n")
    )


#: How a notebook's matplotlib frame is as wide as its output area; a Shiny
#: app's frame is so too while a dialog of maidr's is open. See
#: :func:`_matplotlib_resizer`.
_NOTEBOOK_WIDTH_JS = """\
                    // While a dialog of maidr's is open, the frame
                    // may be as wide as MUI makes a dialog (600px, and 32px
                    // either side), so that a small chart's frame does not
                    // squeeze it.
                    let dialogOpen = iframeDocument.querySelector('.MuiDialog-root');
                    iframe.style.width = maidrOutputWidth(iframe, false);
                    iframe.style.maxWidth = Math.max(own + side, dialogOpen ? 664 : 0) + 'px';"""


def _for_host(script: str, in_shiny: bool) -> str:
    """A frame's script for a Shiny app, or for anywhere else.

    The script that sizes a notebook's frame, or a frame elsewhere, is the
    one it has always been; a Shiny app's adds the fitting to its box (see
    :data:`_BOX_JS`), and while a dialog of maidr's is open runs the lines
    a notebook's frame runs. Its lines of its own are marked
    ``@S``, and the lines it replaces ``@N``; each kind of frame keeps its
    own, unmarked, and drops the other's.

    Parameters
    ----------
    script : str
        The marked script.
    in_shiny : bool
        Whether the frame is a Shiny app's.

    Returns
    -------
    str
        The script.
    """
    keep = "S" if in_shiny else "N"
    lines = []
    for line in script.split("\n"):
        mark = _HOST_LINE.match(line)
        if mark is None:
            lines.append(line)
        elif mark.group(2) == keep:
            lines.append(mark.group(1) + line[mark.end() :])
    return "\n".join(lines)


def _shiny_frame(kind: str, options: dict | None = None) -> tuple[list, str]:
    """A Shiny app's frame's dependency, if it has one, and its ``onload``.

    See :func:`_shiny_onload`: a frame :class:`maidr.widget.shiny.render_maidr`
    sends comes with the served script, and any other carries it.
    """
    served = _DEPENDENCY_SENT.get()
    children = [shiny_frame_dependency()] if served else []
    return children, _shiny_onload(kind, options, carried=not served)


def wrap_in_iframe_matplotlib(
    base_html: Tag,
    chart_title: str | None = None,
    alt: str | None = None,
    *,
    in_notebook: bool = False,
    in_shiny: bool = False,
) -> Tag:
    """Wrap matplotlib HTML in an auto-resizing iframe for notebooks.

    In a notebook (``in_notebook``) the frame stands where the notebook
    would show the figure's image, and holds the chart as the output area
    holds the image: it is as wide as the output area, up to the chart's own
    width -- that of the ``<svg>`` marked :data:`FRAME_SVG_CLASS` -- and the
    chart shrinks with it, keeping its shape, rather than the output area
    scrolling sideways. Its document has :func:`frame_style`. Its height is
    measured again whenever the frame's width or its content changes, and
    while a dialog of maidr's is open the frame is as tall as the part of
    the notebook a reader sees, and the dialog is scrolled into it. The
    notebook's scroll position is kept while the frame is measured.

    In a Shiny app (``in_shiny``) the frame fits its output the same way,
    without the padding a notebook keeps to an output's right, and fits the
    chart to the box it is shown in when that box has a height of its own;
    while a dialog of maidr's is open, it is laid out as a notebook's frame
    is; see :data:`_BOX_JS`. Elsewhere -- Flask, a Pyodide page -- the frame is
    as wide as its content.

    Parameters
    ----------
    base_html : Tag
        The HTML tag containing the matplotlib plot and MAIDR scripts.
    chart_title : str, optional
        The chart's own title, which leads the frame's accessible name. See
        :func:`iframe_title`.
    alt : str, optional
        The alt text of the Quarto cell the chart is drawn in, which names
        the frame instead.
    in_notebook : bool, default=False
        Whether the frame goes into a notebook's output.
    in_shiny : bool, default=False
        Whether the frame goes into a Shiny app's output.

    Returns
    -------
    Tag
        An iframe tag wrapping the original HTML with auto-resizing logic.
    """
    unique_id = _generate_unique_id()
    fits_output = in_notebook or in_shiny
    children: list = []
    if in_shiny:
        children, onload = _shiny_frame("matplotlib")
    else:
        helpers = _NOTEBOOK_JS + _WATCH_JS if fits_output else ""
        onload = (
            f"\n        {helpers}"
            + _matplotlib_resizer(
                f"document.getElementById('{unique_id}')", fits_output=fits_output
            )
        )

    srcdoc = str(base_html.get_html_string())
    if fits_output:
        srcdoc = _frame_style(in_shiny) + srcdoc
    return tags.iframe(
        *children,
        id=unique_id,
        title=iframe_title(chart_title, alt),
        # Marks this frame as maidr's own. A host page may put other
        # iframes in the same container, and anything keying off "an
        # iframe is the chart" -- the Shiny focus restore does -- would
        # otherwise act on one of those. See `maidr/widget/_focus.py`.
        **{"data-maidr-chart": ""},
        allow=_ALLOWED_FEATURES,
        srcdoc=srcdoc,
        width="100%",
        height="100%",
        scrolling="no",
        style=_frame_css(in_shiny),
        frameBorder=0,
        onload=onload,
    )


def _matplotlib_resizer(
    frame: str, *, fits_output: bool, in_shiny: bool = False
) -> str:
    """The script that sizes a matplotlib chart's frame, as its ``onload`` runs it.

    Parameters
    ----------
    frame : str
        A JavaScript expression for the frame.
    fits_output : bool
        Whether the frame fits its output: a notebook's or a Shiny app's.
    in_shiny : bool, default=False
        Whether it is a Shiny app's, which also fits the chart to its box;
        see :func:`_for_host`.

    Returns
    -------
    str
        The script, without the helpers it calls.
    """
    fits = "true" if fits_output else "false"
    # In a notebook the frame is measured again when the output area narrows
    # or widens -- a change of the frame's width only: its height is set as
    # it is measured, at none for a moment, which resizes its window too, and
    # measured it again on every frame for as long as the notebook was open
    # -- when maidr's text or fields or a dialog come, go or change
    # (``maidrWatch``), when the focus moves, and once maidr.js has put the
    # chart back in the document, which it takes out as it starts: in a cell
    # JupyterLab does not draw while it is out of view, the frame's window
    # reports no resize, and the frame was left with no height until the
    # reader scrolled to it. A Shiny app's frame, besides, when its box
    # changes size.
    notebook_listeners = (
        _NOTEBOOK_LISTENERS_JS.replace("FRAME_SVG_CLASS", FRAME_SVG_CLASS)
        if fits_output
        else ""
    )
    if in_shiny:
        notebook_listeners += """
            maidrWatchBox(iframe, scheduleResize);
"""

    # The script runs as the frame's document loads, and again whenever it
    # is loaded again (a frame taken out of the page and put back), giving
    # each document its own listeners and observers. It replaced itself after
    # its first run, which left a document loaded again with only a resize
    # listener, and no height.
    script = f"""
        function resizeIframe() {{
            @N let fitsOutput = {fits};
            let iframe = {frame};
            @S // Fitted to its box, or, while a dialog is open, laid out as
            @S // a notebook's frame is (maidrSuspendBox).
            @S let fitted = !maidrSuspendBox(iframe);
            @S let fitsOutput = true;
            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            if (
                iframe && iframe.contentWindow &&
                iframe.contentWindow.document &&
                iframe.contentWindow.document.body
            ) {{
                let iframeDocument = iframe.contentWindow.document;
                let body = iframeDocument.body;
                let de = iframeDocument.documentElement;
                @N let restoreScroll = fitsOutput ? maidrKeepScroll(iframe) : null;
                @S let letGo = fitted ? maidrHoldStill(iframe) : null;
                @S let restoreScroll = fitted
                @S     ? maidrKeepBoxScroll(iframe) : maidrKeepScroll(iframe);
                let before = iframe.style.height;
                @N let room = fitsOutput ? maidrDialogRoom(iframeDocument, iframe) : 0;
                @S let room = fitted ? 0 : maidrDialogRoom(iframeDocument, iframe);

                let bodyStyle = iframe.contentWindow.getComputedStyle(body);
                let side = (parseFloat(bodyStyle.marginLeft) || 0)
                    + (parseFloat(bodyStyle.marginRight) || 0);
                // In a notebook the frame is as wide as the output area, up to
                // the chart's own width, the width the svg was given (the
                // plain figure's), and the chart shrinks with it (frame.css),
                // as the figure's image shrinks to the output area. A width
                // in CSS, so the frame follows the output area as it narrows
                // or widens, with nothing to run.
                let chart = fitsOutput
                    ? iframeDocument.querySelector('svg.{FRAME_SVG_CLASS}')
                    : null;
                let own = chart && chart.width && chart.width.baseVal
                    ? chart.width.baseVal.value
                    : 0;
                if (own > 0) {{
{_mark('N', _NOTEBOOK_WIDTH_JS)}
                    @S if (fitted) {{
                    @S     // In a Shiny app, the chart is fitted to its box
                    @S     // when the box has a height of its own, and is then
                    @S     // as wide as the box.
                    @S     iframe.style.width = maidrOutputWidth(iframe, true);
                    @S     let boxRoom = maidrBoxRoom(iframe);
                    @S     maidrFitChart(
                    @S         iframeDocument, chart, boxRoom, maidrBoxWidth(iframe), iframe
                    @S     );
                    @S     iframe.style.maxWidth = boxRoom > 0 ? '' : (own + side) + 'px';
                    @S }} else {{
{_mark('S', _NOTEBOOK_WIDTH_JS)}
                    @S }}
                }} else if (fitsOutput) {{
                    // Until maidr.js has put the chart back: narrowed to
                    // nothing, the frame had no width to measure it at.
                    @N iframe.style.width = maidrOutputWidth(iframe, false);
                    @S iframe.style.width = maidrOutputWidth(iframe, fitted);
                    iframe.style.maxWidth = '';
                }} else {{
                    // The width comes first, so the height below is measured
                    // at the width the frame keeps. body.scrollWidth is never
                    // less than the body's own width, so the frame is
                    // narrowed to nothing before it is read, and the content
                    // alone sets it. It is measured from the body's edge, so
                    // the body's margins are added back; without them the
                    // frame cut 8px, and the focus outline, off the chart's
                    // right side (#893).
                    iframe.style.width = '0px';
                    iframe.style.width = (body.scrollWidth + side) + 'px';
                }}

                // In a notebook the height is measured with the frame at
                // none, so that the 150px an iframe is left at is no floor
                // under a short chart.
                iframe.style.height = fitsOutput ? '0px' : 'auto';

                // Use Math.max() across multiple DOM measurements (industry standard)
                let height = Math.max(
                    body.scrollHeight || 0,
                    body.offsetHeight || 0,
                    de.scrollHeight || 0,
                    de.offsetHeight || 0,
                    fitsOutput ? 0 : (de.clientHeight || 0)
                );

                // Scan specific MAIDR elements with getBoundingClientRect()
                // This ensures elements with overflow:visible parents are included
                let selectors = [
                    '#maidr-rotor-area',
                    '#maidr-text-container',
                    '[id^="maidr-braille-textarea"]',
                    '.maidr-review-input'
                ];
                for (let i = 0; i < selectors.length; i++) {{
                    let el = iframeDocument.querySelector(selectors[i]);
                    if (el) {{
                        let rect = el.getBoundingClientRect();
                        let bottom = rect.bottom + (iframe.contentWindow.scrollY || 0);
                        if (bottom > height) {{
                            height = bottom;
                        }}
                    }}
                }}

                // Detect braille textarea by dynamic id prefix
                let brailleContainer = iframeDocument.querySelector('[id^="maidr-braille-textarea"]');
                // Detect review input container by class name
                let reviewInputContainer = iframeDocument.querySelector('.maidr-review-input');
                // Consider braille active if it or any descendant has focus
                let isBrailleActive = brailleContainer && (
                    brailleContainer === iframeDocument.activeElement ||
                    (typeof brailleContainer.contains === 'function' && brailleContainer.contains(iframeDocument.activeElement))
                );
                // Consider review input active if it or any descendant has focus
                let isReviewInputActive = reviewInputContainer && (
                    reviewInputContainer === iframeDocument.activeElement ||
                    (typeof reviewInputContainer.contains === 'function' && reviewInputContainer.contains(iframeDocument.activeElement))
                );

                // Add buffer for active states (rotor-area height is measured directly above)
                if (isBrailleActive) {{
                    height += 100;
                }} else if (isReviewInputActive) {{
                    height += 50;
                }}
                height = Math.max(height, room);
                @S if (fitted) height = maidrSteady(iframe, height);
                iframe.style.height = (height) + 'px';
                if (restoreScroll) restoreScroll();
                @S if (letGo) letGo();
                @S if (fitted && own > 0) maidrRedrawn(iframe);
                if (fitsOutput) {{
                    let resized = iframe.style.height !== before;
                    maidrShowDialog(iframeDocument, iframe, room, resized);
                    maidrShowField(iframeDocument, resized);
                }}
                @S if (fitted) maidrShowText(iframeDocument, iframe);
            }}
        }}
        let iframe = {frame};
        resizeIframe();
        // Delegate focus events for braille textarea (by id prefix)
        iframe.contentWindow.document.addEventListener('focusin', (e) => {{
            try {{
                const t = e && e.target ? e.target : null;
                if (t && typeof t.id === 'string' && t.id.startsWith('maidr-braille-textarea')) resizeIframe();
            }} catch (_) {{ resizeIframe(); }}
        }}, true);
        iframe.contentWindow.document.addEventListener('focusout', (e) => {{
            try {{
                const t = e && e.target ? e.target : null;
                if (t && typeof t.id === 'string' && t.id.startsWith('maidr-braille-textarea')) resizeIframe();
            }} catch (_) {{ resizeIframe(); }}
        }}, true);
        // Delegate focus events for review input container (by class name)
        iframe.contentWindow.document.addEventListener('focusin', (e) => {{
            try {{
                const t = e && e.target ? e.target : null;
                if (t && t.classList && t.classList.contains('maidr-review-input')) resizeIframe();
            }} catch (_) {{ resizeIframe(); }}
        }}, true);
        iframe.contentWindow.document.addEventListener('focusout', (e) => {{
            try {{
                const t = e && e.target ? e.target : null;
                if (t && t.classList && t.classList.contains('maidr-review-input')) resizeIframe();
            }} catch (_) {{ resizeIframe(); }}
        }}, true);
        // Modern resize detection: ResizeObserver with MutationObserver fallback
        try {{
            let rafId = 0;
            let scheduleResize = function() {{
                cancelAnimationFrame(rafId);
                rafId = requestAnimationFrame(function() {{
                    resizeIframe();
                }});
            }};

            {notebook_listeners}
            // Try ResizeObserver first (modern, more efficient)
            if (typeof iframe.contentWindow.ResizeObserver !== 'undefined') {{
                new iframe.contentWindow.ResizeObserver(scheduleResize).observe(
                    iframe.contentWindow.document.body
                );
            }} else {{
                // Fallback to MutationObserver (observe entire document for all changes)
                new MutationObserver(scheduleResize).observe(
                    iframe.contentWindow.document.body,
                    {{ childList: true, subtree: true, characterData: true, attributes: true }}
                );
            }}
        }} catch (_) {{}}
    """
    return _for_host(script, in_shiny)


def wrap_in_iframe_plotly(
    base_html: Tag,
    chart_title: str | None = None,
    alt: str | None = None,
    *,
    in_notebook: bool = False,
    keep_padding: bool = False,
    fill_width: bool = False,
    in_shiny: bool = False,
    fill_height: int = 0,
    keep_shape: bool = False,
) -> Tag:
    """Wrap Plotly HTML in an auto-resizing iframe for notebooks.

    Mirrors the focus-delegation logic from the matplotlib wrapper
    but adds Plotly-specific handling for overflow containers and
    MAIDR element scanning. Bokeh and Altair charts use it too.

    In a notebook (``in_notebook``) the frame's document has
    :func:`frame_style`, and the frame holds the whole chart: its height
    counts the margins of what the document starts and ends with, which cut
    the bottom of a Bokeh chart, its x-axis label with it, and a chart of a
    fixed width wider than the output area widens the frame, so that the
    output area scrolls to it as it scrolls to the plain chart, rather than
    the frame cutting it off; the output area keeps where it was scrolled to
    when the frame is measured. A dialog of maidr's gets room, as in the
    matplotlib frame.

    In a Shiny app (``in_shiny``) the frame fits its output the same way,
    without the padding a notebook keeps to an output's right; the box
    :class:`maidr.widget.shiny.render_maidr` puts around it scrolls to a
    chart wider than the output. A chart that takes its container's width
    (``fill_width``) never widens the frame there: it is narrower once it
    has followed a narrower output, and measured before it had, it held the
    frame at its old width for good.

    Parameters
    ----------
    base_html : Tag
        The HTML tag containing the Plotly chart and MAIDR scripts.
    chart_title : str, optional
        The chart's own title, which leads the frame's accessible name. See
        :func:`iframe_title`.
    alt : str, optional
        The alt text of the Quarto cell the chart is drawn in, which names
        the frame instead.
    in_notebook : bool, default=False
        Whether the frame goes into a notebook's output.
    keep_padding : bool, default=False
        Whether, in a notebook, the frame keeps clear of the padding to the
        right of an HTML output, as the library's own chart does there: a
        Bokeh plot, which is an HTML output itself, and an Altair chart,
        which vega-embed's menu keeps further from that edge. A Plotly
        chart takes the padding, as plotly's own renderer does.
    fill_width : bool, default=False
        Whether the chart takes the width of its container (a Bokeh
        ``sizing_mode`` that stretches or scales its width, a Vega-Lite
        ``width`` of ``"container"``, a Plotly figure with no width): in a
        notebook or a Shiny app it is then as wide as the frame; see
        ``maidr/assets/frame.css``.
    in_shiny : bool, default=False
        Whether the frame goes into a Shiny app's output.
    fill_height : int, default=0
        In a Shiny app, how tall a chart that takes its height from its
        container (a Plotly figure with no height of its own, a Bokeh
        ``sizing_mode`` that stretches or scales its height, a Vega-Lite
        ``height`` of ``"container"``) is in a box
        with no height of its own; in a box with one, it is as tall as the
        box less a line for maidr's text. 0 for a chart with a height of
        its own.
    keep_shape : bool, default=False
        Whether such a chart keeps its shape, as a Bokeh plot scaled both
        ways does: it is then no wider than that height allows.

    Returns
    -------
    Tag
        An iframe tag wrapping the original HTML with auto-resizing logic.
    """
    unique_id = _generate_unique_id()
    fits_output = in_notebook or in_shiny
    children: list = []
    if in_shiny:
        # A chart that takes its container's width never widens the frame.
        options: dict = {"widens": not fill_width}
        if fill_height:
            options["fillHeight"] = int(fill_height)
            if keep_shape:
                options["keepsShape"] = True
        children, onload = _shiny_frame("plotly", options)
    else:
        helpers = _WATCH_JS + (_NOTEBOOK_JS if fits_output else "")
        onload = f"\n        {helpers}" + _plotly_resizer(
            f"document.getElementById('{unique_id}')",
            fits_output=fits_output,
            keep_padding=keep_padding,
        )

    if fits_output and fill_width:
        base_html.add_class("maidr-frame-fill")
    srcdoc = str(base_html.get_html_string())
    if fits_output:
        width_first = "" if keep_padding or in_shiny else _OUTPUT_WIDTH_FIRST
        srcdoc = _frame_style(in_shiny) + width_first + srcdoc
    return tags.iframe(
        *children,
        id=unique_id,
        title=iframe_title(chart_title, alt),
        # Marks this frame as maidr's own. A host page may put other
        # iframes in the same container, and anything keying off "an
        # iframe is the chart" -- the Shiny focus restore does -- would
        # otherwise act on one of those. See `maidr/widget/_focus.py`.
        **{"data-maidr-chart": ""},
        allow=_ALLOWED_FEATURES,
        srcdoc=srcdoc,
        width="100%",
        height="100%",
        scrolling="no",
        style=_frame_css(in_shiny),
        frameBorder=0,
        onload=onload,
    )


def _plotly_resizer(
    frame: str,
    *,
    fits_output: bool,
    keep_padding: bool = False,
    in_shiny: bool = False,
) -> str:
    """The script that sizes a Plotly, Bokeh or Altair chart's frame.

    Parameters
    ----------
    frame : str
        A JavaScript expression for the frame.
    fits_output : bool
        Whether the frame fits its output: a notebook's or a Shiny app's.
    keep_padding : bool, default=False
        See :func:`wrap_in_iframe_plotly`.
    in_shiny : bool, default=False
        Whether it is a Shiny app's, whose script reads what differs from
        one chart to the next from ``options``, and fits the chart to its
        box; see :func:`_shiny_onload` and :func:`_for_host`.

    Returns
    -------
    str
        The script, without the helpers it calls.
    """
    fits = "true" if fits_output else "false"
    keeps = "true" if keep_padding else "false"
    script = f"""
        function resizeIframe() {{
            @N var fitsOutput = {fits};
            @N var keepsPadding = {keeps};
            var iframe = {frame};
            if (!iframe || !iframe.contentWindow || !iframe.contentWindow.document) {{
                return;
            }}
            @S // Fitted to its box, or, while a dialog is open, laid out as
            @S // a notebook's frame is (maidrSuspendBox).
            @S var fitted = !maidrSuspendBox(iframe);
            @S var fitsOutput = true;
            @S var keepsPadding = true;
            @S var widens = options.widens;

            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            var doc = iframe.contentWindow.document;
            var body = doc.body;
            if (!body) return;
            var de = doc.documentElement;
            @N var restoreScroll = fitsOutput ? maidrKeepScroll(iframe) : null;
            @S var letGo = fitted ? maidrHoldStill(iframe) : null;
            @S var restoreScroll = fitted
            @S     ? maidrKeepBoxScroll(iframe) : maidrKeepScroll(iframe);
            var before = iframe.style.height;
            @N var room = fitsOutput ? maidrDialogRoom(doc, iframe) : 0;
            @S var room = fitted ? 0 : maidrDialogRoom(doc, iframe);
            @S // In a Shiny app: the room the box gives the chart (none when
            @S // the box takes its height from the frame), and a chart that
            @S // takes its height from its container as tall as that room
            @S // less the line kept for maidr's text, or, with none,
            @S // options.fillHeight; see _BOX_JS. While a dialog is open, it
            @S // is left at the height it has: drawn again under a dialog, a
            @S // Plotly chart threw ('mo') and lost its highlight.
            @S if (fitted) {{
            @S     var boxRoom = maidrBoxRoom(iframe);
            @S     maidrKeepGutter(iframe, boxRoom > 0 && !widens);
            @S     if (options.fillHeight) {{
            @S         maidrFillHeight(doc, boxRoom > 0
            @S             ? boxRoom - maidrTextLine(doc)
            @S             : options.fillHeight, function() {{
            @S                 requestAnimationFrame(resizeIframe);
            @S             }}, options.keepsShape);
            @S     }}
            @S }}

            // WIDTH, in a notebook: a chart of a fixed width wider than the
            // output area widens the frame, so the output area scrolls to it
            // as it does to the plain chart, where scrolling="no" cut it off.
            // One that takes the frame's width never overflows it. The
            // frame is given the output area's width again only when that
            // has changed.
            if (fitsOutput) {{
                var host = iframe.parentElement;
                var hostWidth = host ? host.clientWidth : 0;
                if (iframe.maidrHostWidth !== hostWidth) {{
                    iframe.maidrHostWidth = hostWidth;
                    iframe.style.width = maidrOutputWidth(iframe, keepsPadding);
                }}
                @N if (de.scrollWidth > iframe.contentWindow.innerWidth + 1) {{
                @S // Not while a dialog is open: MUI centres it in the frame,
                @S // which is then as wide as the page shows.
                @S if (fitted && widens && de.scrollWidth > iframe.contentWindow.innerWidth + 1) {{
                    iframe.style.width = de.scrollWidth + 'px';
                }}
            }}

            // CRITICAL: Shrink iframe first to get accurate content measurement.
            // Without this, body.scrollHeight reflects the current iframe size,
            // not the natural content size (causes whitespace after braille closes).
            // In a notebook to no height at all, so that the 150px an iframe is
            // left at is no floor under the document's own height, which is
            // measured there too: it counts the margins of what the document
            // starts and ends with, which body.scrollHeight leaves out.
            iframe.style.height = fitsOutput ? '0px' : 'auto';

            // HEIGHT: Measure content after shrinking
            var height = Math.max(
                body.scrollHeight || 0,
                body.offsetHeight || 0,
                fitsOutput ? (de.scrollHeight || 0) : 0,
                fitsOutput ? (de.offsetHeight || 0) : 0
            );

            // Scan MAIDR elements for bottom edge (they extend below the chart)
            var heightSelectors = [
                'svg.main-svg',
                '#maidr-rotor-area',
                '#maidr-text-container',
                '[id^="maidr-braille-textarea"]',
                '[id^="maidr-review-input"]'
            ];
            for (var i = 0; i < heightSelectors.length; i++) {{
                var el = doc.querySelector(heightSelectors[i]);
                if (el) {{
                    var rect = el.getBoundingClientRect();
                    var bottom = rect.bottom + (iframe.contentWindow.scrollY || 0);
                    if (bottom > height) {{
                        height = bottom;
                    }}
                }}
            }}

            // Buffer for braille/review active states
            var braille = doc.querySelector('[id^="maidr-braille-textarea"]');
            var review = doc.querySelector('[id^="maidr-review-input"]');
            var isBrailleActive = braille && (
                braille === doc.activeElement ||
                braille.contains(doc.activeElement)
            );
            var isReviewActive = review && (
                review === doc.activeElement ||
                review.contains(doc.activeElement)
            );
            if (isBrailleActive) {{
                height += 100;
            }} else if (isReviewActive) {{
                height += 50;
            }}
            height = Math.max(height, room);
            @S if (fitted) height = maidrSteady(iframe, height);

            iframe.style.height = height + 'px';
            if (restoreScroll) restoreScroll();
            @S if (letGo) letGo();
            @S if (doc.querySelector('[role=img], [role=application]')) {{
            @S     maidrRedrawn(iframe);
            @S }}
            if (fitsOutput) {{
                var resized = iframe.style.height !== before;
                maidrShowDialog(doc, iframe, room, resized);
                maidrShowField(doc, resized);
            }}
            @S if (fitted) maidrShowText(doc, iframe);
        }}

        var iframe = {frame};
        resizeIframe();

        // Measure again when the frame's window changes width. Its height is
        // set here, and the window is resized when it is, measured at
        // 'auto' or none included, which measured the frame again on every
        // frame, for as long as the page was open.
        try {{
            var lastWidth = iframe.contentWindow.innerWidth;
            iframe.contentWindow.addEventListener('resize', function() {{
                var width = iframe.contentWindow.innerWidth;
                if (width !== lastWidth) {{
                    lastWidth = width;
                    resizeIframe();
                }}
            }});
        }} catch (_) {{}}

        // Delayed retries to catch async MAIDR content (plotly.js + maidr.js loading)
        setTimeout(resizeIframe, 500);
        setTimeout(resizeIframe, 1500);
        setTimeout(resizeIframe, 3000);

        // ResizeObserver with MutationObserver fallback for DOM changes
        try {{
            var _raf = 0;
            var scheduleResize = function() {{
                cancelAnimationFrame(_raf);
                _raf = requestAnimationFrame(resizeIframe);
            }};

            // maidr's text and fields, which can lie past the body's box, and
            // a dialog maidr opens or closes, which needs room or gives it back.
            maidrWatch(iframe.contentWindow.document, scheduleResize);
            @S maidrWatchBox(iframe, scheduleResize);

            if (typeof iframe.contentWindow.ResizeObserver !== 'undefined') {{
                new iframe.contentWindow.ResizeObserver(scheduleResize).observe(
                    iframe.contentWindow.document.body
                );
            }} else {{
                new MutationObserver(scheduleResize).observe(
                    iframe.contentWindow.document.body,
                    {{ childList: true, subtree: true, characterData: true, attributes: true }}
                );
            }}
        }} catch (_) {{}}

        // Focus events for braille/review buffer changes
        try {{
            iframe.contentWindow.document.addEventListener('focusin', resizeIframe, true);
            iframe.contentWindow.document.addEventListener('focusout', resizeIframe, true);
        }} catch (_) {{}}
    """
    return _for_host(script, in_shiny)
