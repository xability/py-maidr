"""A copy of ``maidr.js`` the host serves, for the frame being rendered (#457).

An iframed render outside a notebook carries the bundle inline: its
document is serialized with ``Tag.get_html_string()``, which drops the
``HTMLDependency`` that would have placed a ``<script src>``, and no host
served the files for a ``src`` to name. So with ``use_cdn=False`` every
chart document was ~2.2 MB of runtime around a chart of tens of KB, and
under ``use_cdn="auto"`` the offline fallback named a relative
``lib/maidr-<version>/`` path that nothing answered.

A host whose frame documents are fetched from its own origin can do
better, and Shiny's are: :class:`maidr.widget.shiny.render_maidr` serves
each chart from a session route (#534). It registers the bundled files
with the app once, as an ordinary web dependency, and renders inside
:func:`serving_bundle` so that the document names that copy by URL instead
of carrying it. The browser then fetches ``maidr.js`` once per app and
version and keeps it, rather than once per chart per render.

What the renderers ask here is only "does the frame I am building have a
served copy, and where?" -- :func:`served_bundle_url`. Everything else
about the iframe decision stays where it was, so a render that nobody
wraps in :func:`serving_bundle` -- Flask, Streamlit, a notebook,
``save_html`` -- emits exactly what it did before.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional

from maidr.util.dependencies import (
    MAIDR_JS_FILENAME,
    _STATIC_PACKAGE,
    _STATIC_SUBDIR,
    inline_bundle_tags,
    maidr_js_version,
)

#: Name of the dependency a host registers to serve the bundled files.
#:
#: Not ``"maidr"``, the name :func:`maidr.util.dependencies.maidr_html_dependency`
#: uses. Shiny's client records a dependency by name once it has placed it
#: and skips any later one of that name, so a script-less dependency called
#: ``"maidr"`` arriving first would stop a page that also carries the real
#: one from ever loading its ``<script>``. A name of its own collides with
#: nothing.
SERVED_BUNDLE_NAME = "maidr-bundle"


class ServedBundle:
    """Where a frame's document can load the bundled copy, and whether it did.

    Parameters
    ----------
    directory : str
        The served directory, as the frame's document must spell it: a
        URL relative to that document, or an absolute one. A trailing
        slash is ignored.

    Attributes
    ----------
    directory : str
        The directory, without a trailing slash.
    referenced : bool
        Whether a render named the served copy, through :meth:`url`. The
        host serves the files only then, so a chart that loads from the
        CDN -- ``use_cdn=True``, or an Altair chart -- registers nothing.
    """

    __slots__ = ("directory", "referenced")

    def __init__(self, directory: str) -> None:
        self.directory = directory.rstrip("/")
        self.referenced = False

    def url(self, filename: str = MAIDR_JS_FILENAME) -> str:
        """Return the URL of one served file, and record that it was named.

        Parameters
        ----------
        filename : str, default "maidr.js"
            A file in ``maidr/static/``.

        Returns
        -------
        str
            ``directory/filename``.
        """
        self.referenced = True
        return f"{self.directory}/{filename}"


#: The served copy for the render in progress, or ``None`` when the frame
#: has to carry its own. A context variable rather than an argument because
#: the answer belongs to the host, and the question is asked three calls
#: below the one public entry point every host goes through,
#: :func:`maidr.render` -- the same way :meth:`Environment.is_shiny` asks
#: Shiny's own context variable whether a session is live. It also follows
#: the render onto its worker thread: ``asyncio.to_thread`` runs the
#: function in a copy of the caller's context.
_served_bundle: ContextVar[Optional[ServedBundle]] = ContextVar(
    "maidr_served_bundle", default=None
)


@contextmanager
def serving_bundle(bundle: Optional[ServedBundle]) -> Iterator[None]:
    """Render with ``bundle`` as the frame's source of ``maidr.js``.

    Parameters
    ----------
    bundle : ServedBundle or None
        The served copy; ``None`` renders as if there were none, which is
        how a host says it could not serve one this time.

    Yields
    ------
    None
        Control, for the duration of the render.
    """
    token = _served_bundle.set(bundle)
    try:
        yield
    finally:
        _served_bundle.reset(token)


def served_bundle_url(filename: str = MAIDR_JS_FILENAME) -> Optional[str]:
    """Return where the frame being rendered can load a bundled file.

    Asked only on the paths that build a frame outside a notebook -- the
    ones that would otherwise inline the bundle, or fall back to a
    relative ``lib/`` path under ``use_cdn="auto"``.

    Parameters
    ----------
    filename : str, default "maidr.js"
        A file in ``maidr/static/``.

    Returns
    -------
    str or None
        The URL, or ``None`` when no host is serving the bundle for this
        render.
    """
    bundle = _served_bundle.get()
    return None if bundle is None else bundle.url(filename)


def frame_bundle_tags() -> Optional[list[Any]]:
    """Return what a frame outside a notebook carries to load ``maidr.js``.

    A ``<script src>`` naming the served copy when the host serves one.
    Loaded by URL, ``maidr.js`` also finds ``maidr-math.css`` beside itself
    on demand, so neither the maths stylesheet nor the marker that
    :func:`maidr.util.dependencies.inline_bundle_tags` adds for an inline
    script is needed. Otherwise the inline tags, as before.

    Returns
    -------
    list of htmltools.Tag, or None
        The tags, in document order; ``None`` when the bundle has to travel
        inline and cannot be read, leaving the caller its CDN fallback.
    """
    url = served_bundle_url()
    if url is None:
        return inline_bundle_tags()
    from htmltools import tags

    return [tags.script(src=url, type="text/javascript")]


def served_bundle_dependency() -> Any:
    """Return the dependency a host registers to serve the bundled files.

    Every file under ``maidr/static/`` (``all_files=True``), so the
    runtime finds ``maidr-math.css`` beside itself, and no ``<script>`` or
    ``<link>``: placed on a page, it serves the files and loads nothing
    into that page. The frames load ``maidr.js`` themselves, by the URL
    :class:`ServedBundle` gives them.

    Versioned by the bundled ``maidr.js``, which is what puts the version
    in the URL -- ``lib/maidr-bundle-<version>/`` under Shiny -- so a
    browser that has the file keeps it until the bundle changes.

    Returns
    -------
    htmltools.HTMLDependency
        The dependency.
    """
    from htmltools import HTMLDependency

    return HTMLDependency(
        name=SERVED_BUNDLE_NAME,
        version=maidr_js_version(),
        source={"package": _STATIC_PACKAGE, "subdir": _STATIC_SUBDIR},
        script=[],
        stylesheet=[],
        all_files=True,
    )
