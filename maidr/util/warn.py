"""Warning policy shared by everything that reports on the bundle.

Split out of :mod:`maidr.util.dependencies` (#293).  Both halves of that
module warn, and the split would otherwise have left one importing a
private helper from the other across a module boundary -- a wart four
reviews of #494 flagged in a row.

Deliberately a leaf: nothing here imports another ``maidr`` module, so
both sides can import it eagerly without the lazy-shim dance
``bundle_capability`` needs.  Keep it that way; the moment this file
imports back into the package, it stops being able to serve as the shared
bottom of the stack.
"""

from __future__ import annotations

import logging
import os
import threading

_logger = logging.getLogger(__name__)


# Keys of warnings already logged, so a bad pin is reported once instead
# of on every URL build.  See :func:`warn_once`.
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


#: Set to ``0`` / ``false`` / ``off`` to silence the staleness warning.
BUNDLE_WARNING_ENV_VAR = "MAIDR_BUNDLE_STALE_WARNING"


def warn_once(key: str, message: str, *args: object) -> None:
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


def bundle_warning_enabled() -> bool:
    """Return whether the staleness warning is enabled (it is by default)."""
    raw = os.environ.get(BUNDLE_WARNING_ENV_VAR)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}
