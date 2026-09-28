"""Where the bundled ``maidr.js`` finds the languages it does not carry.

Since 4.8.0 ``maidr.js`` speaks English on its own and every other language
from a locale pack, ``locale-<code>.js``, which it fetches when a reader's
language is chosen or detected. It looks for the pack beside the URL it was
loaded from, unless the page names another directory as
``window.maidrLocaleBaseUrl`` -- in which case that wins.

The copy bundled in this package ships without the packs, so a document
that runs it -- from ``lib/``, or inlined into a frame where it has no URL
at all -- has nowhere to find them and stays English. Such a document
declares, in the window the bundle runs in and ahead of it, the directory
holding the packs of the bundled version on jsDelivr::

    window.maidrLocaleBaseUrl = window.maidrLocaleBaseUrl || "https://.../dist/";

English still needs nothing from the network; another language is fetched
when the reader is online, and stays English, as before, when they are
not. ``||`` keeps a directory the page already named. A document that loads
``maidr.js`` from the CDN declares nothing, because the packs sit beside
that copy -- and because the global wins, declaring the bundled version's
packs there would hand a newer CDN copy an older version's packs. So under
``use_cdn="auto"`` the declaration is made in the ``onerror`` fallback,
only once the bundled copy is what will run.

:func:`set_locale_base_url` and ``MAIDR_LOCALE_BASE_URL`` name another
directory, which is then declared in every document, or turn the
declaration off. Mirrors ``R/locale_config.R`` in r-maidr.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal, Optional, Union

from maidr.util import dependencies as _deps

#: Environment variable naming the directory, or empty to declare nothing.
LOCALE_BASE_URL_ENV_VAR = "MAIDR_LOCALE_BASE_URL"

#: Where the packs of a published version live.
_PACK_DIR_TEMPLATE = "https://cdn.jsdelivr.net/npm/maidr@{version}/dist/"

#: The global ``maidr.js`` reads.
_GLOBAL = "window.maidrLocaleBaseUrl"

#: Spellings of "off" accepted from the environment, besides the empty string.
_OFF_WORDS = frozenset({"false", "0", "no", "off"})

#: Set by :func:`set_locale_base_url`: a URL, ``""`` for off, or ``None``
#: to defer to the environment and then to the default.
_locale_base_url: Optional[str] = None


def set_locale_base_url(value: Union[str, Literal[False], None]) -> None:
    """Set where documents running the bundled ``maidr.js`` find locale packs.

    Parameters
    ----------
    value : str, False, or None
        * A URL: the directory holding ``locale-<code>.js``. It is declared
          in every document py-maidr produces, including those that load
          ``maidr.js`` from the CDN, so a self-hosted copy of the packs
          serves them all.
        * ``""`` or ``False``: declare nothing. A document running the
          bundled copy then makes no request for a language and stays in
          English.
        * ``None`` (default state): defer to ``MAIDR_LOCALE_BASE_URL``, and
          then to the packs of the bundled version on jsDelivr.

    Raises
    ------
    TypeError
        If ``value`` is none of the above.

    Notes
    -----
    Process-wide state, like :func:`maidr.set_use_cdn`: in a server
    handling several sessions, set it once at startup.
    """
    global _locale_base_url
    if value is False:
        _locale_base_url = ""
    elif value is None or isinstance(value, str):
        _locale_base_url = None if value is None else value.strip()
    else:
        raise TypeError(
            "set_locale_base_url() takes a URL string, '' or False to declare "
            f"nothing, or None to reset; got {value!r}"
        )


def _configured() -> Optional[str]:
    """The explicit setting: a URL, ``""`` for off, or ``None`` when unset.

    The setter wins; otherwise ``MAIDR_LOCALE_BASE_URL`` is read on every
    call, so a variable set after ``import maidr`` is seen.
    """
    if _locale_base_url is not None:
        return _locale_base_url
    raw = os.environ.get(LOCALE_BASE_URL_ENV_VAR)
    if raw is None:
        return None
    text = raw.strip()
    return "" if text.lower() in _OFF_WORDS else text


def _bundled_pack_dir() -> Optional[str]:
    """The jsDelivr directory of the bundled version's packs, if known."""
    version = _deps.maidr_js_version()
    if not _deps._is_valid_version(version) or version == _deps._UNKNOWN_VERSION:
        return None
    return _PACK_DIR_TEMPLATE.format(version=version)


def locale_base_url(*, bundled: bool) -> Optional[str]:
    """The directory a document should declare, or ``None`` for nothing.

    Parameters
    ----------
    bundled : bool
        Whether the declaration is for a window running the bundled copy.

    Returns
    -------
    str or None
        An explicitly configured URL whatever ``bundled`` is; otherwise the
        bundled version's packs on jsDelivr when ``bundled``; ``None`` when
        the declaration is turned off, or the window loads ``maidr.js`` from
        the CDN and nothing was configured.
    """
    configured = _configured()
    if configured is not None:
        return configured or None
    return _bundled_pack_dir() if bundled else None


def get_locale_base_url() -> Optional[str]:
    """Return where a document running the bundled ``maidr.js`` finds packs.

    Returns
    -------
    str or None
        The directory declared as ``window.maidrLocaleBaseUrl`` in such a
        document, or ``None`` when nothing is declared and it stays in
        English.
    """
    return locale_base_url(bundled=True)


def locale_config_js(url: Optional[str]) -> str:
    """The JS statement declaring ``url``, or ``""`` when it is ``None``.

    ``url`` is JSON-encoded, and every ``<`` in it escaped as ``\\u003c``,
    so no value can close the ``<script>`` it is written into or open a
    comment there.

    Parameters
    ----------
    url : str or None
        As returned by :func:`locale_base_url`.

    Returns
    -------
    str
        One assignment that keeps a directory the page already named.
    """
    if url is None:
        return ""
    literal = json.dumps(url).replace("<", "\\u003c")
    return f"{_GLOBAL} = {_GLOBAL} || {literal};"


def locale_fallback_js() -> str:
    """The declaration for a ``use_cdn="auto"`` fallback, run in its ``onerror``.

    Returns
    -------
    str
        The statement from :func:`locale_config_js` for the bundled copy,
        or ``""`` when it is turned off.
    """
    return locale_config_js(locale_base_url(bundled=True))


def locale_config_child(use_cdn: Union[bool, Literal["auto"]], *, inline: bool) -> Any:
    """The declaration a document or frame carries ahead of ``maidr.js``.

    Under ``use_cdn=False`` the bundled copy is what runs, so the default
    directory is declared. Under ``True`` and ``"auto"`` only an explicitly
    configured one is: ``"auto"`` declares the default in its fallback
    instead (:func:`locale_fallback_js`).

    Parameters
    ----------
    use_cdn : bool or {"auto"}
        The document's resolved ``use_cdn``.
    inline : bool
        True on a path that serializes into an iframe, which keeps only
        tags; False for a document, which keeps dependencies in its head.

    Returns
    -------
    htmltools.Tag, htmltools.HTMLDependency, or None
        A ``<script>`` for a frame, a head-only dependency for a document
        (listed ahead of the bundle's, so it renders above its
        ``<script>``), or ``None`` when nothing is declared.
    """
    script = locale_config_js(locale_base_url(bundled=use_cdn is False))
    if not script:
        return None
    from htmltools import HTMLDependency, tags

    tag = tags.script(script, type="text/javascript")
    if inline:
        return tag
    return HTMLDependency(name="maidr-locale-config", version="1.0.0", head=tag)
