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

import uuid

from htmltools import Tag, tags

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

#: The scroll positions of the boxes a frame scrolls in, kept while it is
#: measured. A frame is measured at no height, and a Plotly, Bokeh or Altair
#: one at the output area's width, for a moment; the boxes around it clamp
#: their scroll positions to what then fits, and a reader scrolled down a
#: notebook, or across a chart wider than its output area, was moved back to
#: its top or left edge every time the frame was measured.
#: ``maidrKeepScroll`` returns what puts them back. A frame wholly above what
#: a box shows moves what it shows by as much as the frame grew, as the
#: browser's scroll anchoring would have, so the reader's place stays put.
#: ``maidrShowField`` shows the whole of a field of maidr's that has the
#: focus once its frame has grown to hold it.
_KEEP_SCROLL_JS = """
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
        function maidrShowField(doc, resized) {
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

#: Whether a notebook's frame is not laid out: in an output the notebook
#: hides, or in a cell JupyterLab does not draw while it is out of view. Such
#: a frame has no width, and measured as nothing; it keeps its height until it
#: has one again, which its window's resize reports.
_NOT_LAID_OUT_JS = """
        function maidrNotLaidOut(iframe) {
            return !!(iframe && iframe.contentWindow && !iframe.contentWindow.innerWidth);
        }
"""

#: Room for maidr's help and settings dialogs, which MUI fixes in the frame's
#: viewport, centred, at least 32px from its edges, and scrolls within when
#: the viewport is shorter than they are. While one is open, a notebook's
#: frame is made as tall as the dialog would be on its own, up to the height
#: of the window, and not less than 480px; a chart taller than that keeps its
#: height. ``doc`` is the frame's document, ``win`` the window the frame is in.
_DIALOG_ROOM_JS = """
        function maidrDialogRoom(doc, win) {
            var paper = doc.querySelector('.MuiDialog-paper');
            if (!paper) return 0;
            var view = paper.ownerDocument.defaultView;
            var style = view.getComputedStyle(paper);
            var natural = (parseFloat(style.paddingTop) || 0)
                + (parseFloat(style.paddingBottom) || 0)
                + (parseFloat(style.borderTopWidth) || 0)
                + (parseFloat(style.borderBottomWidth) || 0);
            for (var i = 0; i < paper.children.length; i++) {
                natural += paper.children[i].scrollHeight || 0;
            }
            var room = natural
                + (parseFloat(style.marginTop) || 0)
                + (parseFloat(style.marginBottom) || 0);
            var cap = Math.max(win.innerHeight || 0, 480);
            return Math.ceil(Math.min(room, cap));
        }
"""

#: What changes a frame's height that its body's size does not show: maidr's
#: text, braille and review fields, which can lie past the body's box (a
#: Plotly or Bokeh chart's do), coming, going or changing. Their frame was
#: measured again on every frame, which this replaces: its text came out
#: below a Plotly chart's frame without it.
_WATCH_JS = """
        function maidrWatch(doc, onChange) {
            var parts = '#maidr-text-container, #maidr-rotor-area, '
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

#: What only a notebook's frame calls. A frame elsewhere leaves it out: a
#: Shiny app sends a frame's script with every flush of its output.
_NOTEBOOK_JS = _OUTPUT_WIDTH_JS + _KEEP_SCROLL_JS + _NOT_LAID_OUT_JS + _DIALOG_ROOM_JS

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
            new MutationObserver(scheduleResize).observe(
                iframe.contentWindow.document.body, { childList: true }
            );
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


def wrap_in_iframe_matplotlib(
    base_html: Tag,
    chart_title: str | None = None,
    alt: str | None = None,
    *,
    in_notebook: bool = False,
) -> Tag:
    """Wrap matplotlib HTML in an auto-resizing iframe for notebooks.

    In a notebook (``in_notebook``) the frame stands where the notebook
    would show the figure's image, and holds the chart as the output area
    holds the image: it is as wide as the output area, up to the chart's own
    width -- that of the ``<svg>`` marked :data:`FRAME_SVG_CLASS` -- and the
    chart shrinks with it, keeping its shape, rather than the output area
    scrolling sideways. Its document has :func:`frame_style`. Its height is
    measured again whenever the frame's width or its content changes, and
    grows while maidr's help or settings dialog is open, so that the dialog
    fits. The notebook's scroll position is kept while the frame is
    measured. Elsewhere -- Shiny, Flask, a Pyodide page -- the frame is as
    wide as its content.

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

    Returns
    -------
    Tag
        An iframe tag wrapping the original HTML with auto-resizing logic.
    """
    unique_id = _generate_unique_id()
    fits = "true" if in_notebook else "false"
    helpers = _NOTEBOOK_JS + _WATCH_JS if in_notebook else ""
    # In a notebook the frame is measured again when the output area narrows
    # or widens -- a change of the frame's width only: its height is set as
    # it is measured, at none for a moment, which resizes its window too, and
    # measured it again on every frame for as long as the notebook was open
    # -- when maidr's text or fields come, go or change (``maidrWatch``), when
    # a dialog maidr opens or closes is added to or taken from the body, when
    # the focus moves, and once maidr.js has put the chart back in the
    # document, which it takes out as it starts: in a cell JupyterLab does not
    # draw while it is out of view, the frame's window reports no resize, and
    # the frame was left with no height until the reader scrolled to it.
    notebook_listeners = (
        _NOTEBOOK_LISTENERS_JS.replace("FRAME_SVG_CLASS", FRAME_SVG_CLASS)
        if in_notebook
        else ""
    )

    # The script runs as the frame's document loads, and again whenever it
    # is loaded again (a frame taken out of the page and put back), giving
    # each document its own listeners and observers. It replaced itself after
    # its first run, which left a document loaded again with only a resize
    # listener, and no height.
    resizing_script = f"""
        {helpers}
        function resizeIframe() {{
            let fitsOutput = {fits};
            let iframe = document.getElementById('{unique_id}');
            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            if (
                iframe && iframe.contentWindow &&
                iframe.contentWindow.document &&
                iframe.contentWindow.document.body
            ) {{
                let iframeDocument = iframe.contentWindow.document;
                let body = iframeDocument.body;
                let de = iframeDocument.documentElement;
                let restoreScroll = fitsOutput ? maidrKeepScroll(iframe) : null;
                let before = iframe.style.height;

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
                    // While maidr's help or settings dialog is open, the frame
                    // may be as wide as MUI makes a dialog (600px, and 32px
                    // either side), so that a small chart's frame does not
                    // squeeze it.
                    let dialogOpen = iframeDocument.querySelector('.MuiDialog-root');
                    iframe.style.width = maidrOutputWidth(iframe, false);
                    iframe.style.maxWidth = Math.max(own + side, dialogOpen ? 664 : 0) + 'px';
                }} else if (fitsOutput) {{
                    // Until maidr.js has put the chart back: narrowed to
                    // nothing, the frame had no width to measure it at.
                    iframe.style.width = maidrOutputWidth(iframe, false);
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
                if (fitsOutput) {{
                    height = Math.max(height, maidrDialogRoom(iframeDocument, window));
                }}
                iframe.style.height = (height) + 'px';
                if (restoreScroll) restoreScroll();
                if (fitsOutput) {{
                    maidrShowField(iframeDocument, iframe.style.height !== before);
                }}
            }}
        }}
        let iframe = document.getElementById('{unique_id}');
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

    srcdoc = str(base_html.get_html_string())
    if in_notebook:
        srcdoc = frame_style() + srcdoc
    return tags.iframe(
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
        style="background-color: #fff; position: relative; border: none",
        frameBorder=0,
        onload=resizing_script,
    )


def wrap_in_iframe_plotly(
    base_html: Tag,
    chart_title: str | None = None,
    alt: str | None = None,
    *,
    in_notebook: bool = False,
    keep_padding: bool = False,
    fill_width: bool = False,
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
    when the frame is measured. The frame grows while maidr's help or
    settings dialog is open, as the matplotlib one does.

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
        ``width`` of ``"container"``): in a notebook it is then as wide as
        the frame; see ``maidr/assets/frame.css``.

    Returns
    -------
    Tag
        An iframe tag wrapping the original HTML with auto-resizing logic.
    """
    unique_id = _generate_unique_id()
    fits = "true" if in_notebook else "false"
    keeps = "true" if keep_padding else "false"
    helpers = _WATCH_JS + (_NOTEBOOK_JS if in_notebook else "")

    resizing_script = f"""
        {helpers}
        function resizeIframe() {{
            var fitsOutput = {fits};
            var keepsPadding = {keeps};
            var iframe = document.getElementById('{unique_id}');
            if (!iframe || !iframe.contentWindow || !iframe.contentWindow.document) {{
                return;
            }}

            if (fitsOutput && maidrNotLaidOut(iframe)) return;
            var doc = iframe.contentWindow.document;
            var body = doc.body;
            if (!body) return;
            var de = doc.documentElement;
            var restoreScroll = fitsOutput ? maidrKeepScroll(iframe) : null;
            var before = iframe.style.height;

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
                if (de.scrollWidth > iframe.contentWindow.innerWidth + 1) {{
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
            if (fitsOutput) {{
                height = Math.max(height, maidrDialogRoom(doc, window));
            }}

            iframe.style.height = height + 'px';
            if (restoreScroll) restoreScroll();
            if (fitsOutput) {{
                maidrShowField(doc, iframe.style.height !== before);
            }}
        }}

        var iframe = document.getElementById('{unique_id}');
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

            if ({fits}) {{
                // A dialog maidr opens or closes is added to or taken from
                // the body.
                new MutationObserver(scheduleResize).observe(
                    iframe.contentWindow.document.body, {{ childList: true }}
                );
            }}

            // maidr's text and fields, which can lie past the body's box.
            maidrWatch(iframe.contentWindow.document, scheduleResize);

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

    if in_notebook and fill_width:
        base_html.add_class("maidr-frame-fill")
    srcdoc = str(base_html.get_html_string())
    if in_notebook:
        width_first = "" if keep_padding else _OUTPUT_WIDTH_FIRST
        srcdoc = frame_style() + width_first + srcdoc
    return tags.iframe(
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
        style="background-color: #fff; position: relative; border: none",
        frameBorder=0,
        onload=resizing_script,
    )
