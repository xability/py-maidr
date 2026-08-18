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

Version distance is the coarse signal, not the answer.  What a user
actually wants to know is whether the bundle can draw the chart they are
emitting, and :func:`maidr.util.bundle_capability.warn_if_bundle_cannot_render`
answers that directly by reading the installed file — no network, so unlike
the staleness warning it reaches the offline and pinned users whose bundle
is what runs.  Keep the two apart when changing either: "you are
drifting" and "this chart will not draw" are different claims, and the
second is the one worth acting on.

What this module no longer owns
-------------------------------
The capability check above lives in :mod:`maidr.util.bundle_capability`
as of #293, which is splitting this file up one concern at a time.  The
names it took are still reachable from here -- see the "Moved out of this
module" section at the foot of the file, which resolves them lazily.  A
reader scanning this file for what it owns should read that section as
part of the answer.
"""

from __future__ import annotations

import logging
import re
import warnings
from functools import lru_cache
from importlib.resources import as_file, files
from pathlib import Path

# ``BUNDLE_WARNING_ENV_VAR`` is not used in this module; it is imported to
# keep ``maidr.util.dependencies.BUNDLE_WARNING_ENV_VAR`` resolving, which it
# did before the name moved to ``warn`` in #496.  Straight from the owner
# rather than through the ``__getattr__`` shim below: the shim would have
# forwarded it to ``bundle_freshness``, which resolves only because *that*
# module happens to import it for its own message text -- so a later cleanup
# there would have broken an unrelated public path.  ``warn`` is a leaf, so
# importing it eagerly raises none of the cycle questions the shim exists for.
from maidr.util.warn import (  # noqa: F401
    _MAX_WARNED_KEY_LEN,
    BUNDLE_WARNING_ENV_VAR,
    warn_once,
)


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


_VERSION_FILENAME = "VERSION"

#: Reported by :func:`maidr_js_version` when ``static/VERSION`` is absent
#: or empty.  Means "no bundled version to speak of", so callers treat it
#: as unknown rather than as an ancient release.
_UNKNOWN_VERSION = "0.0.0"

# ---------------------------------------------------------------------------
# CDN version resolution
# ---------------------------------------------------------------------------


#: CDN-only asset: the Altair adapter loads it, but the wheel does not
#: ship it, so it must never be passed to :func:`_bundled_asset_path`.
MAIDR_VEGALITE_FILENAME = "vegalite.js"














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


# Shared: the placeholder is an *asset* concern, and both the bundled path
# above and `cdn.maidr_css_cdn_url` point at the same 406-byte file. Kept
# here rather than in `cdn` so the asset side does not import the CDN side
# -- that would close the loop the split exists to open.
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


@lru_cache(maxsize=1)
def _inline_bundle_sources() -> "tuple[str, str]":
    """Return the bundled ``maidr-math.css`` and ``maidr.js`` as strings.

    Memoised because :func:`inline_bundle_tags` runs once per render and a
    Shiny app renders once per reactive flush, while the files ship inside
    the wheel and cannot change under a running interpreter.  Uncached,
    each flush re-read and re-decoded about 1.9 MB.

    The public :func:`read_bundled_js` / :func:`read_bundled_math_css` are
    left uncached so that callers -- and tests -- can still stub the paths
    behind them.  Call ``.cache_clear()`` on this function if a test needs
    the same for the inline path.

    Returns
    -------
    tuple of (str, str)
        The maths stylesheet source and the ``maidr.js`` source.

    Raises
    ------
    FileNotFoundError
        If either asset is missing from the installed package.
    OSError
        If either asset cannot be read.
    """
    return read_bundled_math_css(), read_bundled_js()


def inline_bundle_tags() -> "list | None":
    """Return tags that embed the bundled ``maidr.js`` and KaTeX CSS inline.

    An ``HTMLDependency`` is the right way to ship the bundle whenever the
    host serves the assets and htmltools can materialise them.  It is not
    an option for output that is serialised with
    :meth:`htmltools.Tag.get_html_string` -- which silently drops
    ``HTMLDependency`` children -- and then embedded in an iframe
    ``srcdoc``.  A ``srcdoc`` document also has no reachable
    ``window.parent.__maidrJsSource`` unless
    :func:`maidr.api.init_notebook` populated it, which only happens in a
    notebook.  Outside a notebook those two facts leave an iframed
    ``use_cdn=False`` render with no source for ``maidr.js`` at all, so the
    source itself has to travel inline.

    The bare ``<link data-maidr-math>`` marker mirrors the notebook
    bootstrap: ``maidr.js`` decides whether to fetch ``maidr-math.css`` by
    looking for a link carrying that attribute, and a ``<style>`` element
    never matches.  Without the marker it reports the maths rules missing
    even though they are already on the page.

    Returns
    -------
    list of htmltools.Tag, or None
        ``<style>``, the ``data-maidr-math`` marker, and ``<script>``, in
        the order they must appear in the document.  ``None`` when the
        bundle cannot be read, leaving the caller to fall back to the CDN.

    Notes
    -----
    A bundle that predates maidr 3.75.1 ships no ``maidr-math.css``, and
    :func:`bundled_math_css_path` raises for it.  :func:`maidr.init_notebook`
    already treats that as "warn and use the CDN" rather than as a failed
    render, and so does this: a broken install rendered a degraded chart
    before this path existed, and it should not start raising instead.
    """
    from htmltools import tags

    try:
        math_css, js_source = _inline_bundle_sources()
    except (OSError, ValueError):
        # ``OSError`` covers missing and unreadable files (``FileNotFoundError``
        # is one).  ``ValueError`` is here for ``UnicodeDecodeError``, which a
        # truncated or corrupted asset raises out of ``read_text`` and which is
        # *not* an ``OSError`` -- so catching only file errors would let a
        # damaged bundle crash the render this exists to keep alive.
        # Imported here rather than at module scope: `bundle_freshness`
        # imports *this* module, so a top-level import would close the
        # loop. This is the only call in the other direction.
        from maidr.util.bundle_freshness import warn_bundle_unreadable

        warn_bundle_unreadable()
        return None

    return [
        tags.style(math_css),
        tags.link(**{"data-maidr-math": ""}),
        tags.script(js_source, type="text/javascript"),
    ]


#: What the browser says when ``use_cdn="auto"`` runs out of sources.
#:
#: Every fallback can fail to resolve, and each used to do it in silence: the
#: notebook ones only act ``if (jsSrc)`` and swallow the miss, and the bundled
#: ones set no ``onerror`` at all. What the reader gets either way is a chart
#: with no MAIDR runtime -- a picture, with nothing saying why (#455).
#:
#: Names the setting that works rather than describing the failure, because
#: the person who hits this is on an air-gapped deployment and the answer
#: (``use_cdn=False``) is otherwise only discoverable by reading the source.
#:
#: A plain string rather than an f-string: it is interpolated *into* f-strings,
#: so its braces must not be doubled.
#:
#: Lives here rather than beside either renderer because both emit the same
#: failure, and one wording in two files is one wording that can drift.
OFFLINE_FALLBACK_REPORT = """
    function reportNoRuntime(why) {
        console.error(
            '[maidr] The chart loaded but its runtime did not: '
            + why + '. The CDN was unreachable and the bundled '
            + 'copy could not be resolved from inside this frame. '
            + 'Re-render with use_cdn=False to inline the bundle, '
            + 'which works without network access.'
        );
    }
"""


# ---------------------------------------------------------------------------
# Moved out of this module
# ---------------------------------------------------------------------------

#: Names that now live in :mod:`maidr.util.bundle_capability` (#293).
#:
#: Kept reachable from here because ``maidr.util.dependencies`` is an import
#: path other code already uses, and a split is not a reason to break it.
_MOVED_TO_BUNDLE_CAPABILITY = frozenset(
    {
        "MaidrBundleTraceWarning",
        "bundle_trace_types",
        "schema_trace_types",
        "warn_if_bundle_cannot_render",
    }
)

#: Names that now live in :mod:`maidr.util.cdn` (#293).
#:
#: Only the public ones. The resolver's *state* is deliberately absent:
#: the shim forwards attribute **reads**, and cannot forward a **write**,
#: so ``monkeypatch.setattr(dependencies, "urlopen", ...)`` would set an
#: attribute nothing in ``cdn`` reads -- a patch that silently does
#: nothing rather than one that fails. Listing the private names here
#: would make that trap look supported. Patch ``maidr.util.cdn``.
_MOVED_TO_CDN = frozenset(
    {
        "BUNDLED_TAG",
        "CDN_TIMEOUT_ENV_VAR",
        "CDN_VERSION_ENV_VAR",
        "LATEST_TAG",
        "MAIDR_CSS_CDN_URL",
        "MAIDR_JS_CDN_URL",
        "ResolverOutcome",
        "bundled_cdn_url",
        "cdn_url",
        "get_cdn_version",
        "maidr_css_cdn_url",
        "maidr_js_cdn_url",
        "reset_cdn_version_cache",
        "set_cdn_version",
        "unresolved_cdn_url",
    }
)

#: Names that now live in :mod:`maidr.util.bundle_freshness` (#293).
_MOVED_TO_BUNDLE_FRESHNESS = frozenset(
    {
        "BundleStatus",
        "MaidrBundleStaleWarning",
        "STALE_MINOR_GAP",
        "bundle_status",
        "resolver_outcome",
        "warn_bundle_unreadable",
        "warn_if_bundle_is_stale",
    }
)


def __dir__() -> list[str]:
    """List the moved names alongside this module's own.

    PEP 562 pairs this with :func:`__getattr__` because attribute lookup
    and introspection are answered by different machinery: without it,
    ``dir()`` and an interactive tab-complete would omit names that
    ``getattr`` resolves perfectly well.

    Note this does *not* restore ``from maidr.util.dependencies import
    *``, which reads ``__dict__`` rather than ``__dir__`` when a module
    declares no ``__all__``. Nothing in this package or its docs uses that
    form against this module, and inventing an ``__all__`` for a
    2,000-line module to support it would create a list that goes stale
    the first time anything is added.

    Returns
    -------
    list of str
        Everything defined here, plus the names that moved.
    """
    return sorted(
        set(globals())
        | _MOVED_TO_CDN
        | _MOVED_TO_BUNDLE_CAPABILITY
        | _MOVED_TO_BUNDLE_FRESHNESS
    )


def __getattr__(name: str) -> object:
    """Resolve names that moved to a sibling module.

    Deliberately lazy rather than a plain re-export at the bottom of this
    file.  ``bundle_capability`` imports *from here*, so importing it back
    eagerly would make the direction of the dependency circular: whichever
    module a program happened to import first would find the other
    half-initialised.  Resolving on attribute access instead means the
    import only ever runs after both modules are loadable.

    Parameters
    ----------
    name : str
        The attribute being looked up.

    Returns
    -------
    object
        The attribute, when it is one that moved.

    Raises
    ------
    AttributeError
        For anything else, which is what Python expects here.
    """
    if name in _MOVED_TO_CDN:
        from maidr.util import cdn

        return getattr(cdn, name)

    if name in _MOVED_TO_BUNDLE_CAPABILITY:
        from maidr.util import bundle_capability

        return getattr(bundle_capability, name)
    if name in _MOVED_TO_BUNDLE_FRESHNESS:
        from maidr.util import bundle_freshness

        return getattr(bundle_freshness, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
