"""Where a document finds the DotPad SDK, and how a copy travels with it.

``maidr.js`` loads the DotPad tactile-display SDK from a CDN the first time a
DotPad connects -- the one path a ``use_cdn=False`` document still takes to
the network. ``maidr.util.dotpad`` closes it two ways: a URL the session
names travels into every document as the globals ``maidr.js`` reads, and a
copy downloaded with ``download_dotpad_sdk()`` rides along in ``lib/``
beside a saved offline document.

The download is exercised against a fake manifest and a fake fetch, so no
test reaches the network; the real pins are checked for shape, and against
the shipped ``maidr/static/dotpad-sdk.json`` they are read from.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402
from maidr.core import Maidr  # noqa: E402
from maidr.util import dotpad, warn  # noqa: E402

SDK_URL = f"https://intranet.example/dotpad/{dotpad.DOTPAD_SDK_MODULE}"
ASSET_URL = "https://intranet.example/dotpad/lib/"

#: The folder ``save_html`` copies a downloaded SDK into, beside a document.
SDK_FOLDER = f"dotpad-sdk-{dotpad.DOTPAD_SDK_VERSION}"
MODULE = dotpad.DOTPAD_SDK_MODULE

PINS_PATH = (
    Path(maidr.__file__).resolve().parent / "static" / dotpad.DOTPAD_SDK_PINS_FILENAME
)


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch):
    """Every test starts unconfigured, whatever the process or shell says."""
    for name in (
        dotpad.DOTPAD_SDK_URL_ENV_VAR,
        dotpad.DOTPAD_ASSET_BASE_URL_ENV_VAR,
        dotpad.DOTPAD_SDK_DIR_ENV_VAR,
    ):
        monkeypatch.delenv(name, raising=False)
    dotpad.set_dotpad_sdk()
    yield
    dotpad.set_dotpad_sdk()


@pytest.fixture
def fake_sdk(monkeypatch):
    """A three-file stand-in for the real manifest, with its bytes."""
    contents = {
        MODULE: b"export class DotPadSDK {}\n",
        "lib/liblouis.js": b"// liblouis\n",
        "lib/liblouis.data": b"tables" * 100,
    }
    files = {
        name: dotpad.DotPadSdkFile(len(data), hashlib.sha256(data).hexdigest())
        for name, data in contents.items()
    }
    monkeypatch.setattr(dotpad, "DOTPAD_SDK_FILES", files)
    return contents


@pytest.fixture
def local_sdk(fake_sdk, tmp_path, monkeypatch) -> Path:
    """A complete downloaded copy, where ``dotpad_sdk_dir()`` looks."""
    directory = tmp_path / "sdk"
    for name, data in fake_sdk.items():
        target = directory.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    monkeypatch.setenv(dotpad.DOTPAD_SDK_DIR_ENV_VAR, str(directory))
    return directory


@pytest.fixture
def figure():
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    yield fig
    plt.close(fig)


# ---------------------------------------------------------------------------
# The pins
# ---------------------------------------------------------------------------


def test_the_pins_describe_one_commit_of_the_pinned_repository():
    assert re.fullmatch(r"[0-9a-f]{40}", dotpad.DOTPAD_SDK_COMMIT)
    # jsDelivr serves a GitHub repository at ``gh/<owner>/<repo>@<commit>``,
    # whichever repository the manifest names.
    github = "https://github.com/"
    assert dotpad.DOTPAD_SDK_REPOSITORY.startswith(github)
    owner_repo = dotpad.DOTPAD_SDK_REPOSITORY[len(github) :].rstrip("/")
    assert re.fullmatch(r"[\w.-]+/[\w.-]+", owner_repo)
    assert dotpad.DOTPAD_SDK_BASE_URL == (
        f"https://cdn.jsdelivr.net/gh/{owner_repo}@"
        f"{dotpad.DOTPAD_SDK_COMMIT}/Web/{dotpad.DOTPAD_SDK_VERSION}/"
    )
    assert dotpad.DOTPAD_SDK_MODULE == f"DotPadSDK-{dotpad.DOTPAD_SDK_VERSION}.js"
    names = set(dotpad.DOTPAD_SDK_FILES)
    assert dotpad.DOTPAD_SDK_MODULE in names
    for engine in ("liblouis.js", "liblouis.wasm", "liblouis.data"):
        assert dotpad.DOTPAD_SDK_ASSET_DIR + engine in names
    for name, entry in dotpad.DOTPAD_SDK_FILES.items():
        assert not name.startswith("/")
        assert entry.bytes > 0
        assert re.fullmatch(r"[0-9a-f]{64}", entry.sha256)


def test_the_pins_are_the_shipped_manifest():
    # Read independently of the module, so a constant that stopped tracking
    # the file -- or a file the wheel stopped shipping -- shows up here.
    manifest = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    assert dotpad.DOTPAD_SDK_VERSION == manifest["version"]
    assert dotpad.DOTPAD_SDK_REPOSITORY == manifest["repository"]
    assert dotpad.DOTPAD_SDK_COMMIT == manifest["commit"]
    assert dotpad.DOTPAD_SDK_BASE_URL == manifest["baseUrl"]
    assert dotpad.DOTPAD_SDK_MODULE == manifest["module"]
    assert dotpad.DOTPAD_SDK_ASSET_DIR == manifest["assetDir"]
    assert set(dotpad.DOTPAD_SDK_FILES) == set(manifest["files"])
    for name, entry in manifest["files"].items():
        pinned = dotpad.DOTPAD_SDK_FILES[name]
        assert isinstance(pinned, dotpad.DotPadSdkFile)
        assert pinned.bytes == entry["bytes"]
        assert pinned.sha256 == entry["sha256"]
    # The mirror records which vendor archive its files were checked against.
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["upstream"]["commit"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["upstream"]["sha256"])


def test_the_pinned_liblouis_data_is_the_intact_one():
    # The corrupt copy was 7,685 bytes short; this size is the vendor's own
    # release, restored at the pinned commit.
    assert dotpad.DOTPAD_SDK_FILES["lib/liblouis.data"].bytes == 13_751_594


def test_the_lgpl_notice_and_wrapper_sources_travel_with_the_engine():
    # What the vendor asks of anyone who redistributes the SDK.
    names = set(dotpad.DOTPAD_SDK_FILES)
    assert "lib/LICENSES/liblouis-LGPL-2.1.txt" in names
    assert "lib/liblouis-web/liblouis_web.c" in names
    assert "lib/liblouis-web/build_liblouis_web.sh" in names


# ---------------------------------------------------------------------------
# A manifest that will not read
# ---------------------------------------------------------------------------
#
# The manifest comes from outside this repository: the bundle refresh copies
# whatever ``dist/dotpad-sdk.json`` the pinned ``maidr.js`` ships, and commits
# it. A release that renamed a field would reach an installed wheel, and this
# module is imported by ``maidr/__init__.py`` -- so a raised exception here
# would be ``import maidr`` failing, for every user, over a tactile display
# most of them do not own. It warns and goes inert instead, the way an
# unreadable bundled ``VERSION`` does.


def _manifest_without(field: str) -> dict:
    """The real manifest, with one top-level field dropped."""
    manifest = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    del manifest[field]
    return manifest


def _manifest_without_a_digest() -> dict:
    """The real manifest, with one file's ``sha256`` dropped.

    The drift that motivates the check: a future ``maidr.js`` release
    renaming a per-file field, which a top-level key check would miss.
    """
    manifest = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    del manifest["files"]["lib/liblouis.wasm"]["sha256"]
    return manifest


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param("not a manifest", id="not-an-object"),
        pytest.param({}, id="empty"),
        pytest.param(_manifest_without("version"), id="no-version"),
        pytest.param(_manifest_without("baseUrl"), id="no-base-url"),
        pytest.param(_manifest_without("files"), id="no-files"),
        pytest.param(_manifest_without_a_digest(), id="no-file-digest"),
    ],
)
def test_a_manifest_of_the_wrong_shape_is_named_as_such(broken):
    with pytest.raises(ValueError):
        dotpad._parse_pins(broken)


def test_a_file_entry_of_the_wrong_type_is_named_as_such():
    manifest = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    manifest["files"]["lib/liblouis.wasm"]["bytes"] = "171970"
    with pytest.raises(ValueError, match="liblouis.wasm"):
        dotpad._parse_pins(manifest)


@pytest.mark.parametrize(
    "escape",
    [
        "../../../.ssh/authorized_keys",
        "lib/../../outside.js",
        "/etc/passwd",
        "~/.bashrc",
        "C:/Windows/System32/drivers/etc/hosts",
        "lib\\..\\..\\outside.js",
        "lib//liblouis.js",
        "./liblouis.js",
    ],
)
def test_a_path_that_leaves_its_directory_is_refused(escape):
    # Each path is joined onto the download directory to decide where the
    # fetched bytes are written, so a manifest could otherwise name any file
    # on the machine. The download is the one place this package writes
    # files it did not name itself.
    assert not dotpad._path_is_safe(escape)
    manifest = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    manifest["files"][escape] = manifest["files"]["lib/liblouis.wasm"]
    with pytest.raises(ValueError, match="inside the directory"):
        dotpad._parse_pins(manifest)


def test_the_paths_the_manifest_names_are_allowed():
    for relative in dotpad.DOTPAD_SDK_FILES:
        assert dotpad._path_is_safe(relative)


def test_a_digest_of_the_wrong_shape_is_named_at_the_manifest():
    # A truncated or non-hex digest can only ever fail the download; saying
    # so here names the manifest instead of a file that never matches.
    manifest = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    manifest["files"]["lib/liblouis.wasm"]["sha256"] = "abc123"
    with pytest.raises(ValueError, match="liblouis.wasm"):
        dotpad._parse_pins(manifest)


def test_an_unreadable_manifest_warns_and_leaves_the_pins_inert(monkeypatch, caplog):
    class _Missing:
        def joinpath(self, *parts):
            return self

        def read_text(self, encoding=None):
            raise FileNotFoundError("no dotpad-sdk.json")

    monkeypatch.setattr(dotpad, "files", lambda package: _Missing())
    warn._warned_keys.clear()
    with caplog.at_level(logging.WARNING):
        pins = dotpad._read_pins()
    assert pins["files"] == {}
    assert pins["version"] == "0.0.0"
    assert dotpad.DOTPAD_SDK_PINS_FILENAME in caplog.text
    assert "reinstall py-maidr" in caplog.text.lower()


def test_without_pins_no_directory_counts_as_a_copy(monkeypatch, tmp_path):
    # An empty manifest must not make every directory look complete: the
    # check is a loop over the pinned files, and a loop over nothing passes.
    monkeypatch.setattr(dotpad, "DOTPAD_SDK_FILES", {})
    assert dotpad.dotpad_sdk_path(tmp_path) is None


def test_without_pins_the_download_says_what_is_broken(monkeypatch, tmp_path):
    monkeypatch.setattr(dotpad, "DOTPAD_SDK_FILES", {})
    with pytest.raises(RuntimeError, match=dotpad.DOTPAD_SDK_PINS_FILENAME):
        dotpad.download_dotpad_sdk(tmp_path)


# ---------------------------------------------------------------------------
# Naming a copy by URL
# ---------------------------------------------------------------------------


def test_nothing_is_configured_by_default():
    assert maidr.get_dotpad_sdk() == (None, None)
    assert dotpad.dotpad_config_script() is None
    assert dotpad.dotpad_config_tag() is None


def test_the_environment_variables_carry_the_names_of_the_globals(monkeypatch):
    monkeypatch.setenv("MAIDR_DOTPAD_SDK_URL", SDK_URL)
    monkeypatch.setenv("MAIDR_DOTPAD_ASSET_BASE_URL", ASSET_URL)
    assert maidr.get_dotpad_sdk() == (SDK_URL, ASSET_URL)


def test_a_setter_wins_over_the_environment_and_clears_back_to_it(monkeypatch):
    monkeypatch.setenv("MAIDR_DOTPAD_SDK_URL", "/from-env.js")
    maidr.set_dotpad_sdk("/from-python.js", ASSET_URL)
    assert maidr.get_dotpad_sdk() == ("/from-python.js", ASSET_URL)
    maidr.set_dotpad_sdk()
    assert maidr.get_dotpad_sdk() == ("/from-env.js", None)


def test_an_empty_value_counts_as_unset(monkeypatch):
    monkeypatch.setenv("MAIDR_DOTPAD_SDK_URL", "  ")
    maidr.set_dotpad_sdk("", "")
    assert maidr.get_dotpad_sdk() == (None, None)


def test_the_script_declares_only_what_is_configured():
    script = dotpad.dotpad_config_script(dotpad.DotPadSdkConfig(SDK_URL, None))
    assert script == f'window.MAIDR_DOTPAD_SDK_URL = "{SDK_URL}";'

    both = dotpad.dotpad_config_script(dotpad.DotPadSdkConfig("/a.js", "/lib/"))
    assert both.splitlines() == [
        'window.MAIDR_DOTPAD_SDK_URL = "/a.js";',
        'window.MAIDR_DOTPAD_ASSET_BASE_URL = "/lib/";',
    ]


def test_a_url_cannot_break_out_of_the_script_element():
    # ``</`` ends a <script> for the HTML parser whatever the JavaScript
    # around it says, and a quote would end the literal.
    hostile = '/x".js</script><script>alert(1)</script>'
    tag = dotpad.dotpad_config_tag(dotpad.DotPadSdkConfig(hostile, None))
    html = str(tag)
    assert html.count("</script>") == 1
    assert '\\"' in html
    assert "<\\/script>" in html
    # And it round-trips: the browser sees the string that was configured.
    literal = re.search(r"window\.MAIDR_DOTPAD_SDK_URL = (.*);", html).group(1)
    assert json.loads(literal.replace("<\\/", "</")) == hostile


class _Scripts(HTMLParser):
    """The scripts of a page, in order: their ``src`` or their text."""

    def __init__(self):
        super().__init__()
        self.scripts: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            src = dict(attrs).get("src")
            self.scripts.append(src or "")
            self._in_script = src is None

    def handle_data(self, data):
        if self._in_script:
            self.scripts[-1] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False


def _scripts(html: str) -> list[str]:
    parser = _Scripts()
    parser.feed(html)
    return parser.scripts


def _declaration_precedes_the_bundle(html: str) -> bool:
    scripts = _scripts(html)
    declared = next(
        i for i, s in enumerate(scripts) if "window.MAIDR_DOTPAD_SDK_URL" in s
    )
    bundle = next(
        i for i, s in enumerate(scripts) if "maidr.js" in s or "__maidrJsSource" in s
    )
    return declared < bundle


@pytest.mark.parametrize("use_cdn", [False, "auto", True])
def test_a_saved_document_declares_the_globals_ahead_of_the_bundle(
    figure, tmp_path, use_cdn, monkeypatch
):
    monkeypatch.setenv("MAIDR_CDN_VERSION", "bundled")
    maidr.set_dotpad_sdk(SDK_URL, ASSET_URL)
    out = tmp_path / "chart.html"
    maidr.save_html(figure, str(out), use_cdn=use_cdn)
    html = out.read_text(encoding="utf-8")
    assert f'window.MAIDR_DOTPAD_SDK_URL = "{SDK_URL}";' in html
    assert f'window.MAIDR_DOTPAD_ASSET_BASE_URL = "{ASSET_URL}";' in html
    assert _declaration_precedes_the_bundle(html)


def test_an_iframed_render_carries_the_globals_inside_the_frame(figure, monkeypatch):
    monkeypatch.setenv("MAIDR_CDN_VERSION", "bundled")
    monkeypatch.setattr(dotpad.os.environ, "get", dotpad.os.environ.get)
    maidr.set_dotpad_sdk(SDK_URL)
    from maidr.util.environment import Environment

    monkeypatch.setattr(Environment, "is_flask", staticmethod(lambda: True))
    html = str(Maidr(figure).render(use_cdn=False).get_html_string())
    assert "<iframe" in html
    # Inside ``srcdoc`` the quotes are entity-escaped; the name survives.
    assert "window.MAIDR_DOTPAD_SDK_URL" in html


plotly = pytest.importorskip("plotly", reason="the plotly extra is not installed")


def test_a_plotly_document_declares_the_globals_too(tmp_path, monkeypatch):
    import plotly.graph_objects as go

    monkeypatch.setenv("MAIDR_CDN_VERSION", "bundled")
    maidr.set_dotpad_sdk(SDK_URL, ASSET_URL)
    fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
    out = tmp_path / "plotly.html"
    maidr.save_html(fig, str(out), use_cdn=False)
    html = out.read_text(encoding="utf-8")
    assert f'window.MAIDR_DOTPAD_SDK_URL = "{SDK_URL}";' in html
    assert _declaration_precedes_the_bundle(html)


# ---------------------------------------------------------------------------
# Carrying a copy
# ---------------------------------------------------------------------------


def test_the_default_directory_is_per_user_and_versioned(monkeypatch):
    directory = dotpad.dotpad_sdk_dir()
    assert directory.name == dotpad.DOTPAD_SDK_VERSION
    assert directory.parent.name == "dotpad-sdk"
    assert directory.parent.parent.name == "maidr"

    monkeypatch.setenv("MAIDR_DOTPAD_SDK_DIR", "~/elsewhere/sdk")
    assert dotpad.dotpad_sdk_dir() == Path("~/elsewhere/sdk").expanduser()


def test_download_writes_every_file_verified_and_a_manifest(
    fake_sdk, tmp_path, monkeypatch
):
    fetched: list[str] = []

    def fetch(url, timeout):
        fetched.append(url)
        assert url.startswith(dotpad.DOTPAD_SDK_BASE_URL)
        return fake_sdk[url[len(dotpad.DOTPAD_SDK_BASE_URL) :]]

    monkeypatch.setattr(dotpad, "_fetch", fetch)
    target = tmp_path / "sdk"

    assert maidr.download_dotpad_sdk(target) == target
    for name, data in fake_sdk.items():
        assert target.joinpath(*name.split("/")).read_bytes() == data
    assert len(fetched) == len(fake_sdk)
    assert not list(target.rglob("*.part"))

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["commit"] == dotpad.DOTPAD_SDK_COMMIT
    assert manifest["module"] == dotpad.DOTPAD_SDK_MODULE
    assert set(manifest["files"]) == set(fake_sdk)

    # A second call finds every file in place and fetches nothing.
    maidr.download_dotpad_sdk(target)
    assert len(fetched) == len(fake_sdk)

    # Unless told to.
    maidr.download_dotpad_sdk(target, force=True)
    assert len(fetched) == 2 * len(fake_sdk)


def test_download_defaults_to_the_configured_directory(fake_sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("MAIDR_DOTPAD_SDK_DIR", str(tmp_path / "configured"))
    monkeypatch.setattr(
        dotpad,
        "_fetch",
        lambda url, timeout: fake_sdk[url[len(dotpad.DOTPAD_SDK_BASE_URL) :]],
    )
    assert maidr.download_dotpad_sdk() == tmp_path / "configured"
    assert maidr.dotpad_sdk_path() == tmp_path / "configured"


def test_a_corrupt_download_is_refused_and_nothing_is_written(
    fake_sdk, tmp_path, monkeypatch
):
    def fetch(url, timeout):
        data = fake_sdk[url[len(dotpad.DOTPAD_SDK_BASE_URL) :]]
        # The failure that motivated the pin: a file that arrives short.
        return data[:-1] if url.endswith("liblouis.data") else data

    monkeypatch.setattr(dotpad, "_fetch", fetch)
    target = tmp_path / "sdk"

    with pytest.raises(
        RuntimeError, match=r"liblouis\.data .* expected 600 bytes, got 599"
    ):
        maidr.download_dotpad_sdk(target)
    assert not (target / "lib" / "liblouis.data").exists()
    assert not (target / "manifest.json").exists()
    assert maidr.dotpad_sdk_path(target) is None


def test_a_same_size_corruption_is_caught_by_its_digest(
    fake_sdk, tmp_path, monkeypatch
):
    def fetch(url, timeout):
        data = fake_sdk[url[len(dotpad.DOTPAD_SDK_BASE_URL) :]]
        return data[:-1] + b"X" if url.endswith("liblouis.js") else data

    monkeypatch.setattr(dotpad, "_fetch", fetch)
    with pytest.raises(RuntimeError, match="expected sha256"):
        maidr.download_dotpad_sdk(tmp_path / "sdk")


def test_a_copy_is_complete_only_when_every_file_is_at_its_size(fake_sdk, local_sdk):
    assert maidr.dotpad_sdk_path() == local_sdk
    assert maidr.dotpad_sdk_path(local_sdk) == local_sdk

    (local_sdk / "lib" / "liblouis.data").write_bytes(b"short")
    assert maidr.dotpad_sdk_path() is None

    (local_sdk / "lib" / "liblouis.data").unlink()
    assert maidr.dotpad_sdk_path() is None


def test_nothing_is_there_until_it_is_downloaded(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIDR_DOTPAD_SDK_DIR", str(tmp_path / "missing"))
    assert maidr.dotpad_sdk_path() is None


# ---------------------------------------------------------------------------
# A downloaded copy rides along with an offline document
# ---------------------------------------------------------------------------


def test_an_offline_document_carries_the_copy_and_points_at_it(
    figure, local_sdk, tmp_path
):
    out = tmp_path / "out" / "chart.html"
    out.parent.mkdir()
    maidr.save_html(figure, str(out), use_cdn=False)

    copied = out.parent / "lib" / SDK_FOLDER
    assert (copied / MODULE).read_bytes() == (local_sdk / MODULE).read_bytes()
    assert (copied / "lib" / "liblouis.data").is_file()

    html = out.read_text(encoding="utf-8")
    assert f'window.MAIDR_DOTPAD_SDK_URL = "lib/{SDK_FOLDER}/{MODULE}";' in html
    assert f'window.MAIDR_DOTPAD_ASSET_BASE_URL = "lib/{SDK_FOLDER}/lib/";' in html


def test_the_copy_follows_the_lib_dir_and_version_settings(figure, local_sdk, tmp_path):
    out = tmp_path / "chart.html"
    maidr.save_html(
        figure, str(out), use_cdn=False, lib_dir="deps", include_version=False
    )
    assert (tmp_path / "deps" / "dotpad-sdk" / MODULE).is_file()
    html = out.read_text(encoding="utf-8")
    assert f'window.MAIDR_DOTPAD_SDK_URL = "deps/dotpad-sdk/{MODULE}";' in html


@pytest.mark.parametrize("use_cdn", ["auto", True])
def test_only_an_offline_document_carries_the_copy(
    figure, local_sdk, tmp_path, use_cdn, monkeypatch
):
    monkeypatch.setenv("MAIDR_CDN_VERSION", "bundled")
    out = tmp_path / "chart.html"
    maidr.save_html(figure, str(out), use_cdn=use_cdn)
    assert not (tmp_path / "lib" / SDK_FOLDER).exists()
    assert "MAIDR_DOTPAD" not in out.read_text(encoding="utf-8")


def test_a_configured_url_wins_over_a_local_copy(figure, local_sdk, tmp_path):
    maidr.set_dotpad_sdk(SDK_URL)
    out = tmp_path / "chart.html"
    maidr.save_html(figure, str(out), use_cdn=False)
    assert not (tmp_path / "lib" / SDK_FOLDER).exists()
    html = out.read_text(encoding="utf-8")
    assert f'window.MAIDR_DOTPAD_SDK_URL = "{SDK_URL}";' in html
    assert SDK_FOLDER not in html


@pytest.mark.parametrize(
    "configured",
    [(None, ASSET_URL), (SDK_URL, ASSET_URL)],
    ids=["asset-only", "both"],
)
def test_either_url_setting_keeps_a_local_copy_out(
    figure, local_sdk, tmp_path, configured
):
    # Both would write the same globals and the later wins in the browser,
    # so a document carrying both with only the engine's URL configured
    # would load the module from lib/ and the engine from the URL.
    maidr.set_dotpad_sdk(*configured)
    out = tmp_path / "chart.html"
    maidr.save_html(figure, str(out), use_cdn=False)
    assert not (tmp_path / "lib" / SDK_FOLDER).exists()
    html = out.read_text(encoding="utf-8")
    assert html.count("MAIDR_DOTPAD_ASSET_BASE_URL") == 1
    assert f'window.MAIDR_DOTPAD_ASSET_BASE_URL = "{ASSET_URL}";' in html
    assert SDK_FOLDER not in html


def test_a_session_that_never_downloaded_is_left_alone(figure, tmp_path, monkeypatch):
    monkeypatch.setenv("MAIDR_DOTPAD_SDK_DIR", str(tmp_path / "nothing-here"))
    out = tmp_path / "chart.html"
    maidr.save_html(figure, str(out), use_cdn=False)
    assert "MAIDR_DOTPAD" not in out.read_text(encoding="utf-8")
    assert sorted(p.name for p in (tmp_path / "lib").iterdir()) == [
        f"maidr-{maidr.maidr_js_version()}"
    ]


def test_a_plotly_offline_document_carries_the_copy_too(local_sdk, tmp_path):
    import plotly.graph_objects as go

    fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
    out = tmp_path / "plotly.html"
    maidr.save_html(fig, str(out), use_cdn=False)
    assert (tmp_path / "lib" / SDK_FOLDER / MODULE).is_file()
    html = out.read_text(encoding="utf-8")
    assert f'window.MAIDR_DOTPAD_SDK_URL = "lib/{SDK_FOLDER}/{MODULE}";' in html
    assert _declaration_precedes_the_bundle(html)


# ---------------------------------------------------------------------------
# The public surface
# ---------------------------------------------------------------------------


def test_the_helpers_are_part_of_the_package_api():
    for name in (
        "DOTPAD_SDK_VERSION",
        "DotPadSdkConfig",
        "download_dotpad_sdk",
        "dotpad_sdk_dir",
        "dotpad_sdk_path",
        "get_dotpad_sdk",
        "set_dotpad_sdk",
    ):
        assert name in maidr.__all__
        assert hasattr(maidr, name)
