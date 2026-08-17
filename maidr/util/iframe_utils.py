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


def _generate_unique_id() -> str:
    """Generate a unique iframe ID."""
    return "iframe_" + str(uuid.uuid4())


def iframe_title(chart_title: str | None = None) -> str:
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

    Parameters
    ----------
    chart_title : str, optional
        The chart's title. Whitespace-only counts as absent, matching the
        MAIDR engine's trimmed "authored" check.

    Returns
    -------
    str
        The accessible name for the ``iframe``.
    """
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


def wrap_in_iframe_matplotlib(base_html: Tag, chart_title: str | None = None) -> Tag:
    """Wrap matplotlib HTML in an auto-resizing iframe for notebooks.

    Parameters
    ----------
    base_html : Tag
        The HTML tag containing the matplotlib plot and MAIDR scripts.
    chart_title : str, optional
        The chart's own title, which leads the frame's accessible name. See
        :func:`iframe_title`.

    Returns
    -------
    Tag
        An iframe tag wrapping the original HTML with auto-resizing logic.
    """
    unique_id = _generate_unique_id()

    resizing_script = f"""
        function resizeIframe() {{
            let iframe = document.getElementById('{unique_id}');
            if (
                iframe && iframe.contentWindow &&
                iframe.contentWindow.document
            ) {{
                let iframeDocument = iframe.contentWindow.document;
                let body = iframeDocument.body;
                let de = iframeDocument.documentElement;

                iframe.style.height = 'auto';

                // Use Math.max() across multiple DOM measurements (industry standard)
                let height = Math.max(
                    body.scrollHeight || 0,
                    body.offsetHeight || 0,
                    de.scrollHeight || 0,
                    de.offsetHeight || 0,
                    de.clientHeight || 0
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
                iframe.style.height = (height) + 'px';
                iframe.style.width = iframeDocument.body.scrollWidth + 'px';
            }}
        }}
        let iframe = document.getElementById('{unique_id}');
        resizeIframe();
        iframe.onload = function() {{
            resizeIframe();
            iframe.contentWindow.addEventListener('resize', resizeIframe);
        }};
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

    return tags.iframe(
        id=unique_id,
        title=iframe_title(chart_title),
        srcdoc=str(base_html.get_html_string()),
        width="100%",
        height="100%",
        scrolling="no",
        style="background-color: #fff; position: relative; border: none",
        frameBorder=0,
        onload=resizing_script,
    )


def wrap_in_iframe_plotly(base_html: Tag, chart_title: str | None = None) -> Tag:
    """Wrap Plotly HTML in an auto-resizing iframe for notebooks.

    Mirrors the focus-delegation logic from the matplotlib wrapper
    but adds Plotly-specific handling for overflow containers and
    MAIDR element scanning.

    Parameters
    ----------
    base_html : Tag
        The HTML tag containing the Plotly chart and MAIDR scripts.
    chart_title : str, optional
        The chart's own title, which leads the frame's accessible name. See
        :func:`iframe_title`.

    Returns
    -------
    Tag
        An iframe tag wrapping the original HTML with auto-resizing logic.
    """
    unique_id = _generate_unique_id()

    resizing_script = f"""
        function resizeIframe() {{
            var iframe = document.getElementById('{unique_id}');
            if (!iframe || !iframe.contentWindow || !iframe.contentWindow.document) {{
                return;
            }}

            var doc = iframe.contentWindow.document;
            var body = doc.body;
            if (!body) return;

            // CRITICAL: Shrink iframe first to get accurate content measurement.
            // Without this, body.scrollHeight reflects the current iframe size,
            // not the natural content size (causes whitespace after braille closes).
            iframe.style.height = 'auto';

            // HEIGHT: Measure content after shrinking
            var height = Math.max(
                body.scrollHeight || 0,
                body.offsetHeight || 0
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

            iframe.style.height = height + 'px';
        }}

        var iframe = document.getElementById('{unique_id}');
        resizeIframe();

        // Setup resize listener on contentWindow
        try {{
            iframe.contentWindow.addEventListener('resize', resizeIframe);
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

    return tags.iframe(
        id=unique_id,
        title=iframe_title(chart_title),
        srcdoc=str(base_html.get_html_string()),
        width="100%",
        height="100%",
        scrolling="no",
        style="background-color: #fff; position: relative; border: none",
        frameBorder=0,
        onload=resizing_script,
    )
