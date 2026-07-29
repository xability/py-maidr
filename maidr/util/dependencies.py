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

Resolving the published version also makes the *bundled* copy's age
observable.  The bundle is refreshed at py-maidr release time, so it can
drift behind upstream between releases — and a render that falls back to
it silently runs older code.  :func:`bundle_status` reports that drift and
:func:`warn_if_bundle_is_stale` surfaces it once per process when the gap
grows large enough to matter.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import warnings
from functools import lru_cache
from http.client import HTTPException
from importlib.resources import as_file, files
from pathlib import Path
from typing import NamedTuple
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

#: Reported by :func:`maidr_js_version` when ``static/VERSION`` is absent
#: or empty.  Means "no bundled version to speak of", so callers treat it
#: as unknown rather than as an ancient release.
_UNKNOWN_VERSION = "0.0.0"

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

#: Time budget, in seconds, shared across the whole version lookup rather
#: than applied per request, so adding a fallback endpoint cannot multiply
#: how long a first render blocks.  Approximate rather than a hard ceiling
#: — see :func:`_fetch_latest_version`.
CDN_TIMEOUT_ENV_VAR = "MAIDR_CDN_TIMEOUT"
_DEFAULT_CDN_TIMEOUT = 3.0

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

# Same intent as the guard in ``.github/scripts/fetch-maidr-bundle.sh``:
# only a well-formed semver is ever spliced into a URL, so neither a
# hostile ``MAIDR_CDN_VERSION`` nor a compromised registry response can
# steer the request at a path we did not intend.
#
# Spelled out as semver's real grammar — an optional ``-prerelease``
# followed by an optional ``+build`` — rather than a repeated
# ``(?:[-+.]...)*`` group.  The repeated form lets ``-`` and ``.`` both
# open a group *and* appear inside it, so an input like ``9.9.9+`` plus
# many ``--`` pairs has exponentially many parses and backtracks forever.
# Here neither suffix class contains ``+``, so the split is unambiguous
# and matching stays linear.
_VERSION_RE = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)

# Keys of warnings already logged, so a bad pin is reported once instead
# of on every URL build.  See :func:`_warn_once`.
_warned_keys: set[str] = set()

# Ceilings on the above.  Normal use adds nothing or one entry; these
# only matter for a process that programmatically cycles through many
# distinct bad pins.  Both are needed for the bound to be real: capping
# the entry count alone still lets one arbitrarily long pin become an
# arbitrarily long key.
_MAX_WARNED_KEYS = 64
_MAX_WARNED_KEY_LEN = 200

# Deliberately not guarded by ``_resolution_lock`` below: this is a lone
# reference assignment, which is atomic under the GIL, and it is only ever
# written by an explicit :func:`set_cdn_version` call.  The lock exists to
# stop concurrent *lookups*, which is a compound read-modify-write, not to
# protect this.
_cdn_version_override: str | None = None

_resolved_cdn_version: str | None = None
_resolution_attempted: bool = False
_resolution_lock = threading.Lock()

# Unresolved CDN URLs, kept as module constants for callers that want the
# literal ``@latest`` form.  These are also what :func:`maidr_js_cdn_url`
# and :func:`maidr_css_cdn_url` fall back to when the version lookup
# cannot reach the network.
#
# DO NOT reference these from a render path.  ``@latest`` is the mutable
# dist-tag whose seven-day cache lifetime is the bug this module exists to
# fix, so emitting one into HTML silently reintroduces it.  Call
# :func:`maidr_js_cdn_url` / :func:`maidr_css_cdn_url` / :func:`cdn_url`
# instead — ``tests/core/test_cdn_version.py`` enforces this.
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

        Both tags keep the lookup offline: if the bundled ``VERSION`` is
        missing or unparseable, :data:`BUNDLED_TAG` warns and degrades to
        :data:`LATEST_TAG` rather than reaching for the network, since
        asking for the installed copy implies staying local.

    Notes
    -----
    Process-wide, not per-session: this writes module-level state shared
    by every caller in the interpreter, matching ``set_use_cdn``.  In a
    server handling concurrent sessions (e.g. Shiny), one session calling
    this changes what the others render — prefer ``MAIDR_CDN_VERSION`` at
    startup, or an explicit ``use_cdn=`` per call.

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
    pin = _version_pin()
    if pin is not None:
        return pin
    return _resolve_latest_version() or LATEST_TAG


def _version_pin() -> str | None:
    """Return the normalised explicit pin, or ``None`` if there is none."""
    pin = _cdn_version_override
    if pin is None:
        pin = os.environ.get(CDN_VERSION_ENV_VAR)
    if pin is None:
        return None
    return _normalise_version_pin(pin)


def _known_cdn_version() -> str | None:
    """Return the published version *if it is already known*.

    Unlike :func:`get_cdn_version` this never issues a network request:
    it reports only what an explicit pin or an earlier lookup has already
    established.  Callers on the offline path use it so that surfacing a
    stale bundle can never itself reach for the network.

    Returns
    -------
    str or None
        A concrete version, or ``None`` when the published version is
        unknown (unresolved, or deliberately pinned to ``latest``).
    """
    pin = _version_pin()
    if pin is not None:
        return None if pin == LATEST_TAG else pin
    if _resolution_attempted:
        return _resolved_cdn_version
    return None


def reset_cdn_version_cache() -> None:
    """Discard the cached ``latest`` lookup so the next URL re-resolves.

    Both successful and failed lookups are cached for the lifetime of the
    process — the failure case deliberately so, because an offline
    notebook must not stall on a doomed request for every figure it
    renders.  Long-lived processes that want to pick up a newer release
    can call this to force one more attempt.

    Does not re-arm the one-shot staleness warning from
    :func:`warn_if_bundle_is_stale`, which stays spent for the life of
    the process regardless of how often the version is re-resolved.
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
        if _VERSION_RE.match(bundled) and bundled != _UNKNOWN_VERSION:
            return bundled
        # Asking for ``bundled`` is a request to serve what is installed,
        # which implies staying local.  Falling through to a network
        # lookup would betray that intent for someone who chose it to
        # avoid egress, so degrade to ``@latest`` — still a working URL,
        # still no request.
        _warn_once(
            f"{BUNDLED_TAG}:{bundled}",
            "maidr: %s=%s requested but the bundled VERSION is %r; "
            "falling back to the %r dist-tag without resolving. "
            "Reinstall py-maidr to repair the bundle.",
            CDN_VERSION_ENV_VAR,
            BUNDLED_TAG,
            bundled,
            LATEST_TAG,
        )
        return LATEST_TAG
    # Accept a leading ``v`` (``v3.74.0``) since that is how the version
    # is written in git tags and release notes.
    candidate = candidate[1:] if candidate.startswith(("v", "V")) else candidate
    if _VERSION_RE.match(candidate):
        return candidate
    # Truncate for display too: the key is capped, but an oversized pin
    # would otherwise land in the log line at full length.
    _warn_once(
        f"pin:{pin}",
        "maidr: ignoring invalid CDN version pin %r; expected a semver "
        "such as '3.74.0', %r, or %r.",
        pin[:_MAX_WARNED_KEY_LEN],
        BUNDLED_TAG,
        LATEST_TAG,
    )
    return None


def _warn_once(key: str, message: str, *args: object) -> None:
    """Log a warning the first time it is seen, then stay quiet about it.

    :func:`_normalise_version_pin` runs on every URL build — twice per
    figure in the CDN modes — so a single typo'd ``MAIDR_CDN_VERSION``
    would otherwise log two lines per rendered plot for the life of the
    process.  Deduplicating by ``key`` rather than warning once globally
    keeps a *second*, differently-broken pin audible.

    Parameters
    ----------
    key : str
        Identity of this warning.  Include the offending value so that
        changing the value re-warns.  Truncated to
        :data:`_MAX_WARNED_KEY_LEN`, so two pins identical for that many
        characters share one warning.
    message : str
        ``logging``-style format string.
    *args : object
        Arguments interpolated into ``message`` by the logger.
    """
    key = key[:_MAX_WARNED_KEY_LEN]
    if key in _warned_keys:
        return
    if len(_warned_keys) >= _MAX_WARNED_KEYS:
        # Start over rather than grow without bound.  A process churning
        # through this many distinct bad pins will see the occasional
        # repeat, which is a fair trade for fixed memory.
        _warned_keys.clear()
    # ``set.add`` is atomic under the GIL, so no lock is needed here; the
    # worst a race can do is emit the line twice.
    _warned_keys.add(key)
    _logger.warning(message, *args)


def _cdn_timeout() -> float:
    """Return the total time budget for the version lookup, in seconds.

    Notes
    -----
    A non-numeric or non-positive ``MAIDR_CDN_TIMEOUT`` (including ``0``)
    falls back to the default budget rather than meaning "no budget" or
    "skip the lookup" — ``MAIDR_CDN_VERSION=latest`` is the supported way
    to opt out of resolving entirely.

    No upper bound is imposed: the value is explicit configuration from
    whoever set it, and silently clamping it would be the more surprising
    behaviour.  A large value does mean a first render can block for that
    long.
    """
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


def _fetch_latest_version(budget: float) -> str | None:
    """Query the resolver endpoints for the concrete ``latest`` version.

    Parameters
    ----------
    budget : float
        Total seconds allowed for the whole lookup.  Each attempt gets
        whatever is left, so trying a second endpoint cannot double how
        long the caller blocks.

    Returns
    -------
    str or None
        A validated semver string, or ``None`` if every endpoint failed.

    Notes
    -----
    Never raises: a version lookup failing must degrade to the ``@latest``
    URL, not break rendering.

    The budget is approximate, not a hard ceiling.  It is enforced by
    handing each attempt the remaining time as its socket timeout, and
    ``urlopen`` applies that per blocking socket operation — connect, TLS
    handshake, read — rather than to the call as a whole.  An endpoint
    that stalls just under the limit at each step in turn can therefore
    overrun the budget by a small multiple.

    What it does bound reliably is the failure mode that actually bites:
    a firewall blackholing packets, where each attempt would otherwise
    burn a full timeout, and where the number of endpoints would multiply
    the wait.  Hard-capping the total would need a watchdog thread, which
    is not worth it for two endpoints returning sub-kilobyte payloads.
    """
    deadline = time.monotonic() + budget
    for url, key in _RESOLVER_ENDPOINTS:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            _logger.debug(
                "maidr: CDN version lookup budget spent before trying %s", url
            )
            break
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


# ---------------------------------------------------------------------------
# Bundled-copy freshness
# ---------------------------------------------------------------------------

#: Minor-version gap at which the bundled fallback stops being "a release
#: or two behind" and starts being a copy users should know about.  The
#: bug report that prompted this check cited a gap of 8.
STALE_MINOR_GAP = 5

#: Set to ``0`` / ``false`` / ``off`` to silence the staleness warning.
BUNDLE_WARNING_ENV_VAR = "MAIDR_BUNDLE_STALE_WARNING"

# Same grammar as :data:`_VERSION_RE`, with the parts named so
# :func:`_version_key` can pull them out.  Kept deliberately in step with
# it: a looser shape here would mean a version this module refuses to pin
# could still be parsed for comparison, and any future caller that reused
# this on less-trusted input would not inherit the same hardening.
_RELEASE_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?P<prerelease>-[0-9A-Za-z.-]+)?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)

_bundle_warning_emitted = False
_bundle_warning_lock = threading.Lock()


class BundleStatus(NamedTuple):
    """How the bundled ``maidr.js`` compares to the published release.

    Attributes
    ----------
    bundled : str
        Version of the copy shipped inside this wheel.
    published : str or None
        The published version the CDN would serve, or ``None`` when that
        is unknown (not resolved, or pinned to ``latest``).
    is_behind : bool
        ``True`` when the bundled copy is older than ``published``.
    is_stale : bool
        ``True`` when it is behind by at least a major version or
        :data:`STALE_MINOR_GAP` minor versions — the threshold at which
        :func:`warn_if_bundle_is_stale` speaks up.
    """

    bundled: str
    published: str | None
    is_behind: bool
    is_stale: bool


def bundle_status(*, resolve: bool = True) -> BundleStatus:
    """Compare the bundled ``maidr.js`` against the published release.

    Parameters
    ----------
    resolve : bool, default=True
        Whether to resolve the published version over the network when it
        is not already known.  Pass ``False`` on offline code paths: the
        comparison then uses only an explicit pin or an earlier lookup,
        and reports ``published=None`` if neither is available.

    Returns
    -------
    BundleStatus
        The two versions and how far apart they are.  Unparseable or
        unknown versions yield ``is_behind=is_stale=False`` rather than a
        guess.

    Examples
    --------
    >>> status = bundle_status()  # doctest: +SKIP
    >>> status.bundled, status.published, status.is_behind  # doctest: +SKIP
    ('3.73.0', '3.74.0', True)
    """
    bundled = maidr_js_version()
    published = get_cdn_version() if resolve else _known_cdn_version()
    if published == LATEST_TAG:
        published = None

    bundled_key = _version_key(bundled) if bundled != _UNKNOWN_VERSION else None
    published_key = _version_key(published) if published else None
    if bundled_key is None or published_key is None:
        return BundleStatus(bundled, published, is_behind=False, is_stale=False)

    is_behind = bundled_key < published_key
    (bundled_major, bundled_minor, _), _ = bundled_key
    (published_major, published_minor, _), _ = published_key
    is_stale = is_behind and (
        published_major > bundled_major
        or published_minor - bundled_minor >= STALE_MINOR_GAP
    )
    return BundleStatus(bundled, published, is_behind, is_stale)


def warn_if_bundle_is_stale() -> None:
    """Warn once per process when the bundled fallback has drifted badly.

    Intended for the render paths where the bundled copy can actually be
    executed — ``use_cdn=False`` (it is the only source) and
    ``use_cdn="auto"`` (it is the offline fallback).  Never issues a
    network request of its own: it compares against the published version
    only when that is already known, so an offline render stays offline
    and simply says nothing.

    That leaves a deliberate blind spot.  A process using *only*
    ``use_cdn=False`` with no pin never establishes a published version
    to compare against, so it stays silent however old its bundle is —
    and that is precisely the air-gapped audience the warning is for.
    Reaching them automatically would require the network request that
    ``use_cdn=False`` exists to avoid, so this is a partial mitigation by
    construction: :func:`bundle_status` (which does resolve) is the
    explicit check for those users, and a release-time CI comparison is
    the real answer.

    Silenced by ``MAIDR_BUNDLE_STALE_WARNING=0``.

    Notes
    -----
    Fires at most once per process, and neither :func:`set_cdn_version`
    nor :func:`reset_cdn_version_cache` re-arms it — so re-pinning in a
    REPL to watch the warning again will not produce a second one.

    ``stacklevel=2`` deliberately points at maidr's own render machinery
    rather than the caller's ``render()`` / ``save_html()`` line.  The
    depth from user code differs per entry point, so no fixed level
    reaches it, and the warning is about the *installed package* rather
    than about how it was called — the message stands alone without a
    call site.
    """
    global _bundle_warning_emitted
    if _bundle_warning_emitted or not _bundle_warning_enabled():
        return

    status = bundle_status(resolve=False)
    if not status.is_stale:
        return

    # Claim the one warning under a lock so concurrent first renders emit
    # it once rather than racing between the check above and the set.
    with _bundle_warning_lock:
        if _bundle_warning_emitted:
            return
        _bundle_warning_emitted = True

    warnings.warn(
        f"maidr: the bundled copy of maidr.js is {status.bundled}, but the "
        f"current published release is {status.published}. The bundle is "
        f"what renders when the CDN is disabled (use_cdn=False) or "
        f"unreachable (use_cdn='auto'), so those plots run the older "
        f"build. Upgrade py-maidr to pick up a refreshed bundle. Set "
        f"{BUNDLE_WARNING_ENV_VAR}=0 to silence this warning.",
        UserWarning,
        stacklevel=2,
    )


def _bundle_warning_enabled() -> bool:
    """Return whether the staleness warning is enabled (it is by default)."""
    raw = os.environ.get(BUNDLE_WARNING_ENV_VAR)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _version_key(version: str) -> tuple[tuple[int, int, int], int] | None:
    """Return a sortable key for a semver string.

    Parameters
    ----------
    version : str
        A version such as ``"3.74.0"`` or ``"3.74.0-rc.1"``.

    Returns
    -------
    tuple or None
        ``((major, minor, patch), rank)`` where ``rank`` is ``0`` for a
        prerelease and ``1`` for a final release, so ``3.74.0-rc.1``
        sorts before ``3.74.0``.  ``None`` when the string is not a
        version we can compare.
    """
    match = _RELEASE_RE.match(version.strip())
    if match is None:
        return None
    release = (int(match["major"]), int(match["minor"]), int(match["patch"]))
    return release, 0 if match["prerelease"] else 1


@lru_cache(maxsize=1)
def maidr_js_version() -> str:
    """Return the bundled ``maidr.js`` version string.

    Reads ``maidr/static/VERSION`` which is populated either by hand or
    by the ``update-maidr-js`` GitHub Actions workflow.

    Returns
    -------
    str
        The semver string (e.g. ``"3.63.0"``) of the bundled JS assets,
        or ``"0.0.0"`` when the VERSION file is missing.

    Notes
    -----
    Cached for the process: the file ships inside the wheel and cannot
    change under a running interpreter.  Without this, pinning to
    :data:`BUNDLED_TAG` would re-read it twice per figure, since
    :func:`_normalise_version_pin` runs on every URL build.
    """
    try:
        version_resource = files(_STATIC_PACKAGE).joinpath(
            _STATIC_SUBDIR, _VERSION_FILENAME
        )
        text = version_resource.read_text(encoding="utf-8").strip()
        return text or _UNKNOWN_VERSION
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return _UNKNOWN_VERSION


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
