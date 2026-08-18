"""How far the bundled ``maidr.js`` has drifted from what is published.

Split out of :mod:`maidr.util.dependencies` (#293), which owned three
separable concerns.  This is the one that answers "how old is the copy in
this wheel" -- the coarse signal.  Whether that copy can actually draw a
given chart is a different question, answered by
:mod:`maidr.util.bundle_capability`, and the two are deliberately kept
apart: "you are drifting" and "this chart will not draw" are different
claims, and the second is the one worth acting on.

Its tests live in ``tests/core/test_bundle_freshness.py``, which split
along this line before the module did.
"""

from __future__ import annotations

import logging
import threading
import warnings
from typing import NamedTuple

from maidr.util import dependencies as _deps
from maidr.util import cdn as _cdn
from maidr.util.cdn import ResolverOutcome
from maidr.util.dependencies import (
    _UNKNOWN_VERSION,
    _version_key,
)
from maidr.util.warn import (
    BUNDLE_WARNING_ENV_VAR,
    bundle_warning_enabled,
    warn_once,
)

_logger = logging.getLogger(__name__)

#: Minor-version gap at which the bundled fallback stops being "a release
#: or two behind" and starts being a copy users should know about.  The
#: bug report that prompted this check cited a gap of 8.
#:
#: Picked without the release histories, then measured against them (#292).
#: The question that decides it is not how fast upstream ships, it is how
#: many minors accumulate between the py-maidr releases that refresh the
#: bundle.  Over the seventeen cycles from 2026-01-31 to 2026-08-10:
#:
#:     median 1   mean 1.7   min 0   max 7
#:     cycles reaching 3+:  6/17  (35%)
#:     cycles reaching 5+:  1/17  (6%)
#:     cycles reaching 8+:  0/17  (0%)
#:
#: So 5 fires on the one cycle in seventeen where the bundle genuinely
#: fell behind -- a 68-day gap with nothing released -- and stays quiet
#: otherwise.  3 would fire on a third of all cycles, which is how a
#: warning becomes noise; 8 would not have fired even on that one.
#:
#: Recompute the *cycle* table, not upstream's cadence, if this is ever
#: revisited: upstream shipping faster only matters here to the extent it
#: outruns py-maidr's releases.
STALE_MINOR_GAP = 5


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


def resolver_outcome() -> ResolverOutcome | None:
    """Report why the last ``latest`` lookup ended as it did.

    For a monitor rather than for a render.  The scheduled freshness check
    passes when the published version cannot be resolved, because a
    resolver hiccup is not a drift signal and failing on one would train
    maintainers to ignore the job.  That is right for a hiccup and wrong
    for a persistent failure: if the resolver stays unreachable the job
    stays green forever while checking nothing, and a green check that
    verifies nothing is worse than a red one because it is
    indistinguishable from a real pass (#298).

    What separates the two is *how* it failed.  Endpoints that never
    answered are the network, which nobody watching the job can fix.
    Endpoints that answered with something this code could not use are
    this code being wrong about their shape -- which is the most likely
    long-lived cause, and the one worth waking someone for.

    Returns
    -------
    ResolverOutcome or None
        ``None`` when no lookup has run in this process, which is a
        different thing from one that ran and reached nothing.  A pinned
        or offline session never resolves, so the caller has to tell those
        apart rather than reading an empty outcome as a verdict.

    Examples
    --------
    >>> resolver_outcome()  # doctest: +SKIP
    ResolverOutcome(resolved='4.2.0', unreachable=(), answered_badly=())
    """
    return _cdn._resolver_outcome


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
    bundled = _deps.maidr_js_version()
    published = _cdn._published_version(resolve=resolve)

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
    warn_once(
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
    if bundle_is_primary in _bundle_warned or not bundle_warning_enabled():
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
