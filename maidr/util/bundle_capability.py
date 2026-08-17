"""What the bundled ``maidr.js`` is able to draw.

Split out of :mod:`maidr.util.dependencies` (#293), which had grown to own
three separable concerns. This is the one that answers "can the copy in
this wheel render the chart we are about to hand it" -- a question that
distance in version numbers cannot answer, and that the reader who most
needs the answer (``use_cdn=False``, offline) is the one a staleness
warning cannot reach.

Its tests live in ``tests/core/test_bundle_capability.py``, which already
split along this line before the module did.
"""

from __future__ import annotations

import logging
import re
import threading
import warnings
from collections.abc import Iterable

from maidr.util.dependencies import (
    BUNDLE_WARNING_ENV_VAR,
    _bundle_warning_enabled,
    bundled_js_path,
    maidr_js_version,
)

_logger = logging.getLogger(__name__)

#: An enum member assignment, which is how the bundle spells a trace type.
#: TypeScript compiles ``TraceType`` to a run of them, so the 4.3.0 bundle
#: carries ``e.AREA=`area`,e.ALLUVIAL=`alluvial`,e.BAR=`bar`,...``.
#:
#: All three quote characters, because the minifier picks whichever is
#: shortest for the surrounding context -- the 4.1.0 bundle uses backticks
#: throughout, and a check written for double quotes alone would have
#: reported every type missing.
#:
#: Anchored on the ``.UPPER_SNAKE =`` rather than matching every quoted
#: lower-snake string anywhere. The looser form was tenable while the bundle
#: was small, and stopped being so at 4.3.0: nine adapters gained chart types
#: and the vocabularies that came with them (MathML attribute names among
#: others) took the scrape from a few hundred tokens to **1265**, including
#: ordinary words like ``count``, ``above`` and ``accent``. A capability
#: check whose vocabulary contains most of the dictionary answers "yes, your
#: bundle knows that" to anything, so it can no longer raise the warning it
#: exists for -- failing silent rather than merely failing safe (#436).
#: Narrowed, 4.3.0 yields 60.
_BUNDLE_TOKEN_RE = re.compile(
    r"\.[A-Z][A-Z0-9_]*\s*=\s*(?P<quote>[`\"'])"
    r"(?P<token>[a-z][a-z0-9_]{1,39})(?P=quote)"
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
