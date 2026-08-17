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

import re
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


def maidr_html(
    plot: Any = None, *, use_cdn: UseCdn = None, _stacklevel: int = 3
) -> str:
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
    _stacklevel : int, default 3
        Frames to skip when warning, so the warning points at the caller.
        Raised by one when :func:`render_maidr` calls through.

    Returns
    -------
    str
        A complete HTML fragment, safe to embed in an iframe.

    Notes
    -----
    Exists as its own entry point so the *string* can be cached, which is
    the useful lever against Streamlit rerunning the whole script on every
    widget interaction::

        @st.cache_data
        def chart_html(_fig, key):
            return maidr_html(_fig)

        html = chart_html(fig, key=selected_day)

    Both arguments are load-bearing.  The underscore on ``_fig`` tells
    Streamlit not to hash it, which a matplotlib ``Figure`` does not
    support -- and ``key`` is then the only thing left to hash.  Without
    it every argument is skipped, the cache key is constant, and the first
    chart is returned for the rest of the session: a chart that silently
    stops matching its own controls.

    Under ``use_cdn=False`` the ~1.9 MB bundle is embedded in the string.
    Serialising to HTML is what makes an embed possible at all, and it
    drops :class:`htmltools.HTMLDependency` children on the way, so a
    reference to the bundle would not survive; the source itself has to.
    """
    stacklevel = _stacklevel
    resolved = maidr.get_use_cdn() if use_cdn is None else use_cdn
    rendered = maidr.render(plot, use_cdn=use_cdn)
    html = str(rendered.get_html_string())

    if resolved is False:
        if _loads_maidr_remotely(html):
            # Altair charts are the case: :func:`maidr.render` hands them to
            # the Vega-Lite adapter before ``use_cdn`` is consulted, so the
            # chart already names a remote runtime and inlining the bundle
            # would add ~1.9 MB the page never loads -- while still needing
            # the network.  Say so rather than doing it.
            warnings.warn(
                "maidr: use_cdn=False cannot be honoured for this chart; it "
                "loads maidr.js from the CDN regardless, so the embed still "
                "requires network access.",
                UserWarning,
                stacklevel=stacklevel,
            )
        else:
            inline_tags = inline_bundle_tags()
            if inline_tags is not None:
                # Ahead of the rendered tag, so ``maidr.js`` is defined by
                # the time the bootstrap inside it calls ``window.main()``.
                html = str(tags.div(*inline_tags, rendered).get_html_string())

    _warn_if_no_runtime(html, resolved, stacklevel=stacklevel)
    return html


#: Matches a ``<script src=...>`` naming a maidr runtime -- what the Altair
#: adapter emits, and what says "this chart already has a source".
_REMOTE_MAIDR_SCRIPT = re.compile(r"<script[^>]*\bsrc=[\"'][^\"']*maidr[^\"']*", re.I)


def _loads_maidr_remotely(html: str) -> bool:
    """Report whether the HTML already fetches a maidr runtime over the network."""
    return bool(_REMOTE_MAIDR_SCRIPT.search(html))


@lru_cache(maxsize=1)
def _bundle_marker() -> Optional[str]:
    """Return a slice of the bundled ``maidr.js``, for recognising it inline.

    Asking whether the bundle is in the string by looking for the bundle
    beats asking whether the string is large, which a big enough chart can
    satisfy on its own.

    Returns ``None`` when the bundle cannot be read at all -- meaning "no
    answer", so the caller falls back to its other checks rather than
    treating absence as presence.  An *empty* bundle deliberately yields a
    sentinel that cannot occur in real HTML: returning ``""`` there would
    match every string and silently vouch for a chart that has no runtime,
    which is the one thing this check exists to catch.
    """
    try:
        source = read_bundled_js()
    except (OSError, ValueError):
        return None
    return source[:200] or "\x00maidr-bundle-is-empty\x00"


def _warn_if_no_runtime(html: str, use_cdn: Any, stacklevel: int = 3) -> None:
    """Warn when the emitted HTML has no way to load ``maidr.js``.

    A chart with no runtime behind it still *looks* right -- it is the SVG,
    unchanged -- while being silently unusable: no sonification, no
    braille, no keyboard navigation.  That failure is invisible to a
    sighted developer testing their own app, which is precisely why it is
    worth an explicit check rather than trusting the branches above.

    Parameters
    ----------
    html : str
        The serialised chart.
    use_cdn : Any
        The resolved mode, quoted back in the message.
    stacklevel : int, default 3
        Frames to skip so the warning points at the user's own call rather
        than at a line inside this module.
    """
    if "<script" in html and ("src=" in html or "cdn.jsdelivr" in html):
        return
    marker = _bundle_marker()
    if marker is not None and marker in html:
        return
    warnings.warn(
        "maidr: the rendered chart carries no source for maidr.js, so it "
        "will display as a static image with no sonification, braille or "
        f"keyboard navigation (use_cdn={use_cdn!r}). This is a bug in "
        "py-maidr; please report it.",
        UserWarning,
        stacklevel=stacklevel,
    )


def render_maidr(
    plot: Any = None,
    *,
    height: Size = "content",
    width: Size = "stretch",
    tab_index: Optional[int] = None,
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
    tab_index : int or None, default None
        Tab order of the *frame*, passed through to Streamlit.  ``None``
        is the browser default and is deliberate: an iframe's contents
        already take part in sequential focus navigation, and maidr gives
        the chart inside its own tab stop, so a keyboard user tabs
        straight onto the chart.  Passing ``0`` makes the frame itself a
        stop as well, which is one extra Tab before the chart -- and
        Streamlit hardcodes the frame's accessible name as ``st.iframe``,
        so that stop announces the same on every chart on the page.  It is
        exposed for layouts that want a deterministic landing point, not
        because the chart needs it to be reachable.
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

    html = maidr_html(plot, use_cdn=use_cdn, _stacklevel=4)

    if hasattr(st, "iframe"):
        st.iframe(html, width=width, height=height, tab_index=tab_index)
        return

    # Streamlit older than the one that introduced ``st.iframe``.
    # ``components.v1.html`` cannot size itself, and its own default
    # (``None``) renders as 150 px, so a symbolic size has to become a
    # concrete one here rather than silently cropping the chart.
    import streamlit.components.v1 as components

    kwargs = {
        "width": width if isinstance(width, int) else None,
        "height": height if isinstance(height, int) else _LEGACY_FALLBACK_HEIGHT,
        "scrolling": True,
    }
    # ``tab_index`` reached ``components.v1.html`` in Streamlit 1.45, eleven
    # releases before ``st.iframe`` existed, so "no st.iframe" does not mean
    # "no tab_index" -- taking it to mean that would discard a value the
    # caller passed, on every version in between, with nothing said.
    if _accepts_tab_index(components.html):
        kwargs["tab_index"] = tab_index
    elif tab_index is not None:
        warnings.warn(
            "maidr: this Streamlit is too old to set tab_index on an embed; "
            "the argument was ignored. Upgrade Streamlit to use it.",
            UserWarning,
            stacklevel=2,
        )

    components.html(html, **kwargs)


def _accepts_tab_index(fn: Any) -> bool:
    """Report whether a Streamlit embed function takes ``tab_index``.

    Asked of the installed function rather than inferred from a version,
    so the answer stays right across the range the extra allows.
    """
    import inspect

    try:
        return "tab_index" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


__all__ = ["maidr_html", "render_maidr"]
