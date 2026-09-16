"""Where a page finds the DotPad tactile-display SDK, and how to carry a copy.

``maidr.js`` can draw a chart onto a Dot Pad, a refreshable tactile display,
through the vendor's SDK. It does not bundle that SDK: the braille engine
inside it is a 14 MB liblouis build, and every wheel and every page would
carry it for the few readers who own the device. So by default ``maidr.js``
imports the vendor's published copy from a CDN, pinned to a commit, the
first time a DotPad is connected -- which is the one path an offline
document (``use_cdn=False``) still takes to the network.

This module is the Python side of closing that path. Two settings name a
copy the page should use instead, and travel into every document py-maidr
produces as the globals ``maidr.js`` reads::

    window.MAIDR_DOTPAD_SDK_URL          the SDK ES module
    window.MAIDR_DOTPAD_ASSET_BASE_URL   the directory holding liblouis

And :func:`download_dotpad_sdk` fetches the pinned copy -- the module, the
liblouis build, and the LGPL licence text and wrapper sources the vendor
asks redistributors to keep beside it -- verified against the digests in
:data:`DOTPAD_SDK_FILES`, into a directory :func:`save_html` then copies
into ``lib/`` next to a ``use_cdn=False`` document. Dot Inc. permit MAIDR
to redistribute the SDK; the package stays small because nothing here runs
until it is asked to.

The pins are read at import from ``maidr/static/dotpad-sdk.json``: the
manifest ``maidr.js`` ships as ``dist/dotpad-sdk.json`` in its npm package
and reads its own pins from. ``fetch-maidr-bundle.sh`` copies it beside
``maidr.js`` with every bundle refresh, so the two cannot drift apart.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any, NamedTuple, Optional
from urllib.request import Request, urlopen

from maidr.util.warn import warn_once

#: The manifest the pins below are read from, relative to ``maidr/static/``.
#: It is ``dist/dotpad-sdk.json`` from the ``maidr`` npm package, copied
#: beside ``maidr.js`` by ``fetch-maidr-bundle.sh``.
DOTPAD_SDK_PINS_FILENAME = "dotpad-sdk.json"

_STATIC_PACKAGE = "maidr"
_STATIC_SUBDIR = "static"


class DotPadSdkFile(NamedTuple):
    """The size and digest of one file at the pinned commit."""

    bytes: int
    sha256: str


#: The string fields every manifest names, all of them non-empty.
_REQUIRED_PIN_FIELDS = (
    "version",
    "repository",
    "commit",
    "baseUrl",
    "module",
    "assetDir",
)

#: What the pins read as when the manifest will not. Every value is inert:
#: the version stands in for the unknown one the way
#: ``dependencies._UNKNOWN_VERSION`` does, and an empty ``files`` is what
#: :func:`download_dotpad_sdk` and :func:`dotpad_sdk_path` check before
#: they do anything with a copy.
_UNKNOWN_VERSION = "0.0.0"
_UNREADABLE_PINS: dict[str, Any] = {
    "version": _UNKNOWN_VERSION,
    "repository": "",
    "commit": "",
    "baseUrl": "",
    "module": "",
    "assetDir": "lib/",
    "files": {},
}


def _parse_pins(document: Any) -> dict[str, Any]:
    """Check a parsed manifest and turn its ``files`` into named tuples.

    Every field the module publishes is checked here, because the manifest
    arrives from outside this repository: ``fetch-maidr-bundle.sh`` copies
    whatever ``dist/dotpad-sdk.json`` the pinned ``maidr.js`` release ships.
    A field that changed shape upstream is a broken manifest, named as such,
    rather than a ``KeyError`` from somewhere further down.

    Parameters
    ----------
    document : Any
        The result of parsing ``dotpad-sdk.json``.

    Returns
    -------
    dict
        The manifest, with ``files`` mapping each path to a
        :class:`DotPadSdkFile`.

    Raises
    ------
    ValueError
        When a field is missing or is not the shape the module expects.
    """
    if not isinstance(document, dict):
        raise ValueError("the manifest is not a JSON object")
    for field in _REQUIRED_PIN_FIELDS:
        value = document.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field!r} is missing or is not a non-empty string")
    entries = document.get("files")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("'files' is missing or names no file")
    parsed: dict[str, DotPadSdkFile] = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f"the entry for {name!r} is not an object")
        size = entry.get("bytes")
        digest = entry.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError(f"{name!r} has no positive integer 'bytes'")
        if not isinstance(digest, str) or not digest:
            raise ValueError(f"{name!r} has no 'sha256'")
        parsed[name] = DotPadSdkFile(size, digest)
    return {**document, "files": parsed}


def _read_pins() -> dict[str, Any]:
    """Load the shipped manifest, as ``maidr.js`` published it.

    A manifest that is missing or malformed is a broken install, and
    nobody but the user can fix it -- so it is a warning and inert pins
    rather than an exception, because this module is imported by
    ``maidr/__init__.py`` and raising here would take ``import maidr``
    down over a tactile display most readers do not own. Every path that
    needs a real pin checks for one and says what is wrong.

    Returns
    -------
    dict
        The parsed ``dotpad-sdk.json``: ``version``, ``repository``,
        ``commit``, ``baseUrl``, ``module``, ``assetDir`` and ``files``,
        plus ``upstream`` naming the vendor archive the files came from.
        :data:`_UNREADABLE_PINS` when it will not read.
    """
    try:
        resource = files(_STATIC_PACKAGE).joinpath(
            _STATIC_SUBDIR, DOTPAD_SDK_PINS_FILENAME
        )
        return _parse_pins(json.loads(resource.read_text(encoding="utf-8")))
    except (OSError, ModuleNotFoundError, TypeError, ValueError) as error:
        # ``json.JSONDecodeError`` is a ``ValueError``; a missing file is
        # an ``OSError``; an installed package without the resource is a
        # ``ModuleNotFoundError``.
        warn_once(
            f"dotpad-pins:{error}",
            "Bundled DotPad SDK manifest '%s' will not read (%s). "
            "The tactile display cannot be set up offline until it does; "
            "reinstall py-maidr or run the update-maidr-js workflow.",
            DOTPAD_SDK_PINS_FILENAME,
            error,
        )
        return dict(_UNREADABLE_PINS)


_pins = _read_pins()

#: The SDK release these pins describe.
DOTPAD_SDK_VERSION: str = _pins["version"]

#: The repository the files are served from, and the commit every URL
#: below is pinned to.
#:
#: This is a mirror, ``xability/dotpad-sdk-guide``, rather than the
#: vendor's own repository: Dot Inc. publish this release only as a zip
#: archive, which a browser cannot import a module out of, so the mirror
#: carries the extracted files, byte-verified against that archive. The
#: manifest's ``upstream`` entry records the vendor repository, commit,
#: archive path and archive SHA-256 they were checked against.
#:
#: Pinning a commit matters beyond immutability. An earlier vendor commit
#: carried a corrupt ``liblouis.data``: the repository's ``.gitattributes``
#: said ``* text=auto`` and the file is braille-table text with no NUL
#: byte in it, so git rewrote its line endings on commit. It is an
#: Emscripten package addressed by absolute byte offsets, so every table
#: after the first dropped byte was read from the wrong place and the
#: braille line silently fell back to grade 1. The digests below are the
#: intact bytes.
DOTPAD_SDK_REPOSITORY: str = _pins["repository"]
DOTPAD_SDK_COMMIT: str = _pins["commit"]

#: Where the pinned files are served from. Referencing a commit on jsDelivr
#: is what makes the bytes immutable.
DOTPAD_SDK_BASE_URL: str = _pins["baseUrl"]

#: The SDK module, and the directory beside it that liblouis loads from.
DOTPAD_SDK_MODULE: str = _pins["module"]
DOTPAD_SDK_ASSET_DIR: str = _pins["assetDir"]

#: Every file a copy of the SDK consists of, relative to the base URL.
#:
#: The liblouis build is LGPL-2.1-or-later. Its licence text and the
#: sources of the WebAssembly wrapper are here because the vendor's README
#: asks anyone who redistributes the SDK to keep them beside the runtime
#: files, which is the LGPL's relinking requirement.
DOTPAD_SDK_FILES: dict[str, DotPadSdkFile] = _pins["files"]

#: The record :func:`download_dotpad_sdk` writes beside the files, so a copy
#: found on a server can be traced back to a commit.
DOTPAD_SDK_MANIFEST_NAME = "manifest.json"

#: Environment variables. The first two carry the same names as the page
#: globals they set; the third names a directory holding a downloaded copy.
DOTPAD_SDK_URL_ENV_VAR = "MAIDR_DOTPAD_SDK_URL"
DOTPAD_ASSET_BASE_URL_ENV_VAR = "MAIDR_DOTPAD_ASSET_BASE_URL"
DOTPAD_SDK_DIR_ENV_VAR = "MAIDR_DOTPAD_SDK_DIR"

#: The page globals ``maidr.js`` reads.
_SDK_URL_GLOBAL = "MAIDR_DOTPAD_SDK_URL"
_ASSET_BASE_URL_GLOBAL = "MAIDR_DOTPAD_ASSET_BASE_URL"

#: The name of the dependency ``save_html`` copies a local SDK under, so the
#: folder beside the document reads ``lib/dotpad-sdk-<version>/``.
_DEPENDENCY_NAME = "dotpad-sdk"


class DotPadSdkConfig(NamedTuple):
    """Where a page is told to find the SDK, or ``None`` for the CDN."""

    sdk_url: Optional[str]
    asset_base_url: Optional[str]


# ---------------------------------------------------------------------------
# Naming a copy by URL
# ---------------------------------------------------------------------------

# ``None`` means "not set from Python": fall through to the environment.
_sdk_url: Optional[str] = None
_asset_base_url: Optional[str] = None


def _non_empty(value: Optional[str]) -> Optional[str]:
    """Return ``value`` unless it is ``None`` or empty; an empty value is unset."""
    if value is None:
        return None
    return value if value.strip() else None


def set_dotpad_sdk(
    sdk_url: Optional[str] = None, asset_base_url: Optional[str] = None
) -> None:
    """Name the copy of the DotPad SDK every document should load.

    Parameters
    ----------
    sdk_url : str, optional
        URL of the SDK ES module (``DotPadSDK-<version>.js``). ``None`` or an
        empty string falls back to ``MAIDR_DOTPAD_SDK_URL``, and then to the
        vendor's copy on the CDN.
    asset_base_url : str, optional
        URL of the directory holding the braille engine (``liblouis.js``,
        ``.wasm`` and ``.data``). Needed only when it is not the ``lib/``
        folder beside the module. Falls back to
        ``MAIDR_DOTPAD_ASSET_BASE_URL``.

    Notes
    -----
    Both values are written into every document py-maidr produces, ahead
    of ``maidr.js``, as ``window.MAIDR_DOTPAD_SDK_URL`` and
    ``window.MAIDR_DOTPAD_ASSET_BASE_URL``. Inside a notebook the document
    is a ``srcdoc`` iframe with no base URL, so the URL must be one the
    browser can reach on its own -- absolute, or served by the notebook.

    Process-wide state, like :func:`maidr.set_use_cdn`: in a server handling
    several sessions, set it once at startup.
    """
    global _sdk_url, _asset_base_url
    _sdk_url = _non_empty(sdk_url)
    _asset_base_url = _non_empty(asset_base_url)


def get_dotpad_sdk() -> DotPadSdkConfig:
    """Return where documents are told to find the SDK.

    A value set with :func:`set_dotpad_sdk` wins; otherwise the environment
    variables ``MAIDR_DOTPAD_SDK_URL`` and ``MAIDR_DOTPAD_ASSET_BASE_URL``
    are read, on every call, so a variable set after ``import maidr`` is
    seen. Empty values count as unset.

    Returns
    -------
    DotPadSdkConfig
        ``sdk_url`` and ``asset_base_url``, each a string or ``None``.
    """
    return DotPadSdkConfig(
        sdk_url=_sdk_url or _non_empty(os.environ.get(DOTPAD_SDK_URL_ENV_VAR)),
        asset_base_url=_asset_base_url
        or _non_empty(os.environ.get(DOTPAD_ASSET_BASE_URL_ENV_VAR)),
    )


def _js_string(value: str) -> str:
    """Quote ``value`` as a JavaScript literal safe inside ``<script>``.

    JSON is a subset of JavaScript, so :func:`json.dumps` does the quoting.
    It leaves ``/`` alone, though, and an HTML parser ends the surrounding
    ``<script>`` at the first ``</`` it sees whatever the JavaScript around
    it says, so that sequence is escaped too.
    """
    return json.dumps(value).replace("</", "<\\/")


def dotpad_config_script(config: Optional[DotPadSdkConfig] = None) -> Optional[str]:
    """The JavaScript that declares the configured globals, or ``None``.

    Parameters
    ----------
    config : DotPadSdkConfig, optional
        The settings to write; defaults to :func:`get_dotpad_sdk`.

    Returns
    -------
    str or None
        One ``window.X = "...";`` assignment per configured value, or
        ``None`` when neither is configured so nothing is emitted.
    """
    if config is None:
        config = get_dotpad_sdk()
    assignments = [
        f"window.{name} = {_js_string(value)};"
        for name, value in (
            (_SDK_URL_GLOBAL, config.sdk_url),
            (_ASSET_BASE_URL_GLOBAL, config.asset_base_url),
        )
        if value is not None
    ]
    if not assignments:
        return None
    return "\n".join(assignments)


def dotpad_config_tag(config: Optional[DotPadSdkConfig] = None):
    """A ``<script>`` declaring the configured globals, or ``None``.

    For the paths that serialise a tag into an iframe's ``srcdoc``, where an
    ``HTMLDependency`` would be dropped; :func:`dotpad_config_dependency`
    is the same declaration for a document with a head.

    Parameters
    ----------
    config : DotPadSdkConfig, optional
        The settings to write; defaults to :func:`get_dotpad_sdk`.

    Returns
    -------
    htmltools.Tag or None
    """
    script = dotpad_config_script(config)
    if script is None:
        return None
    from htmltools import tags

    return tags.script(script, type="text/javascript")


def dotpad_config_dependency(config: Optional[DotPadSdkConfig] = None):
    """The configured globals as an ``HTMLDependency``, or ``None``.

    Its ``head`` carries the declaration, and it has no files, so listing
    it ahead of the bundle's dependency is what puts the globals ahead of
    the bundle's ``<script>`` in the rendered head. ``maidr.js`` reads them
    at connect time rather than at load, so the order is a courtesy that
    matches the R package rather than a requirement.

    Parameters
    ----------
    config : DotPadSdkConfig, optional
        The settings to write; defaults to :func:`get_dotpad_sdk`.

    Returns
    -------
    htmltools.HTMLDependency or None
    """
    tag = dotpad_config_tag(config)
    if tag is None:
        return None
    from htmltools import HTMLDependency

    return HTMLDependency(name="maidr-dotpad-config", version="1.0.0", head=tag)


def dotpad_config_child(*, inline: bool):
    """Whichever of the two declarations a render path can carry.

    Parameters
    ----------
    inline : bool
        True on a path that serialises into an iframe, which keeps only
        tags; False for a document, which keeps dependencies in its head.

    Returns
    -------
    htmltools.Tag, htmltools.HTMLDependency, or None
    """
    return dotpad_config_tag() if inline else dotpad_config_dependency()


# ---------------------------------------------------------------------------
# Carrying a copy
# ---------------------------------------------------------------------------


def _user_cache_dir() -> Path:
    """The per-user cache directory, by platform convention."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base)


def dotpad_sdk_dir() -> Path:
    """Where a downloaded copy of the SDK lives.

    ``MAIDR_DOTPAD_SDK_DIR`` when set, otherwise a per-user cache directory
    (``~/.cache/maidr/dotpad-sdk/<version>`` on Linux, the platform's equivalent
    elsewhere). Nothing is created by asking.

    Returns
    -------
    pathlib.Path
    """
    configured = _non_empty(os.environ.get(DOTPAD_SDK_DIR_ENV_VAR))
    if configured is not None:
        return Path(configured).expanduser()
    return _user_cache_dir() / "maidr" / "dotpad-sdk" / DOTPAD_SDK_VERSION


def _mismatch(data: bytes, expected: DotPadSdkFile) -> Optional[str]:
    """Why ``data`` is not the file described, or ``None`` when it is.

    Size first, because it is the failure with a story: the corrupt
    ``liblouis.data`` that motivated the pin was 7,685 bytes short, and a
    size says so where a digest only says "different".
    """
    if len(data) != expected.bytes:
        return f"expected {expected.bytes} bytes, got {len(data)}"
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected.sha256:
        return f"expected sha256 {expected.sha256}, got {digest}"
    return None


def _file_is_valid(path: Path, expected: DotPadSdkFile) -> bool:
    """True when ``path`` holds exactly the bytes the manifest describes."""
    try:
        return _mismatch(path.read_bytes(), expected) is None
    except OSError:
        return False


def _fetch(url: str, timeout: float) -> bytes:
    """Download ``url`` in full."""
    request = Request(url, headers={"User-Agent": "py-maidr"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def download_dotpad_sdk(
    directory: "str | os.PathLike[str] | None" = None,
    *,
    force: bool = False,
    timeout: float = 60.0,
) -> Path:
    """Fetch the pinned DotPad SDK into a directory, for use offline.

    Downloads every file in :data:`DOTPAD_SDK_FILES` from the pinned
    repository at the pinned commit, verifies each against its recorded
    size and SHA-256, and writes a ``manifest.json`` beside them naming the
    commit they came from. A file already present and correct is left
    alone, so a second call costs nothing; ``force`` refetches regardless.

    Once downloaded, ``save_html(..., use_cdn=False)`` copies the directory
    into ``lib/`` next to the document and points ``maidr.js`` at it, so a
    reader can connect a DotPad without the network. Around 14 MB, almost
    all of it the braille engine's translation tables.

    Parameters
    ----------
    directory : path-like, optional
        Where to write. Defaults to :func:`dotpad_sdk_dir`.
    force : bool, default=False
        Refetch files that are already present and correct.
    timeout : float, default=60.0
        Seconds allowed for each file.

    Returns
    -------
    pathlib.Path
        The directory the SDK was written to.

    Raises
    ------
    RuntimeError
        When the shipped manifest did not read, so there is no pin to
        fetch; or when a downloaded file does not match its recorded size
        or digest, in which case nothing is written for that file and the
        error names the difference.
    urllib.error.URLError
        When a file cannot be fetched at all.
    """
    if not DOTPAD_SDK_FILES:
        raise RuntimeError(
            f"The bundled DotPad SDK manifest '{DOTPAD_SDK_PINS_FILENAME}' did "
            "not read, so there is nothing to download. Reinstall py-maidr or "
            "run the update-maidr-js workflow."
        )
    target_dir = (
        Path(directory).expanduser() if directory is not None else dotpad_sdk_dir()
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    for relative, expected in DOTPAD_SDK_FILES.items():
        target = target_dir.joinpath(*relative.split("/"))
        if not force and _file_is_valid(target, expected):
            continue
        url = DOTPAD_SDK_BASE_URL + relative
        data = _fetch(url, timeout)
        problem = _mismatch(data, expected)
        if problem is not None:
            raise RuntimeError(f"DotPad SDK file {relative} from {url}: {problem}")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Written beside and renamed over, so a reader of the directory
        # never sees a half-written file as the real one.
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(data)
        os.replace(partial, target)

    manifest = {
        "version": DOTPAD_SDK_VERSION,
        "repository": DOTPAD_SDK_REPOSITORY,
        "commit": DOTPAD_SDK_COMMIT,
        "baseUrl": DOTPAD_SDK_BASE_URL,
        "module": DOTPAD_SDK_MODULE,
        "assetDir": DOTPAD_SDK_ASSET_DIR,
        "files": {
            name: {"bytes": entry.bytes, "sha256": entry.sha256}
            for name, entry in DOTPAD_SDK_FILES.items()
        },
    }
    (target_dir / DOTPAD_SDK_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return target_dir


def dotpad_sdk_path(
    directory: "str | os.PathLike[str] | None" = None,
) -> Optional[Path]:
    """The directory holding a complete copy of the SDK, or ``None``.

    Complete means every file in :data:`DOTPAD_SDK_FILES` is present at
    its recorded size. The digests are checked when the copy is made, not
    on every render, so this costs a handful of ``stat`` calls.

    Parameters
    ----------
    directory : path-like, optional
        Where to look. Defaults to :func:`dotpad_sdk_dir`.

    Returns
    -------
    pathlib.Path or None
        ``None`` when the copy is incomplete, and when the shipped
        manifest did not read: with nothing to check against, no directory
        can be called complete.
    """
    if not DOTPAD_SDK_FILES:
        return None
    candidate = (
        Path(directory).expanduser() if directory is not None else dotpad_sdk_dir()
    )
    for relative, expected in DOTPAD_SDK_FILES.items():
        target = candidate.joinpath(*relative.split("/"))
        try:
            if target.stat().st_size != expected.bytes:
                return None
        except OSError:
            return None
    return candidate


def dotpad_sdk_dependency(
    directory: Path, *, lib_prefix: Optional[str], include_version: bool
):
    """An ``HTMLDependency`` that copies a local SDK beside a saved document.

    ``htmltools`` materialises it into ``<lib_prefix>/dotpad-sdk-<version>/``
    when the document is saved, and its ``head`` declares the two globals
    with that relative path, so the saved page finds the copy wherever the
    folder is moved to, as long as the two move together.

    Parameters
    ----------
    directory : pathlib.Path
        A complete copy, as returned by :func:`dotpad_sdk_path`.
    lib_prefix : str or None
        The ``lib_dir`` the document is saved with.
    include_version : bool
        Whether the dependency folder name carries the version, as the
        document's other dependencies do.

    Returns
    -------
    htmltools.HTMLDependency
    """
    from htmltools import HTMLDependency, tags

    dependency = HTMLDependency(
        name=_DEPENDENCY_NAME,
        version=DOTPAD_SDK_VERSION,
        source={"subdir": str(directory)},
        all_files=True,
    )
    href = dependency.source_path_map(
        lib_prefix=lib_prefix, include_version=include_version
    )["href"]
    config = DotPadSdkConfig(
        sdk_url=f"{href}/{DOTPAD_SDK_MODULE}",
        asset_base_url=f"{href}/{DOTPAD_SDK_ASSET_DIR}",
    )
    script = dotpad_config_script(config)
    return HTMLDependency(
        name=_DEPENDENCY_NAME,
        version=DOTPAD_SDK_VERSION,
        source={"subdir": str(directory)},
        all_files=True,
        head=tags.script(script, type="text/javascript"),
    )


def local_dotpad_sdk_dependency(
    *,
    use_cdn,
    lib_prefix: Optional[str],
    include_version: bool,
):
    """The dependency that bundles a downloaded SDK with a document going offline.

    Applies only to ``use_cdn=False``: that is the document whose reader
    has no network, and the one whose ``lib/`` folder already travels
    with it. A page that names its own copy by URL keeps that -- either
    setting, alone or together, wins over a local directory -- and a
    session that never downloaded the SDK is left exactly as before.

    Either setting, not only the module's. This dependency and the URL
    one write the same globals and the later wins in the browser, so a
    document carrying both with only the engine's URL configured would
    load the module from ``lib/`` and the engine from that URL: the
    offline copy's worst half, and the network dependency
    ``use_cdn=False`` exists to remove.

    The caller puts it first in the document. htmltools renders
    dependency heads in document order, so that is what places the
    globals above the bundle's ``<script>``, as the URL path already does.

    Parameters
    ----------
    use_cdn : bool or {"auto"}
        The document's resolved ``use_cdn``.
    lib_prefix : str or None
        The ``lib_dir`` it will be saved with.
    include_version : bool
        Whether its dependency folders carry a version.

    Returns
    -------
    htmltools.HTMLDependency or None
        The dependency to lead the document with, or ``None`` when the
        document should carry no copy.
    """
    if use_cdn is not False:
        return None
    configured = get_dotpad_sdk()
    if configured.sdk_url is not None or configured.asset_base_url is not None:
        return None
    local = dotpad_sdk_path()
    if local is None:
        return None
    return dotpad_sdk_dependency(
        local, lib_prefix=lib_prefix, include_version=include_version
    )
