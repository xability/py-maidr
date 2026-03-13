"""
Utility functions for wrapping HTML content in auto-resizing iframes.

These functions are used by both matplotlib and Plotly renderers to embed
plots in Jupyter notebooks, Google Colab, VSCode, Flask, and Shiny environments.
"""

import uuid

from htmltools import Tag, tags


def _generate_unique_id() -> str:
    """Generate a unique iframe ID."""
    return "iframe_" + str(uuid.uuid4())


def wrap_in_iframe_matplotlib(base_html: Tag) -> Tag:
    """Wrap matplotlib HTML in an auto-resizing iframe for notebooks.

    Parameters
    ----------
    base_html : Tag
        The HTML tag containing the matplotlib plot and MAIDR scripts.

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
                // Detect braille textarea by dynamic id prefix
                let brailleContainer = iframeDocument.querySelector('[id^="maidr-braille-textarea"]');
                // Detect review input container by class name
                let reviewInputContainer = iframeDocument.querySelector('.maidr-review-input');
                iframe.style.height = 'auto';
                let height = iframeDocument.body.scrollHeight;
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
                if (isBrailleActive) {{
                    height += 100;
                }} else if (isReviewInputActive) {{
                    height += 50;
                }} else {{
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
    """

    return tags.iframe(
        id=unique_id,
        srcdoc=str(base_html.get_html_string()),
        width="100%",
        height="100%",
        scrolling="no",
        style="background-color: #fff; position: relative; border: none",
        frameBorder=0,
        onload=resizing_script,
    )


def wrap_in_iframe_plotly(base_html: Tag) -> Tag:
    """Wrap Plotly HTML in an auto-resizing iframe for notebooks.

    Mirrors the focus-delegation logic from the matplotlib wrapper
    but adds Plotly-specific handling for overflow containers and
    MAIDR element scanning.

    Parameters
    ----------
    base_html : Tag
        The HTML tag containing the Plotly chart and MAIDR scripts.

    Returns
    -------
    Tag
        An iframe tag wrapping the original HTML with auto-resizing logic.
    """
    unique_id = _generate_unique_id()

    resizing_script = f"""
        function resizeIframe() {{
            var iframe = document.getElementById('{unique_id}');
            if (
                !iframe || !iframe.contentWindow ||
                !iframe.contentWindow.document
            ) return;

            var doc = iframe.contentWindow.document;
            var body = doc.body;
            var de = doc.documentElement;
            if (!body) return;

            // Start with standard DOM measurements.
            var height = Math.max(
                body.scrollHeight || 0,
                body.offsetHeight || 0,
                de.scrollHeight || 0,
                de.offsetHeight || 0,
                de.clientHeight || 0
            );

            // Plotly's .svg-container has overflow:visible, so
            // MAIDR text below the chart is NOT included in
            // scrollHeight (CSS spec).  Scan MAIDR elements to
            // find the lowest bottom edge.
            var selectors = [
                '#maidr-text-container',
                '[id^="react-container-"]',
                '[id^="maidr-braille-textarea"]',
                '[id^="maidr-review-input"]'
            ];
            for (var i = 0; i < selectors.length; i++) {{
                var el = doc.querySelector(selectors[i]);
                if (el) {{
                    var rect = el.getBoundingClientRect();
                    var bottom = rect.bottom +
                        (iframe.contentWindow.scrollY || 0);
                    if (bottom > height) {{
                        height = bottom;
                    }}
                }}
            }}

            // Buffer for braille/review active states.
            var braille = doc.querySelector(
                '[id^="maidr-braille-textarea"]'
            );
            var review = doc.querySelector(
                '[id^="maidr-review-input"]'
            );
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
            }} else {{
                height += 50;
            }}

            iframe.style.height = height + 'px';
        }}

        var iframe = document.getElementById('{unique_id}');
        resizeIframe();
        iframe.onload = function() {{
            resizeIframe();
            iframe.contentWindow.addEventListener(
                'resize', resizeIframe
            );

            // MutationObserver: detect react-container appearing
            // on first focus and other DOM changes.
            try {{
                var _raf = 0;
                new MutationObserver(function() {{
                    cancelAnimationFrame(_raf);
                    _raf = requestAnimationFrame(function() {{
                        resizeIframe();
                    }});
                }}).observe(
                    iframe.contentWindow.document.body,
                    {{ childList: true, subtree: true, attributes: true }}
                );
            }} catch (_) {{}}

            // Focus events for braille/review buffer changes.
            try {{
                iframe.contentWindow.document.addEventListener(
                    'focusin', function() {{ resizeIframe(); }}, true
                );
                iframe.contentWindow.document.addEventListener(
                    'focusout', function() {{ resizeIframe(); }}, true
                );
            }} catch (_) {{}}
        }};
    """

    return tags.iframe(
        id=unique_id,
        srcdoc=str(base_html.get_html_string()),
        width="100%",
        height="100%",
        scrolling="no",
        style="background-color: #fff; position: relative; border: none",
        frameBorder=0,
        onload=resizing_script,
    )
