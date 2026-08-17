"""Streamlit integration for MAIDR.

Provides :func:`render_maidr`, which draws an accessible chart into a
Streamlit app, and :func:`maidr_html`, which returns the same chart as a
self-contained HTML string for callers that want to cache or place it
themselves.

Requires the optional ``streamlit`` extra::

    pip install "maidr[streamlit]"

Notes
-----
The chart is embedded in an iframe, and that is deliberate rather than
incidental.  Streamlit's own app binds ``r``, ``c`` and ``esc`` at the
document level, exempting only form fields, and maidr binds all three for
replay, braille and dismissing panels.  Two listeners on one document
cannot both win, and ``preventDefault`` in one does not stop the other.
The iframe is what keeps maidr's keyboard interface intact, so an
embedding that renders the chart directly into the Streamlit page would
take those keys away from it.
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Any, Literal, Optional, Union

from htmltools import tags

import maidr
from maidr.util.dependencies import inline_bundle_tags, read_bundled_js

#: Accepted by ``use_cdn``; ``None`` defers to :func:`maidr.get_use_cdn`.
UseCdn = Optional[Union[bool, Literal["auto"]]]

#: Sizes accepted by :func:`render_maidr`, mirroring ``st.iframe``.
Size = Union[int, Literal["content", "stretch"]]

#: Height used when falling back to ``components.v1.html``, which cannot
#: size itself.  Its own default is ``None``, which Streamlit renders as
#: 150 px -- tall enough to look deliberate and short enough to crop every
#: real chart, which is the most common way a Streamlit embed goes wrong.
_LEGACY_FALLBACK_HEIGHT = 600


def maidr_html(plot: Any = None, *, use_cdn: UseCdn = None) -> str:
    """
    Return an accessible chart as a self-contained HTML string.

    Parameters
    ----------
    plot : Any, optional
        The plot to render -- a matplotlib or seaborn artist, a Plotly
        ``Figure``, or an Altair chart.  ``None`` uses the current
        matplotlib figure.
    use_cdn : bool, {"auto"}, or None, default None
        Where the chart loads ``maidr.js`` from; see :func:`maidr.render`.
        ``None`` defers to the process-wide default.

    Returns
    -------
    str
        A complete HTML fragment, safe to embed in an iframe.

    Notes
    -----
    Exists as its own entry point so the *string* can be cached::

        @st.cache_data
        def chart_html(_fig):
            return maidr_html(_fig)

    Caching that is the useful lever, because Streamlit reruns the whole
    script on every widget interaction.  Note the underscore: it tells
    Streamlit not to hash the argument, which a matplotlib ``Figure`` does
    not support.

    Under ``use_cdn=False`` the ~1.9 MB bundle is embedded in the string.
    Serialising to HTML is what makes an embed possible at all, and it
    drops :class:`htmltools.HTMLDependency` children on the way, so a
    reference to the bundle would not survive; the source itself has to.
    """
    resolved = maidr.get_use_cdn() if use_cdn is None else use_cdn
    rendered = maidr.render(plot, use_cdn=use_cdn)

    if resolved is False:
        inline_tags = inline_bundle_tags()
        if inline_tags is not None:
            # Ahead of the rendered tag, so ``maidr.js`` is defined by the
            # time the bootstrap inside it calls ``window.main()``.
            rendered = tags.div(*inline_tags, rendered)

    html = str(rendered.get_html_string())
    _warn_if_no_runtime(html, resolved)
    return html


@lru_cache(maxsize=1)
def _bundle_marker() -> str:
    """Return a slice of the bundled ``maidr.js``, for recognising it inline.

    Asking whether the bundle is in the string by looking for the bundle
    beats asking whether the string is large, which a big enough chart can
    satisfy on its own.  Returns ``""`` -- which is in every string, so the
    caller treats the runtime as present -- if the bundle cannot be read,
    since a broken install has already warned by then and a second warning
    saying something untrue would not help.
    """
    try:
        return read_bundled_js()[:200]
    except (OSError, ValueError):
        return ""


def _warn_if_no_runtime(html: str, use_cdn: Any) -> None:
    """Warn when the emitted HTML has no way to load ``maidr.js``.

    A chart with no runtime behind it still *looks* right -- it is the SVG,
    unchanged -- while being silently unusable: no sonification, no
    braille, no keyboard navigation.  That failure is invisible to a
    sighted developer testing their own app, which is precisely why it is
    worth an explicit check rather than trusting the branches above.
    """
    if "<script" in html and ("src=" in html or "cdn.jsdelivr" in html):
        return
    if _bundle_marker() in html:
        return
    warnings.warn(
        "maidr: the rendered chart carries no source for maidr.js, so it "
        "will display as a static image with no sonification, braille or "
        f"keyboard navigation (use_cdn={use_cdn!r}). This is a bug in "
        "py-maidr; please report it.",
        UserWarning,
        stacklevel=3,
    )


def render_maidr(
    plot: Any = None,
    *,
    height: Size = "content",
    width: Size = "stretch",
    tab_index: Optional[int] = 0,
    use_cdn: UseCdn = None,
) -> None:
    """
    Draw an accessible MAIDR chart in a Streamlit app.

    Parameters
    ----------
    plot : Any, optional
        The plot to render -- a matplotlib or seaborn artist, a Plotly
        ``Figure``, or an Altair chart.  ``None`` uses the current
        matplotlib figure.
    height : int, {"content", "stretch"}, default "content"
        Height of the embed.  ``"content"`` lets Streamlit measure the
        chart, which is what keeps maidr's braille and text panels visible
        when they open.
    width : int, {"content", "stretch"}, default "stretch"
        Width of the embed.
    tab_index : int or None, default 0
        Keyboard tab order for the embed.  ``0`` places it in document
        order, so a keyboard user reaches the chart by tabbing rather than
        having to click it first.  This is why it is not ``None``: the
        browser default leaves the frame unreachable from the keyboard,
        which for this library is the whole interface.
    use_cdn : bool, {"auto"}, or None, default None
        Where the chart loads ``maidr.js`` from; see :func:`maidr.render`.
        Pass ``False`` for an air-gapped deployment.

    Returns
    -------
    None
        Nothing is returned.  The embed sends no data back, and handing
        back a Streamlit object would suggest an interactivity this does
        not have.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> from maidr.widget.streamlit import render_maidr
    >>>
    >>> fig, ax = plt.subplots()
    >>> ax.bar(["a", "b"], [1, 2])
    >>> render_maidr(ax)
    """
    try:
        import streamlit as st
    except ImportError as error:  # pragma: no cover - needs streamlit absent
        raise ImportError(
            "maidr's Streamlit integration requires the `streamlit` "
            'package. Install it with: pip install "maidr[streamlit]"'
        ) from error

    html = maidr_html(plot, use_cdn=use_cdn)

    if hasattr(st, "iframe"):
        st.iframe(html, width=width, height=height, tab_index=tab_index)
        return

    # Streamlit older than the one that introduced ``st.iframe``.
    # ``components.v1.html`` cannot size itself, and its own default
    # (``None``) renders as 150 px, so a symbolic size has to become a
    # concrete one here rather than silently cropping the chart.
    import streamlit.components.v1 as components

    components.html(
        html,
        width=width if isinstance(width, int) else None,
        height=height if isinstance(height, int) else _LEGACY_FALLBACK_HEIGHT,
        scrolling=True,
    )


__all__ = ["maidr_html", "render_maidr"]
