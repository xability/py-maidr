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

import asyncio
import json
import logging
import math
import os
import re
import threading
import time
import warnings
from collections.abc import Iterable
from functools import lru_cache
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

#: KaTeX, which styles LaTeX in AI chat responses.
#:
#: maidr 3.75.1 moved it out of :data:`MAIDR_CSS_FILENAME` -- which is now a
#: 406-byte placeholder kept alive only so that existing ``<link>`` tags do
#: not 404 -- and made ``maidr.js`` fetch this file on demand, the first
#: time a response actually contains maths.  Nothing links it: the runtime
#: resolves it against the URL ``maidr.js`` was loaded from, so it simply
#: has to *be* in the same directory.
MAIDR_MATH_CSS_FILENAME = "maidr-math.css"

#: The release that made the split above true.
#:
#: Before it, ``maidr.css`` carried KaTeX and had to be linked.  py-maidr
#: links no stylesheet at all now, so pinning the CDN to anything older
#: leaves LaTeX in AI chat responses unstyled -- everything else is
#: unaffected, since the interface has been styled at runtime throughout.
#: :func:`_warn_if_pin_predates_stylesheet_split` says so once rather than
#: letting it be discovered.
_STYLESHEET_SPLIT_VERSION = "3.75.1"

_VERSION_FILENAME = "VERSION"

#: Reported by :func:`maidr_js_version` when ``static/VERSION`` is absent
#: or empty.  Means "no bundled version to speak of", so callers treat it
#: as unknown rather than as an ancient release.
_UNKNOWN_VERSION = "0.0.0"

# ---------------------------------------------------------------------------
# CDN version resolution
# ---------------------------------------------------------------------------

_CDN_URL_TEMPLATE = "https://cdn.jsdelivr.net/npm/maidr@{version}/dist/{filename}"

#: CDN-only asset: the Altair adapter loads it, but the wheel does not
#: ship it, so it must never be passed to :func:`_bundled_asset_path`.
MAIDR_VEGALITE_FILENAME = "vegalite.js"

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

#: Ceiling on the above.  Far beyond any legitimate lookup, so a larger
#: value indicates a mistake — most plausibly milliseconds — rather than
#: an intent to wait that long before a plot appears.
_MAX_CDN_TIMEOUT = 30.0

#: Floor on the same value, for the mistake in the other direction.  A
#: budget below this cannot complete a round trip, so every attempt times
#: out, the failure is cached, and every render for the rest of the
#: process emits ``@latest`` — silently reinstating the stale-cache bug
#: this module exists to fix.  ``MAIDR_CDN_TIMEOUT=0.05`` from someone
#: wanting the lookup to be fast is the plausible way to get there; the
#: milliseconds misreading (``=100``) lands on the ceiling instead.
_MIN_CDN_TIMEOUT = 0.1

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


def _unresolved_cdn_url(filename: str) -> str:
    """Format the ``@latest`` URL for ``filename``.  See public wrapper."""
    return _CDN_URL_TEMPLATE.format(version=LATEST_TAG, filename=filename)


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
# ``[0-9]`` rather than ``\d``: on a ``str`` pattern ``\d`` matches the
# whole Unicode Nd category, so ``٣.٧.٤`` would pass here and fail the
# shell guard's ``[0-9]`` — and would splice a URL that silently 404s.
# ``\Z`` rather than ``$``, which in Python also matches just before a
# trailing newline, so ``"3.74.0\n"`` would validate.
#
# The identifier fragments below are shared by :data:`_VERSION_RE` and
# :data:`_RELEASE_RE` so the validator and the comparator cannot drift into
# disagreeing about what a version is — a looser comparator would parse
# shapes the validator rejects, and a looser validator would hand the
# comparator input it has no sensible ordering for.

#: ``0`` or a digit run with no leading zero, per semver §9.  Rejecting
#: ``3.074.0`` matters because ``int()`` would silently read it as 74 and
#: make it compare equal to ``3.74.0``.
_NUMERIC_ID = r"0|[1-9][0-9]*"

#: A prerelease identifier: numeric (no leading zeros) or alphanumeric
#: (at least one non-digit).  Both alternatives require a character, so
#: ``3.74.0-.`` — an *empty* identifier, which :func:`_prerelease_key`
#: would rank above every numeric one and order nonsensically — no longer
#: parses.
_PRERELEASE_ID = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_PRERELEASE = rf"{_PRERELEASE_ID}(?:\.{_PRERELEASE_ID})*"

#: Build identifiers are plain non-empty alphanumerics; semver allows
#: leading zeros here because build metadata never carries precedence.
_BUILD_ID = r"[0-9A-Za-z-]+"
_BUILD = rf"{_BUILD_ID}(?:\.{_BUILD_ID})*"

# Each repetition above must consume a literal ``.``, which appears in no
# identifier class, so no input has two parses across iterations and
# matching stays linear.  ``test_version_regex_does_not_backtrack_
# catastrophically`` holds that to a wall-clock bound.
_VERSION_RE = re.compile(
    rf"^(?:{_NUMERIC_ID})\.(?:{_NUMERIC_ID})\.(?:{_NUMERIC_ID})"
    rf"(?:-{_PRERELEASE})?(?:\+{_BUILD})?\Z"
)

#: Length ceiling applied before the pattern.  The pattern bounds the
#: *shape* of a version but not its size, and unbounded numeric fields
#: are not merely untidy: ``int()`` raises ``ValueError`` above CPython's
#: 4300-digit integer-string conversion limit, so a version like
#: ``3.74.0-`` plus five thousand digits validates, gets spliced into a
#: URL, and then explodes out of ``render()`` when compared.  Real npm
#: versions are far under this.
_MAX_VERSION_LEN = 128


def _is_valid_version(candidate: str) -> bool:
    """Return whether ``candidate`` is a version we will accept.

    Checks size before shape, so nothing unbounded reaches the regex or,
    later, :func:`_version_key`'s ``int()`` calls.

    Parameters
    ----------
    candidate : str
        A version string from a pin, a resolver response, or the bundled
        ``VERSION`` file.

    Returns
    -------
    bool
        ``True`` when it is safe to splice into a URL and to parse.
    """
    return (
        len(candidate) <= _MAX_VERSION_LEN
        and _VERSION_RE.match(candidate) is not None
    )


# Keys of warnings already logged, so a bad pin is reported once instead
# of on every URL build.  See :func:`_warn_once`.
_warned_keys: set[str] = set()
_warned_keys_lock = threading.Lock()

# Ceilings on the above.  Normal use adds nothing or one entry; these
# only matter for a process that programmatically cycles through many
# distinct bad pins.  Both are needed for the bound to be real: capping
# the entry count alone still lets one arbitrarily long pin become an
# arbitrarily long key.
# Note the guarantee this buys is "each distinct value warns, and
# repeats stay quiet" rather than "exactly once, forever": eviction
# clears the whole set, so a value that already warned can warn again
# once 64 other distinct values have cycled through.
_MAX_WARNED_KEYS = 64
_MAX_WARNED_KEY_LEN = 200

# Deliberately not guarded by ``_resolution_lock`` below: this is a lone
# reference assignment, written only by an explicit
# :func:`set_cdn_version` call.  The lock exists to stop concurrent
# *lookups*, which are a compound read-modify-write, not to protect this.
#
# Unlike the compound update in :func:`_warn_once`, the reasoning here
# does not depend on the GIL and so survives free-threaded builds (PEP
# 703): storing a single object reference stays indivisible there, so a
# reader sees either the old value or the new one, never a torn write.
_cdn_version_override: str | None = None

_resolved_cdn_version: str | None = None
_resolution_attempted: bool = False

# Bumped by :func:`reset_cdn_version_cache`.  A fetch reads this before it
# starts and refuses to publish if it changed meanwhile, so a reset issued
# mid-request discards the in-flight answer instead of being silently
# overwritten by it.  The reset cannot simply take ``_fetch_lock``: that
# would make it block for the whole timeout budget behind the very lookup
# it is trying to abandon.
_resolution_generation: int = 0

# Guards the three globals above and nothing else, so it is only ever held
# for a few instructions.  Readers on the *offline* paths take it, and a
# lock held across a network call would let one stalled lookup freeze an
# unrelated ``use_cdn=False`` render for the whole timeout budget --
# breaking the guarantee those paths advertise.
_resolution_lock = threading.Lock()

# Serialises the lookup itself, so concurrent first renders still make one
# request between them.  Fetchers take this *then* ``_resolution_lock`` to
# publish; readers never take it, so they cannot be blocked by a fetch.
_fetch_lock = threading.Lock()

# Unresolved CDN URLs, kept only for backwards compatibility with
# callers outside this package that imported them before version
# resolution existed.  Nothing inside ``maidr/`` references them.
#
# DO NOT reference these from a render path.  ``@latest`` is the mutable
# dist-tag whose seven-day cache lifetime is the bug this module exists to
# fix, so emitting one into HTML silently reintroduces it.  Call
# :func:`maidr_js_cdn_url` / :func:`maidr_css_cdn_url` / :func:`cdn_url`
# instead — ``tests/core/test_cdn_version.py`` enforces this.
#
# Derived from :func:`unresolved_cdn_url` rather than formatting the
# template again, so "the unresolved URL" is spelled out in exactly one
# place and the constants cannot drift from the function.
MAIDR_JS_CDN_URL = _unresolved_cdn_url(MAIDR_JS_FILENAME)
MAIDR_CSS_CDN_URL = _unresolved_cdn_url(MAIDR_CSS_FILENAME)


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
    A malformed concrete version is logged and then *ignored*, which
    means the next URL resolves normally — one bounded lookup, exactly as
    if no pin had been set.  That is deliberate: mistyping ``3.74.0`` as
    ``3.74`` says "I wanted a particular version", not "I want to stay
    off the network", so recovering to the current published version is
    the closest thing to what was asked.  Contrast :data:`BUNDLED_TAG`,
    which *does* imply staying local and therefore degrades to
    :data:`LATEST_TAG` rather than resolving.  The supported ways to
    forbid the lookup outright are ``MAIDR_CDN_VERSION=latest`` and
    ``use_cdn=False``.

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
    # A blank string is treated as ``None`` rather than as a malformed
    # pin.  Otherwise it stores an empty override that later reads as
    # "no pin" and falls through silently, while every *other* unusable
    # value warns — an asymmetry with no reason behind it.
    if version is None or not str(version).strip():
        _cdn_version_override = None
        reset_cdn_version_cache()
        return
    _cdn_version_override = str(version).strip()


def get_cdn_version() -> str:
    """Return the ``maidr`` version to splice into CDN URLs.

    Resolution order:

    1. An explicit pin from :func:`set_cdn_version`.
    2. The ``MAIDR_CDN_VERSION`` environment variable.
    3. The version this wheel ships, when resolving would block an event
       loop — see :func:`_resolution_would_block`, and the note below.
    4. The ``latest`` dist-tag resolved over the network (once per
       process, then cached).
    5. The literal string ``"latest"`` when the lookup fails, which
       reproduces the library's historical behaviour.

    Returns
    -------
    str
        A concrete version such as ``"3.74.0"``, or ``"latest"``.

    Notes
    -----
    Step 5 is what makes this safe to call from a render path: an
    unreachable, blocked, or malformed resolver degrades to ``"latest"``
    rather than raising.  That guarantee rests on
    :func:`_fetch_latest_version` honouring its own "never raises"
    contract — it catches ``Exception`` around every fallible step for
    exactly this reason.  Should something slip past it anyway, the
    handler in :func:`_resolve_latest_version` caches the attempt (so the
    failure is not retried on every later render) and re-raises, so the
    exception surfaces from ``render()`` / ``save_html()``.  That is a
    deliberate fail-fast for a bug in this module rather than a third
    degradation path.

    A ``KeyboardInterrupt`` is treated differently: it is not cached, so
    interrupting one render does not leave the rest of the process
    emitting ``@latest``.

    Step 3 is the one that depends on where it is called from, and it is
    a deliberate trade.  ``maidr.render()`` is synchronous and Shiny calls
    it from ``render_maidr.render()``, which is ``async`` — so under the
    default the first figure in an app performed a blocking ``urlopen`` on
    the event loop, stalling every concurrent session behind it (#296).
    The bundled version is a real published one, so the URL resolves and
    is immutable; what is given up is picking up a release newer than the
    wheel, automatically, in an async process.

    That is the trade the docs already recommended making by hand:
    ``MAIDR_CDN_VERSION=bundled`` was the advice for Shiny apps, and this
    makes the default do it in exactly the context the advice was for.
    Two things follow that are worth knowing rather than discovering:

    * :func:`warn_if_bundle_is_stale` reads only an already-completed
      lookup, so a process that never resolves never hears it.
    * Calling this once from synchronous code at start-up caches the
      answer, after which every async render uses the resolved version --
      which is how an app that wants the newer release gets it without
      any render paying for the request.

    Synchronous callers are unaffected, including threads: they still
    resolve once per process and queue on ``_fetch_lock`` while the first
    of them does.  That queueing is not fixed here; it is the event loop
    specifically that must not be made to wait.
    """
    pin = _version_pin()
    if pin is not None:
        return pin
    if _resolution_would_block():
        return _offline_version()
    return _resolve_latest_version() or LATEST_TAG


def _version_pin() -> str | None:
    """Return the normalised explicit pin, or ``None`` if there is none."""
    pin = _cdn_version_override
    if pin is None:
        pin = os.environ.get(CDN_VERSION_ENV_VAR)
    if pin is None:
        return None
    return _normalise_version_pin(pin)


def _published_version(*, resolve: bool) -> str | None:
    """Return the version npm has actually published, ignoring any pin.

    A pin answers "which version should we serve?", which is a different
    question from "which version is current?".  Feeding a pin into the
    staleness comparison would let ``set_cdn_version("4.0.0")`` — pinning
    an unreleased build to test it — report 4.0.0 as *published* and
    advise upgrading, and would let a backwards pin mask a genuinely old
    bundle.  Only a real lookup answers the published question.

    Parameters
    ----------
    resolve : bool
        Whether to perform the lookup when the answer is not already
        cached.  ``False`` keeps the caller offline and accepts ``None``.

    Returns
    -------
    str or None
        A concrete version, or ``None`` when it is unknown.
    """
    if resolve:
        return _resolve_latest_version()
    return _cached_resolution()


def _resolution_state() -> tuple[bool, str | None]:
    """Return ``(attempted, value)`` for the cached lookup, atomically.

    Reads both globals under the lock so a caller cannot observe the flag
    without the value it refers to.  Returned as a pair because ``None``
    is ambiguous on its own: it means both "no lookup yet" and "the lookup
    failed", and the two need different handling.

    The lock is held for these two reads only — never across a network
    call — so an offline caller is never delayed by someone else's lookup.
    """
    with _resolution_lock:
        return _resolution_attempted, _resolved_cdn_version


def _cached_resolution() -> str | None:
    """Return the resolved version if a lookup has completed, else ``None``."""
    attempted, value = _resolution_state()
    return value if attempted else None


def _offline_version() -> str:
    """Return the best version available without making a request.

    The order is the same question asked three ways, cheapest first: what
    did the caller ask for, what did an earlier lookup establish, and what
    shipped in this wheel.  Only when none of those is usable does this
    fall back to :data:`LATEST_TAG`, the mutable dist-tag this module
    exists to stop emitting.

    Both offline callers read it from here rather than each spelling it
    out, because when they disagreed the result was one page loading two
    different builds of ``maidr.js`` -- an iframe on the pinned version
    and its host on the bundled one.

    Returns
    -------
    str
        A concrete version, or ``latest`` when there is no better answer.
    """
    pin = _version_pin()
    if pin is not None:
        return pin

    resolved = _cached_resolution()
    if resolved is not None and _is_valid_version(resolved):
        return resolved

    bundled = maidr_js_version()
    if _is_valid_version(bundled) and bundled != _UNKNOWN_VERSION:
        return bundled

    return LATEST_TAG


def _resolution_would_block() -> bool:
    """Report whether resolving now would stall an event loop.

    ``_resolve_latest_version`` makes a blocking ``urlopen`` call, holding
    ``_fetch_lock`` across it.  On a thread running an event loop -- which
    is where ``maidr.render()`` is called from in a Shiny app, through
    ``render_maidr.render()`` -- that stalls every other session in the
    process for up to :data:`MAIDR_CDN_TIMEOUT`, and that budget is only
    approximate: ``urlopen``'s timeout applies per socket operation and
    does not reliably cover ``getaddrinfo``, so a broken resolver can
    exceed it (#296).

    A lookup that has already completed costs nothing, so it is not
    blocking and this says so -- which is what makes the answer stable
    rather than context-dependent after the first resolution anywhere in
    the process.  Resolving once from synchronous code at start-up is
    therefore the way to have an async app serve the resolved version.

    Returns
    -------
    bool
        ``True`` only when a lookup would have to be performed *and* this
        thread is running an event loop.
    """
    attempted, _ = _resolution_state()
    if attempted:
        return False

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def unresolved_cdn_url(filename: str) -> str:
    """Return the ``@latest`` CDN URL without resolving a version.

    The last resort, reached only when no concrete version is available:
    :func:`bundled_cdn_url` falls back here when the bundled ``VERSION``
    is unusable, and :func:`get_cdn_version` returns ``latest`` when a
    lookup fails.  Prefer :func:`cdn_url` or :func:`bundled_cdn_url` —
    ``@latest`` is the mutable dist-tag this module exists to stop
    emitting.

    Parameters
    ----------
    filename : str
        Asset name under the package's ``dist/`` directory.

    Returns
    -------
    str
        A jsDelivr URL pinned to the ``latest`` dist-tag.
    """
    return _unresolved_cdn_url(filename)


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

    Returns without waiting on a lookup already in flight — it does not
    take ``_fetch_lock``, which would make the reset itself block for the
    whole budget behind the request it is abandoning.  That is a promise
    about *this* call, not about the next one: a caller that needs a
    version afterwards still queues on ``_fetch_lock`` behind the
    abandoned request, and only then makes its own.  What the generation
    counter guarantees is that the abandoned answer is discarded rather
    than published over the reset.
    """
    global _resolved_cdn_version, _resolution_attempted, _resolution_generation
    with _resolution_lock:
        _resolved_cdn_version = None
        _resolution_attempted = False
        # Invalidate any lookup already in flight, so its result cannot
        # land after this call and quietly undo it.
        _resolution_generation += 1


def cdn_url(filename: str) -> str:
    """Return the jsDelivr URL for a ``dist/`` asset at the resolved version.

    Parameters
    ----------
    filename : str
        Asset name under the package's ``dist/`` directory, e.g.
        ``"maidr.js"``.  Trusted input: unlike the version, it is not
        validated, because every call site passes one of this module's
        ``MAIDR_*_FILENAME`` constants.  Validate it here first if that
        ever stops being true.

    Returns
    -------
    str
        A fully qualified jsDelivr URL.
    """
    return _CDN_URL_TEMPLATE.format(version=get_cdn_version(), filename=filename)


def bundled_cdn_url(filename: str) -> str:
    """Return the CDN URL pinned to the version shipped in this wheel.

    For code that must emit a CDN reference without making a request.
    The bundled version came from the registry at release time, so it is
    a real published version and the URL resolves — while being
    immutable, and therefore free of the seven-day cache lifetime that
    ``@latest`` carries.

    Honours an explicit pin first, then a version an already-completed
    lookup established, so these tags stay on the same version anything
    else in the page loads.  Falls back to :data:`LATEST_TAG` only when
    none of those is usable, where there is no better answer available
    offline.

    Parameters
    ----------
    filename : str
        Asset name under the package's ``dist/`` directory.

    Returns
    -------
    str
        A jsDelivr URL at the bundled version, or at ``latest`` when that
        version is unknown.
    """
    # A pin first, then a version an earlier lookup already established,
    # then the bundled one -- see `_offline_version`, which is the same
    # order `get_cdn_version` falls back to on an event loop, written once
    # so the two cannot answer differently. When they did, a pinned
    # session emitted the *bundled* version here while every iframe
    # emitted the pinned one, and one page loaded two builds of maidr.js.
    #
    # A LATEST_TAG pin lands there too and yields the ``@latest`` URL,
    # which is what that pin asks for and what the render paths emit.
    return _CDN_URL_TEMPLATE.format(version=_offline_version(), filename=filename)


def maidr_js_cdn_url() -> str:
    """Return the CDN URL for ``maidr.js`` at the resolved version.

    Returns
    -------
    str
        A fully qualified jsDelivr URL.
    """
    return cdn_url(MAIDR_JS_FILENAME)


def _warn_placeholder_css(name: str, instead: str) -> None:
    """
    Announce that a ``maidr.css`` accessor is going away.

    ``FutureWarning`` rather than ``DeprecationWarning``, which is the more
    usual category for an API removal. Python's own guidance splits them by
    audience: ``DeprecationWarning`` is for warnings aimed at other library
    authors, ``FutureWarning`` for those aimed at end users of applications
    written in Python. Someone calling this is building a dashboard or a
    report, not extending py-maidr.

    The practical half matters more. ``DeprecationWarning`` is silenced by
    default outside ``__main__``, so a caller inside a Shiny app or an
    imported module would never see it and would meet the removal as a
    breakage instead of a warning -- which is the one thing a deprecation
    cycle exists to prevent.

    Parameters
    ----------
    name : str
        The function being called, spelled as a path that actually
        imports, so the message names the caller's own call rather than
        this helper.  Fully qualified rather than assumed: only one of
        these two is re-exported from the top-level package, so a fixed
        ``maidr.`` prefix would name a path that raises
        :class:`AttributeError` for the other.
    instead : str
        What to call in its place, in the same form the caller wanted.  The
        two accessors return different things -- a local :class:`Path` and a
        remote URL -- so a single suggestion would hand one of them the
        wrong type, which is the opposite of what a deprecation message is
        for.
    """
    warnings.warn(
        f"{name}() is deprecated and will be removed in the next major "
        "release, along with the bundled maidr.css it resolves. That file has "
        "carried no rules since maidr 3.75.1 and nothing in py-maidr links "
        f"it. Use {instead} for the stylesheet that does carry rules, or link "
        "no stylesheet at all -- MAIDR styles its interface at runtime.",
        FutureWarning,
        stacklevel=3,
    )


def maidr_css_cdn_url() -> str:
    """Return the CDN URL for ``maidr.css`` at the resolved version.

    .. deprecated::
        Linking this buys nothing and will be removed, along with
        ``maidr.css`` itself, in the next major release.  If what you
        wanted was the stylesheet that carries rules, and you want it from
        the CDN as this function returns it, call
        ``cdn_url(MAIDR_MATH_CSS_FILENAME)`` -- both from this module, which
        is also the only place this function itself is importable from.
        :func:`bundled_math_css_path` is the local-file counterpart, and is
        re-exported as ``maidr.bundled_math_css_path``.  Or link nothing at
        all -- MAIDR styles its interface at runtime.

    Nothing in ``maidr/`` emits this any more.  From maidr 3.75.1 the file
    it points at is a placeholder with no rules in it, published only so
    that ``<link>`` tags written before the split keep resolving; linking
    it costs a request and buys nothing.  Kept for callers outside this
    package that already build their own HTML around it.

    Returns
    -------
    str
        A fully qualified jsDelivr URL.

    Warns
    -----
    FutureWarning
        Always.  See :func:`_warn_placeholder_css` for why this category.
    """
    _warn_placeholder_css(
        "maidr.util.dependencies.maidr_css_cdn_url",
        "cdn_url(MAIDR_MATH_CSS_FILENAME) from maidr.util.dependencies",
    )
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
        if _is_valid_version(bundled) and bundled != _UNKNOWN_VERSION:
            return bundled
        # Asking for ``bundled`` is a request to serve what is installed,
        # which implies staying local.  Falling through to a network
        # lookup would betray that intent for someone who chose it to
        # avoid egress, so degrade to ``@latest`` — still a working URL,
        # still no request.
        _warn_once(
            f"{BUNDLED_TAG}:{bundled}",
            "maidr: a %r CDN version pin was requested but the bundled "
            "VERSION is %r; falling back to the %r dist-tag without "
            "resolving. Reinstall py-maidr to repair the bundle.",
            BUNDLED_TAG,
            bundled,
            LATEST_TAG,
        )
        return LATEST_TAG
    # Accept a leading ``v`` (``v3.74.0``) since that is how the version
    # is written in git tags and release notes.
    candidate = candidate[1:] if candidate.startswith(("v", "V")) else candidate
    if _is_valid_version(candidate):
        _warn_if_pin_predates_stylesheet_split(candidate)
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


def _warn_if_pin_predates_stylesheet_split(version: str) -> None:
    """Warn once when a pin names a maidr from before the KaTeX split.

    py-maidr emits no stylesheet link, because from
    :data:`_STYLESHEET_SPLIT_VERSION` the published ``maidr.css`` is a
    placeholder and ``maidr.js`` fetches the maths stylesheet itself.  An
    older version has neither that runtime fetch nor rules anywhere else,
    so LaTeX in AI chat responses renders unstyled.

    The failure is narrow and silent — no other part of the interface
    changes, and a page whose chat is never opened looks perfectly fine —
    which is exactly why pinning backwards deserves a sentence rather
    than a discovery.

    Parameters
    ----------
    version : str
        A pin that has already passed :func:`_is_valid_version`.
    """
    key = _version_key(version)
    split_key = _version_key(_STYLESHEET_SPLIT_VERSION)
    if key is None or split_key is None or key >= split_key:
        return
    _warn_once(
        f"pre-split-pin:{version}",
        "maidr: CDN version pin %r predates maidr %s, where KaTeX moved out "
        "of maidr.css into maidr-math.css. py-maidr links no stylesheet, so "
        "LaTeX in AI chat responses will render unstyled at that version; "
        "everything else is unaffected. Pin %s or newer to style it.",
        version,
        _STYLESHEET_SPLIT_VERSION,
        _STYLESHEET_SPLIT_VERSION,
    )


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
    # Claim the key under the lock.  Individual set operations being
    # atomic would not be enough: the sequence below is compound, so two
    # threads could both pass the size check and one's ``clear()`` would
    # drop the key the other just added.  Leaning on the GIL for that
    # would also stop holding under free-threaded builds (PEP 703).  The
    # membership test above keeps the lock off the common path.
    with _warned_keys_lock:
        if key in _warned_keys:
            return
        if len(_warned_keys) >= _MAX_WARNED_KEYS:
            # Start over rather than grow without bound.  A process
            # churning through this many distinct bad pins will see the
            # occasional repeat, which is a fair trade for fixed memory.
            _warned_keys.clear()
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

    Values above :data:`_MAX_CDN_TIMEOUT` are clamped, with a warning so
    the clamp is visible rather than silent.  Honouring an arbitrarily
    large value would respect the letter of the configuration at the cost
    of a render that appears to hang: ``MAIDR_CDN_TIMEOUT=3000`` meant as
    milliseconds would block for fifty minutes.  Nothing legitimate needs
    longer than the cap to fetch a sub-kilobyte JSON document, and a
    lookup that slow degrades to the ``@latest`` URL anyway.

    Values below :data:`_MIN_CDN_TIMEOUT` are clamped for the mirror-image
    reason, and it is the more damaging mistake: a budget like ``0.05``,
    set by someone who wanted the lookup to be quick, is positive and so
    passes every other guard, yet no round trip can finish inside it.
    Every attempt times out, the failure is cached once, and every render
    for the rest of the process quietly emits ``@latest`` — the exact bug
    this module exists to fix, arrived at through configuration rather
    than through code.  A render that waits a tenth of a second and then
    gives up is the better failure.
    """
    raw = os.environ.get(CDN_TIMEOUT_ENV_VAR)
    if raw is None:
        return _DEFAULT_CDN_TIMEOUT
    try:
        timeout = float(raw)
    except ValueError:
        _warn_once(
            f"timeout-nan:{raw}",
            "maidr: ignoring non-numeric %s=%r; using the %ss default.",
            CDN_TIMEOUT_ENV_VAR,
            raw[:_MAX_WARNED_KEY_LEN],
            _DEFAULT_CDN_TIMEOUT,
        )
        return _DEFAULT_CDN_TIMEOUT
    if not math.isfinite(timeout):
        # ``float("nan")`` parses, and NaN compares False against both
        # the floor and the ceiling below, so it would sail through every
        # guard and reach ``urlopen`` — which raises, gets swallowed by
        # the broad handler there, and silently disables resolution with
        # nothing logged.  ``inf`` would hang instead of being clamped.
        _warn_once(
            f"timeout-nonfinite:{raw}",
            "maidr: %s=%s is not a finite number; using the %ss default.",
            CDN_TIMEOUT_ENV_VAR,
            raw[:_MAX_WARNED_KEY_LEN],
            _DEFAULT_CDN_TIMEOUT,
        )
        return _DEFAULT_CDN_TIMEOUT
    if timeout <= 0:
        # Say so rather than silently substituting the default: `0` most
        # plausibly means "don't look up", and the user should learn that
        # it doesn't rather than wonder where the wait came from.
        _warn_once(
            f"timeout-nonpositive:{raw}",
            "maidr: %s=%s is not a valid budget, so the %ss default applies. "
            "To skip the lookup entirely, set %s=%s.",
            CDN_TIMEOUT_ENV_VAR,
            raw[:_MAX_WARNED_KEY_LEN],
            _DEFAULT_CDN_TIMEOUT,
            CDN_VERSION_ENV_VAR,
            LATEST_TAG,
        )
        return _DEFAULT_CDN_TIMEOUT
    if timeout < _MIN_CDN_TIMEOUT:
        _warn_once(
            f"timeout-tiny:{raw}",
            "maidr: %s=%s is below the %ss floor and was clamped. The value "
            "is in seconds; a budget that small times out on every attempt "
            "and silently reinstates the '%s' dist-tag.",
            CDN_TIMEOUT_ENV_VAR,
            raw[:_MAX_WARNED_KEY_LEN],
            _MIN_CDN_TIMEOUT,
            LATEST_TAG,
        )
        return _MIN_CDN_TIMEOUT
    if timeout > _MAX_CDN_TIMEOUT:
        _warn_once(
            f"timeout:{raw}",
            "maidr: %s=%s exceeds the %ss cap and was clamped. The value is "
            "in seconds; a lookup needing longer would fall back to the "
            "'%s' dist-tag regardless.",
            CDN_TIMEOUT_ENV_VAR,
            raw[:_MAX_WARNED_KEY_LEN],
            _MAX_CDN_TIMEOUT,
            LATEST_TAG,
        )
        return _MAX_CDN_TIMEOUT
    return timeout


def _resolve_latest_version() -> str | None:
    """Return the cached ``latest`` version, resolving it on first use.

    Returns
    -------
    str or None
        The concrete version behind the ``latest`` dist-tag, or ``None``
        when it could not be resolved (offline, blocked, or malformed
        response).

    Notes
    -----
    A :func:`reset_cdn_version_cache` call that lands while this lookup is
    in flight wins: the result is returned to *this* caller but not
    cached, so the next render re-resolves rather than seeing the answer
    the reset asked to discard.
    """
    global _resolved_cdn_version, _resolution_attempted
    attempted, value = _resolution_state()
    if attempted:
        return value

    with _fetch_lock:
        # Re-check: another fetcher may have finished while we queued.
        attempted, value = _resolution_state()
        if attempted:
            return value

        with _resolution_lock:
            generation = _resolution_generation

        # Deliberately outside ``_resolution_lock``.  The offline paths
        # read that lock, so holding it here would make a stalled lookup
        # block a render that promised to make no request at all.
        try:
            result = _fetch_latest_version(_cdn_timeout())
        except Exception:
            # ``_fetch_latest_version`` is written not to raise, but if it
            # ever does, record the attempt so the failure is cached
            # rather than retried on every later render.
            #
            # Deliberately ``Exception`` and not ``BaseException``: a
            # ``KeyboardInterrupt`` landing mid-lookup is the user
            # interrupting, not a resolver that cannot be reached, and
            # caching it would poison resolution for the life of the
            # process -- every later render would silently emit
            # ``@latest``, which is the bug this module exists to fix.
            # Letting it propagate un-cached means the next render simply
            # tries again.
            with _resolution_lock:
                if generation == _resolution_generation:
                    _resolution_attempted = True
            raise

        with _resolution_lock:
            # Drop the result if a reset intervened -- it asked for this
            # answer to be discarded, and publishing it now would silently
            # undo the reset.
            if generation == _resolution_generation:
                _resolved_cdn_version = result
                _resolution_attempted = True
        return result


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
    overrun the budget by a small multiple.  Name resolution is a further
    gap: ``getaddrinfo`` is not reliably covered by a socket timeout on
    every platform, so a broken resolver can stall past the budget before
    any of those steps begins.

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
        except Exception:
            # Deliberately broad.  The obvious failures are OSError,
            # HTTPException, ValueError and UnicodeDecodeError, but the
            # contract above is that a lookup failure degrades to the
            # ``@latest`` URL rather than breaking rendering — and an
            # exception this list did not anticipate would break it.
            # Sandboxes make that concrete: pytest-socket raises
            # SocketBlockedError, which derives from Exception, not
            # OSError, and would otherwise propagate out of render().
            _logger.debug("maidr: CDN version lookup failed at %s", url, exc_info=True)
            continue

        candidate = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(candidate, str) and _is_valid_version(candidate.strip()):
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
    rf"^(?P<major>{_NUMERIC_ID})\.(?P<minor>{_NUMERIC_ID})\.(?P<patch>{_NUMERIC_ID})"
    rf"(?P<prerelease>-{_PRERELEASE})?"
    rf"(?:\+{_BUILD})?\Z"
)

# Which severities have already spoken.  One shared flag would let the
# quiet ``auto`` path -- the default, so almost always first -- consume the
# single shot and leave the ``use_cdn=False`` warning permanently
# unreachable, which is precisely the audience it exists for.
_bundle_warned: set[bool] = set()
_bundle_warning_lock = threading.Lock()


class MaidrBundleStaleWarning(UserWarning):
    """Raised as a warning when the bundled ``maidr.js`` has fallen behind.

    A dedicated category so consumers running ``-W error`` or pytest's
    ``filterwarnings = ["error"]`` can silence *this* advisory without
    having to silence every ``UserWarning`` the stack emits.

    Examples
    --------
    >>> import warnings
    >>> warnings.filterwarnings(  # doctest: +SKIP
    ...     "ignore", category=maidr.MaidrBundleStaleWarning
    ... )
    """


class BundleStatus(NamedTuple):
    """How the bundled ``maidr.js`` compares to the published release.

    Attributes
    ----------
    bundled : str
        Version of the copy shipped inside this wheel.
    published : str or None
        The version npm has published, or ``None`` when that is not
        known.  Never what a pin says to serve — see
        :func:`_published_version`.
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
        Whether to look the published version up over the network when it
        is not already cached.  Pass ``False`` on offline code paths: the
        comparison then uses only an earlier lookup, and reports
        ``published=None`` when none has happened.

        Note that ``published`` always means "what npm published", never
        "what we will serve" — a pin from :func:`set_cdn_version` or
        ``MAIDR_CDN_VERSION`` does not stand in for it, so pinning
        neither fakes staleness nor conceals it.

    Returns
    -------
    BundleStatus
        The two versions and how far apart they are.  Unparseable or
        unknown versions yield ``is_behind=is_stale=False`` rather than a
        guess.

    Raises
    ------
    Exception
        Only with ``resolve=True``, and only if the lookup itself fails
        in a way it is written not to: unreachable endpoints, timeouts
        and malformed responses are all handled internally and reported
        as ``published=None``.  The re-raise exists so a genuine bug in
        the resolver surfaces instead of being cached as "no answer", so
        callers that must not fail -- a scheduled freshness check, say --
        should still catch it.

    Examples
    --------
    >>> bundle_status()  # doctest: +SKIP
    BundleStatus(bundled='3.73.0', published='3.74.0', is_behind=True, is_stale=False)

    The versions above are illustrative, not a fixture: ``published`` is
    looked up at call time, so real output tracks whatever is current.
    """
    bundled = maidr_js_version()
    published = _published_version(resolve=resolve)

    bundled_key = _version_key(bundled) if bundled != _UNKNOWN_VERSION else None
    published_key = _version_key(published) if published else None
    if bundled_key is None or published_key is None:
        return BundleStatus(bundled, published, is_behind=False, is_stale=False)

    is_behind = bundled_key < published_key
    (bundled_major, bundled_minor, _), _, _ = bundled_key
    (published_major, published_minor, _), _, _ = published_key
    is_stale = is_behind and (
        published_major > bundled_major
        or published_minor - bundled_minor >= STALE_MINOR_GAP
    )
    return BundleStatus(bundled, published, is_behind, is_stale)


def warn_bundle_unreadable() -> None:
    """Warn that ``use_cdn=False`` had to reach for the CDN anyway.

    Lives here rather than in :mod:`maidr.api` so the dedup bookkeeping
    it relies on stays inside the module that owns it, and so every
    statement about the bundled assets is made from one place.

    Notes
    -----
    Uses ``logging`` where :func:`warn_if_bundle_is_stale` uses
    ``warnings.warn``, which is deliberate rather than an oversight.  This
    one can fire from ``init_notebook()`` during ``import maidr``, where a
    ``UserWarning`` is awkward to attribute and impossible to filter
    before it happens; the staleness warning fires from an explicit render
    call, where a filterable warning category is the better fit.
    """
    _warn_once(
        "missing-bundle",
        "maidr: use_cdn=False was requested but the bundled maidr.js/css "
        "could not be read, so the notebook will load them from the CDN. "
        "Reinstall py-maidr to repair the bundle for offline use.",
    )


def warn_if_bundle_is_stale(*, bundle_is_primary: bool = True) -> None:
    """Warn once per process when the bundled fallback has drifted badly.

    Intended for the render paths where the bundled copy can actually be
    executed — ``use_cdn=False`` (it is the only source) and
    ``use_cdn="auto"`` (it is the offline fallback).  Never issues a
    network request of its own: it compares against the published version
    only when that is already known, so an offline render stays offline
    and simply says nothing.

    That leaves a deliberate blind spot, and it is wider than it looks.
    Only a real lookup arms this warning — and a pin *prevents* one,
    because :func:`get_cdn_version` short-circuits on a pin before
    resolution runs.  So a process pinned to any version, or using only
    ``use_cdn=False``, stays silent however old its bundle is.  That is
    precisely the air-gapped audience the warning is for.
    Reaching them automatically would require the network request that
    ``use_cdn=False`` exists to avoid, so this is a partial mitigation by
    construction: :func:`bundle_status` (which does resolve) is the
    explicit check for those users, and a release-time CI comparison is
    the real answer.

    Parameters
    ----------
    bundle_is_primary : bool, default True
        Whether the bundled copy is what will actually run.  ``True`` for
        ``use_cdn=False``, where it is the only source, and the drift is
        raised as a :class:`MaidrBundleStaleWarning`.  ``False`` for
        ``use_cdn="auto"``, where the CDN copy normally loads instead and
        the drift goes to the logger rather than to a warning that could
        fail a suite running ``-W error`` over code that never executed.

    Notes
    -----
    Silenced by ``MAIDR_BUNDLE_STALE_WARNING=0``.

    Emitted as a ``UserWarning``, so a caller running under ``-W error``
    (or pytest's ``filterwarnings = ["error"]``) sees ``render()`` raise
    rather than warn.  That is a real upgrade hazard for anyone treating
    warnings as errors, which is why it is called out in the user guide
    as well as here.

    Fires at most once per process *per severity*, and neither
    :func:`set_cdn_version` nor :func:`reset_cdn_version_cache` re-arms
    it — so re-pinning in a REPL to watch it again will not produce a
    second report.

    ``stacklevel=2`` deliberately points at maidr's own render machinery
    rather than the caller's ``render()`` / ``save_html()`` line.  The
    depth from user code differs per entry point, so no fixed level
    reaches it, and the warning is about the *installed package* rather
    than about how it was called — the message stands alone without a
    call site.
    """
    if bundle_is_primary in _bundle_warned or not _bundle_warning_enabled():
        return

    status = bundle_status(resolve=False)
    if not status.is_stale:
        return

    # Claim this severity's one report under a lock so concurrent first
    # renders emit it once rather than racing between the check above and
    # the set.  Latched per severity: a quiet ``auto`` report must not
    # suppress a later ``use_cdn=False`` warning, where the bundle really
    # is what runs.
    with _bundle_warning_lock:
        if bundle_is_primary in _bundle_warned:
            return
        _bundle_warned.add(bundle_is_primary)

    message = (
        f"maidr: the bundled copy of maidr.js is {status.bundled}, but the "
        f"current published release is {status.published}. The bundle is "
        f"what renders when the CDN is disabled (use_cdn=False) or "
        f"unreachable (use_cdn='auto'), so those plots run the older "
        f"build. Upgrade py-maidr to pick up a refreshed bundle. Set "
        f"{BUNDLE_WARNING_ENV_VAR}=0 to silence this warning."
    )
    if bundle_is_primary:
        warnings.warn(message, MaidrBundleStaleWarning, stacklevel=2)
    else:
        # Under ``use_cdn="auto"`` the CDN copy normally loads and the
        # bundle never executes, so a warning here is about code that did
        # not run -- and under ``-W error`` it would redden a downstream
        # suite over it.  Report it, but to the logger.
        _logger.warning("%s", message)


def _bundle_warning_enabled() -> bool:
    """Return whether the staleness warning is enabled (it is by default)."""
    raw = os.environ.get(BUNDLE_WARNING_ENV_VAR)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


# ---------------------------------------------------------------------------
# Bundled-copy capability
# ---------------------------------------------------------------------------

#: A quoted lower-snake identifier, which is how the bundle spells a trace
#: type.  All three quote characters, because the minifier picks whichever
#: is shortest for the surrounding context -- the 4.1.0 bundle uses
#: backticks throughout, and a check written for double quotes alone would
#: have reported every type missing.
_BUNDLE_TOKEN_RE = re.compile(
    r"(?P<quote>[`\"'])(?P<token>[a-z][a-z0-9_]{1,39})(?P=quote)"
)

#: Parsed once; the bundle does not change under a running process.
_bundle_tokens: frozenset[str] | None = None
_bundle_token_lock = threading.Lock()

#: Which (severity, trace type) pairs have already been reported, so a
#: chart rendered in a loop says it once per type rather than per render.
#: Its own lock: it shares no invariant with the token cache, and the
#: staleness warning next door already keeps these two concerns apart.
_bundle_trace_warned: set[tuple[bool, str]] = set()
_bundle_trace_lock = threading.Lock()


class MaidrBundleTraceWarning(UserWarning):
    """Raised when the bundled ``maidr.js`` cannot draw an emitted layer.

    Distinct from :class:`MaidrBundleStaleWarning`, which is about age.
    This one is about capability, and it is the question a reader actually
    has: a bundle five minors behind may render everything, and one minor
    behind may render none of a newly added type.

    Re-exported as ``maidr.MaidrBundleTraceWarning``, so a consumer running
    under ``-W error`` can silence this advisory alone::

        warnings.filterwarnings("ignore", category=maidr.MaidrBundleTraceWarning)
    """


def bundle_trace_types() -> frozenset[str]:
    """Return the trace types the bundled ``maidr.js`` mentions.

    Read straight out of the shipped bundle rather than from a table kept
    in step by hand.  A table costs one line per new plot type and forgetting
    that line is silent in exactly the way this exists to prevent; the
    bundle already knows the answer, because its factory switches on these
    strings.

    Returns
    -------
    frozenset of str
        Every quoted lower-snake identifier in the bundle.  Empty when the
        bundle cannot be read, which callers must treat as "cannot tell"
        rather than as "renders nothing".

    Notes
    -----
    This is a *mention* rather than a proof: the identifiers are collected
    without regard to where they appear, so a string that coincides with a
    trace type in unrelated code counts. That biases the check towards
    silence, which is the right direction — a false "your bundle is fine"
    leaves the reader where they already were, while a false "your bundle
    cannot draw this" sends them chasing a version they do not need.

    Cached for the life of the process; ``bundle_trace_types.cache_clear``
    is not offered because the bundle is installed, not configured.
    """
    global _bundle_tokens
    if _bundle_tokens is not None:
        return _bundle_tokens

    with _bundle_token_lock:
        if _bundle_tokens is not None:
            return _bundle_tokens
        try:
            source = bundled_js_path().read_text(encoding="utf-8", errors="ignore")
        except (FileNotFoundError, ModuleNotFoundError, OSError):
            _logger.debug("maidr: bundled maidr.js unreadable; capability unknown")
            _bundle_tokens = frozenset()
        else:
            _bundle_tokens = frozenset(
                match.group("token") for match in _BUNDLE_TOKEN_RE.finditer(source)
            )
        return _bundle_tokens


def warn_if_bundle_cannot_render(
    trace_types: Iterable[str], *, bundle_is_primary: bool = True
) -> None:
    """Warn when the bundled copy has no builder for a layer being emitted.

    ``STALE_MINOR_GAP`` answers "how old is this bundle?" The question a
    user needs answered is "can this bundle draw what I am about to hand
    it?", and version distance is a poor proxy for it (#358). This asks
    the bundle directly, so it needs no network and reaches the
    ``use_cdn=False`` audience that :func:`warn_if_bundle_is_stale`
    documents itself as unable to reach.

    Parameters
    ----------
    trace_types : iterable of str
        The layer types this render is about to emit.
    bundle_is_primary : bool, default True
        Whether the bundled copy is what will actually run. ``True`` for
        ``use_cdn=False``, where it is the only source and the reader gets
        ``Invalid trace type`` and a blank figure; ``False`` for
        ``use_cdn="auto"``, where the CDN copy normally loads instead and
        this goes to the logger rather than to a warning that could fail a
        suite running ``-W error`` over code that never executed.

    Notes
    -----
    Silenced by ``MAIDR_BUNDLE_STALE_WARNING=0``, the same switch as the
    staleness warning: a user turning bundle chatter off wants it off.

    Reported once per process per trace type per severity, so a chart
    rendered in a loop says it once and a second unsupported type is not
    swallowed by the first.
    """
    if not _bundle_warning_enabled():
        return

    known = bundle_trace_types()
    if not known:
        # Unreadable bundle. Saying "renders nothing" here would warn about
        # every layer of every chart on the strength of a missing file.
        return

    named = {
        name
        for name in (_trace_type_name(entry) for entry in trace_types)
        if name is not None
    }
    missing = sorted(named - known)
    if not missing:
        return

    with _bundle_trace_lock:
        fresh = [
            name
            for name in missing
            if (bundle_is_primary, name) not in _bundle_trace_warned
        ]
        for name in fresh:
            _bundle_trace_warned.add((bundle_is_primary, name))
    if not fresh:
        return

    listed = ", ".join(fresh)
    message = (
        f"maidr: the bundled copy of maidr.js is {maidr_js_version()}, which "
        f"has no renderer for {listed}. The bundle is what renders when the "
        f"CDN is disabled (use_cdn=False) or unreachable (use_cdn='auto'), "
        f"and a layer it cannot build is dropped rather than drawn, so those "
        f"plots come out blank. Upgrade py-maidr to pick up a refreshed "
        f"bundle, or render with use_cdn=True. Set "
        f"{BUNDLE_WARNING_ENV_VAR}=0 to silence this warning."
    )
    if bundle_is_primary:
        warnings.warn(message, MaidrBundleTraceWarning, stacklevel=2)
    else:
        _logger.warning("%s", message)


def schema_trace_types(schema: object) -> set[str]:
    """Collect every layer type in an emitted MAIDR schema.

    Reads the schema rather than the ``PlotType`` enum, because the two do
    not agree: a ``seaborn.countplot`` is classified ``PlotType.COUNT`` and
    emitted as ``bar``, so a check driven by the enum would ask the bundle
    about a type no schema ever carries.

    Parameters
    ----------
    schema : object
        A flattened MAIDR schema, or any nested structure of dicts and
        lists containing one.

    Returns
    -------
    set of str
        The distinct ``type`` values of every layer found.
    """
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            name = _trace_type_name(node.get("type"))
            if name is not None:
                found.add(name)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(schema)
    return found


def _trace_type_name(kind: object) -> str | None:
    """Return the string a layer's ``type`` reaches the JSON as.

    A schema still in memory holds a :class:`~maidr.core.enum.PlotType`
    there, and ``PlotType`` subclasses :class:`str` -- so it compares and
    hashes as its value while ``str()`` of it is ``"PlotType.BAR"``. Asking
    the bundle about that name reports every layer of every chart missing,
    which is what the first draft of this did.

    Parameters
    ----------
    kind : object
        A layer's ``type``, as either the enum member or the plain string.

    Returns
    -------
    str or None
        The trace-type string, or None when the node carries no usable one.
    """
    value = getattr(kind, "value", kind)
    return value if isinstance(value, str) else None


def _prerelease_key(prerelease: str) -> tuple[tuple[int, int, str], ...]:
    """Return a sortable key for a semver prerelease string.

    Follows semver's precedence rules for the dot-separated identifiers:
    numeric ones compare numerically and rank below alphanumeric ones,
    alphanumeric ones compare lexically, and a shorter run of identifiers
    sorts below an otherwise-equal longer one — which plain tuple
    comparison gives for free.

    Parameters
    ----------
    prerelease : str
        The prerelease body, without its leading ``-``.

    Returns
    -------
    tuple
        One ``(is_alphanumeric, numeric_value, text_value)`` triple per
        identifier.
    """
    return tuple(
        (0, int(ident), "") if ident.isdigit() else (1, 0, ident)
        for ident in prerelease.split(".")
    )


def _version_key(
    version: str,
) -> tuple[tuple[int, int, int], int, tuple[tuple[int, int, str], ...]] | None:
    """Return a sortable key for a semver string.

    Parameters
    ----------
    version : str
        A version such as ``"3.74.0"`` or ``"3.74.0-rc.1"``.

    Returns
    -------
    tuple or None
        ``((major, minor, patch), rank, prerelease)`` where ``rank`` is
        ``0`` for a prerelease and ``1`` for a final release, so
        ``3.74.0-rc.1`` sorts before ``3.74.0``.  The third element
        orders two prereleases of the same release against each other
        (``rc.1`` before ``rc.2``); it is empty for a final release,
        where ``rank`` has already decided the comparison.  ``None``
        when the string is not a version we can compare.

    Notes
    -----
    Build metadata (``+build.5``) is deliberately ignored, which is what
    semver requires: it carries no precedence.
    """
    candidate = version.strip()
    if len(candidate) > _MAX_VERSION_LEN:
        return None
    match = _RELEASE_RE.match(candidate)
    if match is None:
        return None
    try:
        release = (int(match["major"]), int(match["minor"]), int(match["patch"]))
        prerelease = match["prerelease"]
        if not prerelease:
            return release, 1, ()
        # Strip the leading ``-`` the pattern captured with the body.
        return release, 0, _prerelease_key(prerelease[1:])
    except ValueError:
        # Defence in depth behind the length cap above.  A comparison is
        # advisory; it must never be the thing that breaks a render.
        _logger.debug("maidr: unparseable version %r", candidate[:80])
        return None


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

    The cache is part of the contract: this will not observe a ``VERSION``
    file edited at runtime, and exposes ``.cache_clear()`` for the tests
    that need to.
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
    """Return the filesystem path to the bundled MAIDR stylesheet.

    .. deprecated::
        The file this resolves has no rules in it, and both it and this
        function will be removed in the next major release.  Use
        :func:`bundled_math_css_path` if what you wanted was the
        stylesheet that carries rules, or link nothing at all -- MAIDR
        styles its interface at runtime.

    Kept for callers that predate maidr 3.75.1.  Since that release the
    file is a placeholder with no rules in it, and nothing in ``maidr/``
    links it; :func:`bundled_math_css_path` is the stylesheet that
    carries content.

    Warns
    -----
    FutureWarning
        Always.  See :func:`_warn_placeholder_css` for why this category.
    """
    _warn_placeholder_css("maidr.bundled_css_path", "maidr.bundled_math_css_path()")
    return _bundled_asset_path(MAIDR_CSS_FILENAME)


def bundled_math_css_path() -> Path:
    """Return the filesystem path to the bundled KaTeX stylesheet.

    Returns
    -------
    Path
        On-disk path to ``maidr-math.css``.

    Raises
    ------
    FileNotFoundError
        If the wheel was built without it, which means the bundle
        predates maidr 3.75.1.
    """
    return _bundled_asset_path(MAIDR_MATH_CSS_FILENAME)


def read_bundled_js() -> str:
    """Return the contents of the bundled ``maidr.js`` as a string."""
    return bundled_js_path().read_text(encoding="utf-8")


def read_bundled_math_css() -> str:
    """Return the contents of the bundled ``maidr-math.css`` as a string."""
    return bundled_math_css_path().read_text(encoding="utf-8")


def maidr_html_dependency():
    """Return an :class:`htmltools.HTMLDependency` for the bundled assets.

    The dependency points at the ``maidr/static/`` directory inside the
    installed package.  When consumed by
    :meth:`htmltools.HTMLDocument.save_html`, ``htmltools`` copies the
    assets into the HTML file's ``lib_dir`` and rewrites the ``<script>``
    tag to use a relative path, producing a self-contained output
    directory that works without network access.

    No stylesheet is linked.  maidr styles its interface at runtime, and
    since 3.75.1 the only stylesheet with rules in it is
    ``maidr-math.css``, which ``maidr.js`` fetches for itself from
    whichever directory it was loaded from.  ``all_files=True`` is what
    puts it in that directory: it copies every file under
    ``maidr/static/`` rather than only the ones named in a tag, so the
    runtime's fetch resolves against ``lib/maidr-<version>/`` and finds
    it there.

    Returns
    -------
    htmltools.HTMLDependency
        Dependency describing the bundled assets.
    """
    # Imported lazily so this module stays importable even in contexts
    # where ``htmltools`` may not be fully initialised.
    from htmltools import HTMLDependency

    return HTMLDependency(
        name="maidr",
        version=maidr_js_version(),
        source={"package": _STATIC_PACKAGE, "subdir": _STATIC_SUBDIR},
        script=[{"src": MAIDR_JS_FILENAME}],
        stylesheet=[],
        all_files=True,
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
