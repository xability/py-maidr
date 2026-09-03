"""Resolving which published ``maidr.js`` a page should load.

Split out of :mod:`maidr.util.dependencies` (#293), which keeps the other
half: reaching the copy bundled inside this package. The direction is
one-way -- this module imports ``dependencies`` for the asset names and
the bundled version, and nothing there imports back.

Reads that tests patch go through the module object rather than a
from-import (``_deps._deps.maidr_js_version()``), because a from-import binds
at import time and would silently stop receiving
``monkeypatch.setattr(dependencies, ...)``.

The same hazard is why the back-compat shim in ``dependencies`` cannot
cover this module's *state*. It forwards attribute **reads**, so
``dependencies.get_cdn_version`` still resolves; it cannot forward a
**write**, so ``monkeypatch.setattr(dependencies, "urlopen", ...)`` would
set an attribute nothing here reads. Tests patch ``cdn`` directly for
that reason, and the shim's docstring says so.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
import warnings
from typing import NamedTuple
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from maidr.util import dependencies as _deps
from maidr.util.dependencies import (
    MAIDR_CSS_FILENAME,
    MAIDR_JS_FILENAME,
    # Unused here, re-exported so `maidr_css_cdn_url`'s deprecation can tell
    # people to call `cdn_url(MAIDR_MATH_CSS_FILENAME)` *from this module*
    # and have both names resolve from it. `test_deprecation_names_only_
    # importable_symbols` fails if advice names a symbol the reader cannot
    # import where they were sent.
    MAIDR_MATH_CSS_FILENAME,  # noqa: F401
    _UNKNOWN_VERSION,
    _is_valid_version,
    _warn_placeholder_css,
    _version_key,
)
from maidr.util.warn import _MAX_WARNED_KEY_LEN, warn_once

_logger = logging.getLogger(__name__)


#: The release that made the split above true.
#:
#: Before it, ``maidr.css`` carried KaTeX and had to be linked.  py-maidr
#: links no stylesheet at all now, so pinning the CDN to anything older
#: leaves LaTeX in AI chat responses unstyled -- everything else is
#: unaffected, since the interface has been styled at runtime throughout.
#: :func:`_warn_if_pin_predates_stylesheet_split` says so once rather than
#: letting it be discovered.
_STYLESHEET_SPLIT_VERSION = "3.75.1"


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


class ResolverOutcome(NamedTuple):
    """Why the last ``latest`` lookup ended the way it did.

    :func:`_fetch_latest_version` collapses every failure into ``None``,
    which is the right answer for a render -- there is nothing a chart can
    do about it either way -- but it loses the one distinction a monitor
    needs.  Two endpoints failing to answer is the network; two endpoints
    answering with something unusable is *this code* being wrong about
    their shape, and only the second should wake anyone up.

    Kept separate from :class:`BundleStatus` rather than folded into it,
    so the render path's answer to "how does my bundle compare?" stays the
    two versions and the two flags it already is.

    Attributes
    ----------
    resolved : str or None
        The version the lookup settled on, if any.
    unreachable : tuple of str
        Endpoints that never answered: a timeout, a refused connection, a
        name that would not resolve, a blocked socket.  Says nothing about
        whether the resolver code is right, because nothing was read.
    answered_badly : tuple of str
        Endpoints that answered, in a way this code could not use: an HTTP
        error status, a body that would not decode or parse, a payload
        without the key, or a value that is not a version.  This is the
        one worth failing a scheduled check over -- an API that changed
        shape looks exactly like this and looks like nothing else.
    """

    resolved: str | None
    unreachable: tuple[str, ...]
    answered_badly: tuple[str, ...]


def _unresolved_cdn_url(filename: str) -> str:
    """Format the ``@latest`` URL for ``filename``.  See public wrapper."""
    return _CDN_URL_TEMPLATE.format(version=LATEST_TAG, filename=filename)


# Deliberately not guarded by ``_resolution_lock`` below: this is a lone
# reference assignment, written only by an explicit
# :func:`set_cdn_version` call.  The lock exists to stop concurrent
# *lookups*, which are a compound read-modify-write, not to protect this.
#
# Unlike the compound update in :func:`maidr.util.warn.warn_once`, the
# reasoning here does not depend on the GIL and so survives free-threaded
# builds (PEP 703): storing a single object reference stays indivisible
# there, so a reader sees either the old value or the new one, never a
# torn write.
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


# The last lookup's verdict, for :func:`resolver_outcome`.  A single
# rebound reference like the globals above, so no lock is needed to read
# it: a reader sees one whole outcome, never half of two.  ``None`` until
# a lookup has run, which is what tells "not tried" from "tried and
# reached nothing".
_resolver_outcome: ResolverOutcome | None = None


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

    Warns
    -----
    FutureWarning
        When ``version`` is unusable.  Today the pin is ignored and the
        next URL resolves normally; a future major release will raise
        :class:`ValueError` instead.

        The leniency is right for ``MAIDR_CDN_VERSION`` -- ambient
        configuration may be set by something outside the caller's
        control, and crashing on it would be hostile.  It is wrong here:
        this is an explicit call with a bad argument, which is the
        textbook case for ``ValueError``, and the caller currently gets no
        return value, no exception, and a *log* line they may never see.
        So a typo does nothing, visibly (#294).

        Raising outright would break a script that has been quietly
        mistyping its pin and rendering fine, so it goes through a
        deprecation the way :func:`bundled_css_path` did.  The warning is
        the behaviour change; the raise is the next major's.
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

    candidate = str(version).strip()
    # Checked here as well as on every URL build, because the two
    # answer different questions. `_normalise_version_pin` asks "can I
    # use this?" every time it needs a URL, and logs. This asks "did the
    # caller just make a mistake?", once, at the point they made it --
    # which is the only moment a stack trace points anywhere useful.
    if _normalise_version_pin(candidate) is None:
        warnings.warn(
            f"maidr.set_cdn_version({version!r}) was given something that is "
            f"neither a semver such as '3.74.0' nor {BUNDLED_TAG!r} or "
            f"{LATEST_TAG!r}. The pin is ignored and URLs resolve as if it "
            "had not been set. A future major release will raise ValueError "
            "here instead.",
            FutureWarning,
            stacklevel=2,
        )

    _cdn_version_override = candidate


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

    The same applies to every Jupyter/IPython kernel, where each cell
    executes on the kernel's event loop: a notebook on the default setting
    serves the bundled version for the life of the kernel and never arms
    :func:`warn_if_bundle_is_stale`.  There is no synchronous start-up
    code in a notebook, so the way to move off the bundled version there
    is ``MAIDR_CDN_VERSION``, :func:`set_cdn_version`, or one explicit
    :func:`maidr.bundle_status` call, which resolves regardless of the
    loop and caches the answer.

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
    # A lookup that failed falls back to the bundled version, not to
    # `@latest`.  `@latest` is the mutable dist-tag whose seven-day
    # `Cache-Control` is the whole of #290 -- so degrading to it meant the
    # fix stopped applying in precisely the case it was meant to survive,
    # and an offline browser could still replay a week-old build (#295).
    #
    # The bundled version is a real published one, immutable, and is the
    # copy this wheel would have served anyway had the CDN been declined.
    # What it costs is that a network hiccup pins the page to a possibly
    # older release -- quieter, but staler. That trade was argued the
    # other way when this fallback was written, on the grounds that
    # `@latest` is byte-for-byte what users had before version resolution
    # existed and so nobody ends up worse off. Three other paths have
    # since moved to the bundled answer, and being the last one left
    # emitting the mutable tag is not a place worth defending.
    resolved = _resolve_latest_version()
    if resolved is None:
        return _offline_version()
    if _is_older_than_bundled(resolved):
        return _bundled_version()
    return resolved


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

    The last step warns, because there are two roads to ``latest`` and
    only one of them is normal.  A lookup that failed is a routine
    operating condition -- offline, blocked, a malformed response -- and
    is documented as the safe degradation; it stays quiet.  A bundled
    version that will not read is a broken install, nobody but the user
    can fix it, and the page still works, so without a word the only
    symptom is someone occasionally being served a week-old ``maidr.js``
    for reasons nothing in the output explains (#364).

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

    return _bundled_version()


def _bundled_version() -> str:
    """Return the version this wheel ships, or ``latest`` if it will not read.

    Split out of :func:`_offline_version` because the downgrade guard in
    :func:`get_cdn_version` needs *this* answer specifically.  Going through
    the offline path would hand back the resolver's answer from the cache --
    the very version being refused.

    Returns
    -------
    str
        The bundled version, or ``latest`` when it is unusable.
    """
    bundled = _deps.maidr_js_version()
    if _is_valid_version(bundled) and bundled != _UNKNOWN_VERSION:
        return bundled

    # The two faults read differently, and the point of speaking at all is
    # to be read: an absent VERSION reported as `is unreadable ('0.0.0')`
    # says the file contains those characters, which is the one thing it
    # does not. `maidr_js_version` returns the sentinel for missing,
    # empty and unreadable alike, so that is as far as the distinction
    # goes -- but it is the distinction someone chasing this needs first.
    if bundled == _UNKNOWN_VERSION:
        detail = "cannot be read (the VERSION file is missing or empty)"
    else:
        # Truncated for the same reason `_normalise_version_pin` truncates
        # its pin: nothing bounds the length of a garbled file, and a log
        # line is not where a megabyte belongs.
        detail = f"is not a version ({bundled[:_MAX_WARNED_KEY_LEN]!r})"

    # Keyed on the unusable value, so a wheel whose VERSION is garbled
    # rather than absent says which -- and a second, differently broken
    # one is still audible.
    warn_once(
        f"unusable-bundled-version:{bundled}",
        "maidr: the bundled maidr.js version %s, so CDN URLs fall back to "
        "the mutable maidr@%s tag. jsDelivr serves that with a seven-day "
        "cache lifetime, so a browser may replay an old bundle. Reinstall "
        "py-maidr, or pin a version with maidr.set_cdn_version().",
        detail,
        LATEST_TAG,
    )
    return LATEST_TAG


def _is_older_than_bundled(resolved: str) -> bool:
    """Report whether a resolver answer is older than the version we ship.

    The resolver is asked which version is current; nothing about the
    request obliges the answer to be one.  A compromised registry, a
    hostile caching proxy, or anything else that can reply could name an
    older-but-well-formed version and have it spliced into every CDN URL
    the page emits (#297).

    Refusing it is only a defence if the fallback is not the same party.
    Degrading to the mutable ``@latest`` tag would ask the CDN to resolve
    the version instead -- the same answer from the same place -- so the
    caller pins to :func:`_bundled_version` rather than falling through.
    That is the one version on this machine known to have shipped with the
    package.

    **This is not a tamper detector.**  A bundled copy ahead of what is
    published is a state this package already documents as normal: anyone
    running from source between releases is in it, and so is anyone whose
    upstream release was yanked.  The two are indistinguishable from here,
    which is why the log line is ``debug`` and leads with the ordinary
    cause.  What the guard buys either way is that the URL names a version
    this wheel was built against, which is the safe answer in all three.

    Scoped to the resolver's answer.  An explicit pin -- ``set_cdn_version``
    or ``MAIDR_CDN_VERSION`` -- is the caller's own decision about their own
    process and is left alone; a guard there would refuse a deliberate
    downgrade someone asked for by name.

    Parameters
    ----------
    resolved : str
        The version the resolver answered with.

    Returns
    -------
    bool
        True when the answer sorts below the bundled version.  False when
        either side cannot be compared, which leaves the resolver's answer
        in place: an unreadable bundled version is a broken install rather
        than evidence about the resolver.
    """
    bundled = _deps.maidr_js_version()
    if bundled == _UNKNOWN_VERSION:
        return False

    bundled_key = _version_key(bundled)
    resolved_key = _version_key(resolved)
    if bundled_key is None or resolved_key is None:
        return False
    if resolved_key >= bundled_key:
        return False

    _logger.debug(
        "maidr: the resolver answered maidr@%s, which is older than the %s "
        "bundled in this install -- normal between releases, or after an "
        "upstream release is yanked. CDN URLs use the bundled version, "
        "which is the copy this wheel was built against.",
        resolved,
        bundled,
    )
    return True


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

    The same applies to every Jupyter/IPython kernel, where each cell
    executes on the kernel's event loop: a notebook on the default setting
    serves the bundled version for the life of the kernel and never arms
    :func:`warn_if_bundle_is_stale`.  A notebook has no synchronous
    start-up code, so the way off the bundled version there is
    ``MAIDR_CDN_VERSION``, :func:`set_cdn_version`, or one explicit
    :func:`maidr.bundle_status` call, which resolves regardless of the
    loop and caches the answer.

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

    Clears :func:`resolver_outcome` too.  It describes the lookup this
    call is discarding, and leaving it behind would let a monitor read a
    stale verdict as the current one -- reporting an endpoint as broken
    after a successful re-resolution, or the reverse.

    Returns without waiting on a lookup already in flight — it does not
    take ``_fetch_lock``, which would make the reset itself block for the
    whole budget behind the request it is abandoning.  That is a promise
    about *this* call, not about the next one: a caller that needs a
    version afterwards still queues on ``_fetch_lock`` behind the
    abandoned request, and only then makes its own.  What the generation
    counter guarantees is that the abandoned answer is discarded rather
    than published over the reset -- its :func:`resolver_outcome` with
    it, since that verdict lands after this call cleared the previous one
    and would otherwise be read as the current one.
    """
    global _resolved_cdn_version, _resolution_attempted, _resolution_generation
    global _resolver_outcome
    with _resolution_lock:
        _resolved_cdn_version = None
        _resolution_attempted = False
        _resolver_outcome = None
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
        "maidr.util.cdn.maidr_css_cdn_url",
        "cdn_url(MAIDR_MATH_CSS_FILENAME) from maidr.util.cdn",
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
        bundled = _deps.maidr_js_version()
        if _is_valid_version(bundled) and bundled != _UNKNOWN_VERSION:
            return bundled
        # Asking for ``bundled`` is a request to serve what is installed,
        # which implies staying local.  Falling through to a network
        # lookup would betray that intent for someone who chose it to
        # avoid egress, so degrade to ``@latest`` — still a working URL,
        # still no request.
        warn_once(
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
    warn_once(
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
    warn_once(
        f"pre-split-pin:{version}",
        "maidr: CDN version pin %r predates maidr %s, where KaTeX moved out "
        "of maidr.css into maidr-math.css. py-maidr links no stylesheet, so "
        "LaTeX in AI chat responses will render unstyled at that version; "
        "everything else is unaffected. Pin %s or newer to style it.",
        version,
        _STYLESHEET_SPLIT_VERSION,
        _STYLESHEET_SPLIT_VERSION,
    )


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
        warn_once(
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
        warn_once(
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
        warn_once(
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
        warn_once(
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
        warn_once(
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
    the reset asked to discard.  The verdict :func:`_fetch_latest_version`
    recorded for it is dropped with it, because that reset cleared
    :func:`resolver_outcome` and the abandoned lookup's verdict would
    otherwise land after the reset and read as the current one.
    """
    global _resolved_cdn_version, _resolution_attempted, _resolver_outcome
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
            else:
                # The verdict belongs to the lookup the reset abandoned,
                # and it landed after the reset cleared the previous one
                # -- so it would otherwise be read as current.
                _resolver_outcome = None
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

    Records its verdict in :data:`_resolver_outcome` unconditionally, as a
    lone reference assignment.  Whether that verdict still describes the
    current lookup is the caller's question: :func:`_resolve_latest_version`
    is the one holding the generation it started under, so it is the one
    that discards the verdict when a reset intervened.

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
    global _resolver_outcome

    deadline = time.monotonic() + budget
    unreachable: list[str] = []
    answered_badly: list[str] = []
    resolved: str | None = None

    for url, key in _RESOLVER_ENDPOINTS:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            _logger.debug(
                "maidr: CDN version lookup budget spent before trying %s", url
            )
            # Never asked, so neither bucket: recording it as unreachable
            # would report a spent budget as a network fault, and as
            # answering badly would blame this code for a question it did
            # not put. The endpoints before it already carry the verdict.
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
        except HTTPError:
            # The server answered; the status was one we cannot use. That
            # is the endpoint telling us something -- a moved path, a
            # removed package, a rate limit -- and it is a different fact
            # from not having reached it at all.
            _logger.debug("maidr: CDN version lookup rejected at %s", url,
                          exc_info=True)
            answered_badly.append(url)
            continue
        except (ValueError, UnicodeDecodeError):
            # Bytes arrived and would not become JSON, or would not decode.
            # Reached, and unusable.
            _logger.debug("maidr: unparseable CDN version response from %s", url,
                          exc_info=True)
            answered_badly.append(url)
            continue
        except Exception:
            # Deliberately broad, and deliberately last.  The obvious
            # failures are OSError and HTTPException, but the contract
            # above is that a lookup failure degrades to the ``@latest``
            # URL rather than breaking rendering — and an exception this
            # list did not anticipate would break it.  Sandboxes make that
            # concrete: pytest-socket raises SocketBlockedError, which
            # derives from Exception, not OSError, and would otherwise
            # propagate out of render().
            #
            # Counted as unreachable rather than as a bad answer, because
            # that is the safe direction: an unrecognised failure calling
            # itself "this code is wrong" would redden a scheduled check
            # for a network condition nobody can fix.
            _logger.debug("maidr: CDN version lookup failed at %s", url, exc_info=True)
            unreachable.append(url)
            continue

        candidate = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(candidate, str) and _is_valid_version(candidate.strip()):
            resolved = candidate.strip()
            break
        # Answered, parsed, and said something this code cannot read: the
        # payload has no such key, or the value is not a version. An
        # endpoint that changed shape looks exactly like this.
        _logger.debug("maidr: unusable CDN version %r from %s", candidate, url)
        answered_badly.append(url)

    _resolver_outcome = ResolverOutcome(
        resolved=resolved,
        unreachable=tuple(unreachable),
        answered_badly=tuple(answered_badly),
    )
    return resolved
