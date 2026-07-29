"""Helpers for locating and referencing the bundled ``maidr.js`` assets.

This module centralises the logic for switching between CDN-hosted and
locally bundled copies of the MAIDR JavaScript and CSS.  A prebuilt copy
of ``maidr.js`` is shipped inside the wheel under ``maidr/static/`` so
that users with no internet connection can still render accessible
plots by passing ``use_cdn=False`` to the public API.

It also owns *CDN version resolution*.  Emitting the mutable
``maidr@latest`` dist-tag in a ``<script src=...>`` is what made browsers
serve a week-old ``maidr.js``: jsDelivr answers that URL with
``Cache-Control: public, max-age=604800``, so a browser that fetched it
once keeps replaying its cached copy long after a new release lands.
Resolving ``latest`` to a concrete version in Python at render time and
emitting ``maidr@<version>/dist/maidr.js`` instead changes the cache key
on every release, which makes the stale-cache window disappear *and*
lets the browser cache each build permanently.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from http.client import HTTPException
from importlib.resources import as_file, files
from pathlib import Path
from urllib.request import Request, urlopen


_logger = logging.getLogger(__name__)

# Package-relative locations of the bundled assets.  Kept here as module
# constants so tests and tooling have a single source of truth.
_STATIC_PACKAGE = "maidr"
_STATIC_SUBDIR = "static"
MAIDR_JS_FILENAME = "maidr.js"
MAIDR_CSS_FILENAME = "maidr.css"
MAIDR_VEGALITE_FILENAME = "vegalite.js"
_VERSION_FILENAME = "VERSION"

# ---------------------------------------------------------------------------
# CDN version resolution
# ---------------------------------------------------------------------------

_CDN_URL_TEMPLATE = "https://cdn.jsdelivr.net/npm/maidr@{version}/dist/{filename}"

#: Version specifier meaning "emit the mutable ``@latest`` dist-tag and do
#: not contact the network".  This is the pre-resolution behaviour.
LATEST_TAG = "latest"

#: Version specifier meaning "use the version of the bundle shipped inside
#: this wheel", i.e. serve over the CDN exactly what the offline fallback
#: would serve.
BUNDLED_TAG = "bundled"

#: Pin the CDN version without touching Python (``MAIDR_CDN_VERSION=3.74.0``,
#: ``=bundled``, or ``=latest`` to opt out of resolution entirely).
CDN_VERSION_ENV_VAR = "MAIDR_CDN_VERSION"

#: Per-request timeout, in seconds, for the version lookup.
CDN_TIMEOUT_ENV_VAR = "MAIDR_CDN_TIMEOUT"
_DEFAULT_CDN_TIMEOUT = 2.0

# Endpoints consulted, in order, to turn the mutable ``latest`` dist-tag
# into a concrete version.  jsDelivr's data API comes first because it is
# the authority on what ``cdn.jsdelivr.net`` will actually serve; the npm
# registry's dist-tags endpoint is the backup.  Both return small JSON
# documents, so the lookup costs one short round trip per process.
_RESOLVER_ENDPOINTS: tuple[tuple[str, str], ...] = (
    (
        "https://data.jsdelivr.com/v1/packages/npm/maidr/resolved"
        "?specifier=latest",
        "version",
    ),
    ("https://registry.npmjs.org/-/package/maidr/dist-tags", "latest"),
)

# Cap on how much of a resolver response we read, so a hostile or broken
# endpoint cannot stream an unbounded body into memory.
_MAX_RESOLVER_BYTES = 64 * 1024

# Mirrors the guard in ``.github/scripts/fetch-maidr-bundle.sh``: only a
# well-formed semver is ever spliced into a URL, so neither a hostile
# ``MAIDR_CDN_VERSION`` nor a compromised registry response can steer the
# request at a path we did not intend.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)*$")

_cdn_version_override: str | None = None
_resolved_cdn_version: str | None = None
_resolution_attempted: bool = False
_resolution_lock = threading.Lock()

# Unresolved CDN URLs, kept as module constants for callers that want the
# literal ``@latest`` form.  These are also what :func:`maidr_js_cdn_url`
# and :func:`maidr_css_cdn_url` fall back to when the version lookup
# cannot reach the network.
MAIDR_JS_CDN_URL = _CDN_URL_TEMPLATE.format(
    version=LATEST_TAG, filename=MAIDR_JS_FILENAME
)
MAIDR_CSS_CDN_URL = _CDN_URL_TEMPLATE.format(
    version=LATEST_TAG, filename=MAIDR_CSS_FILENAME
)


def set_cdn_version(version: str | None) -> None:
    """Pin the ``maidr`` version referenced by emitted CDN URLs.

    Parameters
    ----------
    version : str or None
        A concrete version (``"3.74.0"``, optionally ``v``-prefixed),
        :data:`BUNDLED_TAG` to mirror the version bundled in this wheel,
        or :data:`LATEST_TAG` to emit the mutable ``@latest`` dist-tag and
        skip the network lookup entirely.  ``None`` clears the pin and
        discards any cached lookup so the next URL re-resolves.

    Notes
    -----
    Takes precedence over the ``MAIDR_CDN_VERSION`` environment variable.
    A value that is neither a recognised tag nor a valid semver is
    ignored (with a warning) in favour of the normal resolution path.
    """
    global _cdn_version_override
    if version is None:
        _cdn_version_override = None
        reset_cdn_version_cache()
        return
    _cdn_version_override = str(version).strip()


def get_cdn_version() -> str:
    """Return the ``maidr`` version to splice into CDN URLs.

    Resolution order:

    1. An explicit pin from :func:`set_cdn_version`.
    2. The ``MAIDR_CDN_VERSION`` environment variable.
    3. The ``latest`` dist-tag resolved over the network (once per
       process, then cached).
    4. The literal string ``"latest"`` when the lookup fails, which
       reproduces the library's historical behaviour.

    Returns
    -------
    str
        A concrete version such as ``"3.74.0"``, or ``"latest"``.
    """
    pin = _cdn_version_override
    if pin is None:
        pin = os.environ.get(CDN_VERSION_ENV_VAR)
    if pin is not None:
        normalised = _normalise_version_pin(pin)
        if normalised is not None:
            return normalised
    return _resolve_latest_version() or LATEST_TAG


def reset_cdn_version_cache() -> None:
    """Discard the cached ``latest`` lookup so the next URL re-resolves.

    Both successful and failed lookups are cached for the lifetime of the
    process — the failure case deliberately so, because an offline
    notebook must not stall on a doomed request for every figure it
    renders.  Long-lived processes that want to pick up a newer release
    can call this to force one more attempt.
    """
    global _resolved_cdn_version, _resolution_attempted
    with _resolution_lock:
        _resolved_cdn_version = None
        _resolution_attempted = False


def cdn_url(filename: str) -> str:
    """Return the jsDelivr URL for a ``dist/`` asset at the resolved version.

    Parameters
    ----------
    filename : str
        Asset name under the package's ``dist/`` directory, e.g.
        ``"maidr.js"``.

    Returns
    -------
    str
        A fully qualified jsDelivr URL.
    """
    return _CDN_URL_TEMPLATE.format(version=get_cdn_version(), filename=filename)


def maidr_js_cdn_url() -> str:
    """Return the CDN URL for ``maidr.js`` at the resolved version."""
    return cdn_url(MAIDR_JS_FILENAME)


def maidr_css_cdn_url() -> str:
    """Return the CDN URL for ``maidr.css`` at the resolved version."""
    return cdn_url(MAIDR_CSS_FILENAME)


def _normalise_version_pin(pin: str) -> str | None:
    """Turn a user-supplied version specifier into a URL-safe string.

    Parameters
    ----------
    pin : str
        Raw specifier from :func:`set_cdn_version` or the environment.

    Returns
    -------
    str or None
        The version to use, or ``None`` when the specifier is empty or
        unusable and the caller should fall through to network
        resolution.
    """
    candidate = pin.strip()
    if not candidate:
        return None
    if candidate.lower() == LATEST_TAG:
        return LATEST_TAG
    if candidate.lower() == BUNDLED_TAG:
        bundled = maidr_js_version()
        if _VERSION_RE.match(bundled) and bundled != "0.0.0":
            return bundled
        _logger.warning(
            "maidr: %s=%s requested but the bundled VERSION is %r; "
            "resolving the latest published version instead.",
            CDN_VERSION_ENV_VAR,
            BUNDLED_TAG,
            bundled,
        )
        return None
    # Accept a leading ``v`` (``v3.74.0``) since that is how the version
    # is written in git tags and release notes.
    candidate = candidate[1:] if candidate.startswith(("v", "V")) else candidate
    if _VERSION_RE.match(candidate):
        return candidate
    _logger.warning(
        "maidr: ignoring invalid CDN version pin %r; expected a semver "
        "such as '3.74.0', %r, or %r.",
        pin,
        BUNDLED_TAG,
        LATEST_TAG,
    )
    return None


def _cdn_timeout() -> float:
    """Return the per-request timeout for the version lookup, in seconds."""
    raw = os.environ.get(CDN_TIMEOUT_ENV_VAR)
    if raw is None:
        return _DEFAULT_CDN_TIMEOUT
    try:
        timeout = float(raw)
    except ValueError:
        _logger.debug("maidr: ignoring non-numeric %s=%r", CDN_TIMEOUT_ENV_VAR, raw)
        return _DEFAULT_CDN_TIMEOUT
    return timeout if timeout > 0 else _DEFAULT_CDN_TIMEOUT


def _resolve_latest_version() -> str | None:
    """Return the cached ``latest`` version, resolving it on first use.

    Returns
    -------
    str or None
        The concrete version behind the ``latest`` dist-tag, or ``None``
        when it could not be resolved (offline, blocked, or malformed
        response).
    """
    global _resolved_cdn_version, _resolution_attempted
    if _resolution_attempted:
        return _resolved_cdn_version
    with _resolution_lock:
        if _resolution_attempted:
            return _resolved_cdn_version
        _resolved_cdn_version = _fetch_latest_version(_cdn_timeout())
        _resolution_attempted = True
    return _resolved_cdn_version


def _fetch_latest_version(timeout: float) -> str | None:
    """Query the resolver endpoints for the concrete ``latest`` version.

    Parameters
    ----------
    timeout : float
        Per-request timeout in seconds.

    Returns
    -------
    str or None
        A validated semver string, or ``None`` if every endpoint failed.

    Notes
    -----
    Never raises: a version lookup failing must degrade to the ``@latest``
    URL, not break rendering.
    """
    for url, key in _RESOLVER_ENDPOINTS:
        try:
            # ``url`` is one of the hard-coded https:// endpoints above, never
            # anything caller-supplied, so there is no scheme to smuggle here.
            request = Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "py-maidr"},
            )
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(
                    response.read(_MAX_RESOLVER_BYTES).decode("utf-8")
                )
        except (OSError, HTTPException, ValueError, UnicodeDecodeError):
            _logger.debug("maidr: CDN version lookup failed at %s", url, exc_info=True)
            continue

        candidate = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(candidate, str) and _VERSION_RE.match(candidate.strip()):
            return candidate.strip()
        _logger.debug("maidr: unusable CDN version %r from %s", candidate, url)
    return None


def maidr_js_version() -> str:
    """Return the bundled ``maidr.js`` version string.

    Reads ``maidr/static/VERSION`` which is populated either by hand or
    by the ``update-maidr-js`` GitHub Actions workflow.

    Returns
    -------
    str
        The semver string (e.g. ``"3.63.0"``) of the bundled JS assets,
        or ``"0.0.0"`` when the VERSION file is missing.
    """
    try:
        version_resource = files(_STATIC_PACKAGE).joinpath(
            _STATIC_SUBDIR, _VERSION_FILENAME
        )
        return version_resource.read_text(encoding="utf-8").strip() or "0.0.0"
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return "0.0.0"


def _bundled_asset_path(filename: str) -> Path:
    """Return an on-disk path to a bundled static asset.

    Parameters
    ----------
    filename : str
        File name relative to ``maidr/static/``.

    Returns
    -------
    pathlib.Path
        Absolute filesystem path to the requested asset.

    Raises
    ------
    FileNotFoundError
        If the requested asset is not shipped with the installed package.
    """
    resource = files(_STATIC_PACKAGE).joinpath(_STATIC_SUBDIR, filename)
    # ``as_file`` is a context manager, but for regular installs the
    # resource is already a real filesystem path.  We materialise it to
    # a concrete ``Path`` so callers can treat it like any other file.
    with as_file(resource) as path:
        if not path.exists():
            raise FileNotFoundError(
                f"Bundled MAIDR asset '{filename}' is missing. "
                "Reinstall py-maidr or run the update-maidr-js workflow."
            )
        return Path(path)


def bundled_js_path() -> Path:
    """Return the filesystem path to the bundled ``maidr.js`` file."""
    return _bundled_asset_path(MAIDR_JS_FILENAME)


def bundled_css_path() -> Path:
    """Return the filesystem path to the bundled MAIDR stylesheet."""
    return _bundled_asset_path(MAIDR_CSS_FILENAME)


def read_bundled_js() -> str:
    """Return the contents of the bundled ``maidr.js`` as a string."""
    return bundled_js_path().read_text(encoding="utf-8")


def maidr_html_dependency():
    """Return an :class:`htmltools.HTMLDependency` for the bundled assets.

    The dependency points at the ``maidr/static/`` directory inside the
    installed package.  When consumed by
    :meth:`htmltools.HTMLDocument.save_html`, ``htmltools`` copies the
    assets into the HTML file's ``lib_dir`` and rewrites ``<script>``
    / ``<link>`` tags to use relative paths, producing a self-contained
    output directory that works without network access.

    Returns
    -------
    htmltools.HTMLDependency
        Dependency describing the bundled JS and CSS assets.
    """
    # Imported lazily so this module stays importable even in contexts
    # where ``htmltools`` may not be fully initialised.
    from htmltools import HTMLDependency

    return HTMLDependency(
        name="maidr",
        version=maidr_js_version(),
        source={"package": _STATIC_PACKAGE, "subdir": _STATIC_SUBDIR},
        script=[{"src": MAIDR_JS_FILENAME}],
        stylesheet=[{"href": MAIDR_CSS_FILENAME}],
        all_files=False,
    )


def maidr_bundled_relative_dir() -> str:
    """Return the relative directory htmltools uses for the bundled assets.

    htmltools writes dependencies under ``lib/<name>-<version>/`` when
    ``save_html`` materialises them.  The ``use_cdn="auto"`` code
    path needs this path as a JS string so the browser can fall back to
    the bundled copy if the CDN fetch fails.

    Returns
    -------
    str
        Relative directory such as ``"lib/maidr-3.63.0"``.
    """
    return f"lib/maidr-{maidr_js_version()}"


def maidr_bundled_files_dependency():
    """Return an ``HTMLDependency`` that copies the bundle without tags.

    For ``use_cdn="auto"`` we want ``htmltools`` to materialise the
    bundled ``maidr.js`` / ``maidr.css`` into ``lib_dir`` so the browser
    can fall back to them, *without* emitting automatic ``<script>`` or
    ``<link>`` tags that would load the bundle unconditionally.  Passing
    ``script=[]`` and ``stylesheet=[]`` with ``all_files=True`` achieves
    exactly that: the files are copied, but the caller controls how
    they are referenced.

    Returns
    -------
    htmltools.HTMLDependency
        A no-tag dependency that copies every file under
        ``maidr/static/`` into the output ``lib_dir``.
    """
    from htmltools import HTMLDependency

    return HTMLDependency(
        name="maidr",
        version=maidr_js_version(),
        source={"package": _STATIC_PACKAGE, "subdir": _STATIC_SUBDIR},
        script=[],
        stylesheet=[],
        all_files=True,
    )
