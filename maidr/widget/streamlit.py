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
incidental.  Streamlit binds ``r`` at the document level -- it reruns the
script -- exempting only form fields, and maidr binds ``r`` for review
mode.  Two listeners on one document cannot both win, and
``preventDefault`` in one does not stop the other.  The iframe is what
keeps maidr's keyboard interface intact, so an embedding that renders the
chart directly into the Streamlit page would take that key away from it.

Measured rather than inferred, on Streamlit 1.61.1 in Chromium.  From the
page, ``r`` reruns the script; from inside the frame, the same keystroke
reaches maidr (``Review is on``) and the script does not rerun.  One
document-level collision is enough to make the frame load-bearing, which
is why this note now claims only the key that was measured: an earlier
version of it also named ``c`` and ``esc``, neither of which produced an
observable rerun.  That is not proof they are unbound -- they may drive
something else that collides just as badly -- but it was more than the
evidence supported.
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
        Internal. Frames to skip when warning, so a warning points at the
        caller's own line; :func:`render_maidr` raises it by one because it
        sits a frame further out. Not part of the public API -- the
        underscore is the only thing stopping an IDE from offering it.

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
    # Resolved once and then passed on, rather than read again inside
    # ``render``.  ``set_use_cdn`` writes process-wide state and Streamlit
    # runs sessions on separate threads, so reading it twice leaves a window
    # in which this function decides whether to inline against one answer
    # while the chart was built from another.
    resolved = maidr.get_use_cdn() if use_cdn is None else use_cdn
    rendered = maidr.render(plot, use_cdn=resolved)
    html = str(rendered.get_html_string())

    if resolved is False:
        if _references_maidr_runtime(html):
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
                # One less than ``_warn_if_no_runtime`` gets: this warns from
                # inside this function, while that one warns from inside its
                # own, a frame deeper.  Sharing the number would point this
                # warning one frame past the caller.
                stacklevel=stacklevel - 1,
            )
        else:
            inline_tags = inline_bundle_tags()
            if inline_tags is not None:
                # Ahead of the rendered tag, so ``maidr.js`` is defined by
                # the time the bootstrap inside it calls ``window.main()``.
                html = str(tags.div(*inline_tags, rendered).get_html_string())

    _warn_if_no_runtime(html, resolved, stacklevel=stacklevel)
    return html


#: Matches a quoted URL naming the ``maidr`` npm package and a ``.js`` file.
#:
#: Deliberately matches a *URL* rather than a ``<script src=...>`` tag,
#: because maidr arrives in two shapes: the Altair adapter emits a literal
#: tag, while the matplotlib and Plotly paths build the element in
#: JavaScript (``s.src = '...'``), where no such tag exists in the markup.
#: Matching the tag alone reports "no runtime" for the two commonest
#: renderers.
#: The ``/`` is load-bearing: without it, any quoted string merely ending in
#: ``...maidr@1.js`` would match -- ``notmaidr@1.js`` among them. Every URL
#: this needs to recognise carries the npm path segment ``/maidr@``.
_MAIDR_RUNTIME_URL = re.compile(r"[\"'][^\"']*/maidr@[^\"']*\.js", re.I)


def _references_maidr_runtime(html: str) -> bool:
    """Report whether the HTML fetches a maidr runtime over the network.

    Names the ``maidr`` package specifically.  Asking only whether *some*
    ``<script>`` and *some* ``src=`` appear would be answered "yes" by any
    Plotly chart, which always carries a ``cdn.plot.ly`` tag of its own --
    vouching for a maidr runtime on the strength of an unrelated one.

    Parameters
    ----------
    html : str
        The serialised chart.

    Returns
    -------
    bool
        True if a maidr runtime URL appears in the document.
    """
    return bool(_MAIDR_RUNTIME_URL.search(html))


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
    if _references_maidr_runtime(html):
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
        Pass ``False`` for an air-gapped deployment.  Prefer this argument
        over :func:`maidr.set_use_cdn`: the setter writes process-wide
        state, and Streamlit runs sessions on separate threads, so one
        session calling it changes what every other session renders.

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
    except ImportError as error:
        from maidr.widget._extras import missing_extra_error

        raise missing_extra_error(error, "streamlit", "streamlit") from error

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
