"""Tests for CDN version resolution.

Emitting the mutable ``maidr@latest`` dist-tag let browsers replay a
week-old ``maidr.js`` (jsDelivr serves that URL with a 7-day
``max-age``).  These tests pin down the fix: ``latest`` is resolved to a
concrete version in Python and the emitted URL carries it, so the
browser's cache key changes on every release.
"""

from __future__ import annotations

import io
import json
import time

import matplotlib.pyplot as plt
import pytest

import maidr
from maidr.util import dependencies


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bar_plot():
    fig, ax = plt.subplots()
    ax.bar(["A", "B", "C"], [1, 2, 3])
    yield fig
    plt.close(fig)


@pytest.fixture
def resolvable(monkeypatch):
    """Allow resolution and stub the network with a recorded response.

    Returns the list of requested URLs so tests can assert how many
    round trips actually happened.
    """
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)

    calls: list[str] = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return _json_response({"version": "9.9.9", "latest": "9.9.9"})

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)
    yield calls
    dependencies.set_cdn_version(None)


class _FakeResponse(io.BytesIO):
    """Minimal ``urlopen`` stand-in supporting the ``with`` protocol."""

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _json_response(payload: dict) -> _FakeResponse:
    return _FakeResponse(json.dumps(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# Explicit pins
# ---------------------------------------------------------------------------


def test_set_cdn_version_pins_concrete_version():
    maidr.set_cdn_version("3.74.0")
    assert dependencies.get_cdn_version() == "3.74.0"
    assert (
        dependencies.maidr_js_cdn_url()
        == "https://cdn.jsdelivr.net/npm/maidr@3.74.0/dist/maidr.js"
    )
    assert (
        dependencies.maidr_css_cdn_url()
        == "https://cdn.jsdelivr.net/npm/maidr@3.74.0/dist/maidr.css"
    )


def test_set_cdn_version_accepts_v_prefix():
    maidr.set_cdn_version("v3.74.0")
    assert dependencies.get_cdn_version() == "3.74.0"


def test_set_cdn_version_accepts_prerelease():
    maidr.set_cdn_version("3.74.0-beta.1")
    assert dependencies.get_cdn_version() == "3.74.0-beta.1"


def test_latest_tag_opts_out_of_resolution(monkeypatch):
    """``latest`` keeps the legacy URL and makes no network request."""

    def explode(*_args, **_kwargs):
        raise AssertionError("resolution must not run when pinned to 'latest'")

    monkeypatch.setattr(dependencies, "urlopen", explode)
    maidr.set_cdn_version("latest")

    assert dependencies.get_cdn_version() == "latest"
    assert dependencies.maidr_js_cdn_url() == dependencies.MAIDR_JS_CDN_URL


def test_bundled_tag_uses_shipped_version(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("resolution must not run when pinned to 'bundled'")

    monkeypatch.setattr(dependencies, "urlopen", explode)
    maidr.set_cdn_version("bundled")

    assert dependencies.get_cdn_version() == dependencies.maidr_js_version()


def test_env_var_pins_version(monkeypatch):
    monkeypatch.setenv(dependencies.CDN_VERSION_ENV_VAR, "3.70.1")
    dependencies.set_cdn_version(None)
    assert dependencies.get_cdn_version() == "3.70.1"


def test_set_cdn_version_overrides_env_var(monkeypatch):
    monkeypatch.setenv(dependencies.CDN_VERSION_ENV_VAR, "3.70.1")
    maidr.set_cdn_version("3.74.0")
    assert dependencies.get_cdn_version() == "3.74.0"


@pytest.mark.parametrize(
    "version",
    [
        "3.74.0",
        "3.74.0-rc.1",
        "3.74.0+build.5",
        "3.74.0-rc.1+build.5",
        "10.0.123",
    ],
)
def test_version_regex_accepts_real_semver(version):
    assert dependencies._VERSION_RE.match(version)


@pytest.mark.parametrize(
    "version",
    ["3.74", "3.74.0.post1", "v3.74.0", "3.74.0-", "3.74.0+", "", "3.74.0 "],
)
def test_version_regex_rejects_non_semver(version):
    assert dependencies._VERSION_RE.match(version) is None


def test_version_regex_does_not_backtrack_catastrophically():
    """Guard against the ReDoS shape CodeQL flagged.

    An earlier ``(?:[-+.][0-9A-Za-z.-]+)*`` let ``-`` and ``.`` both open
    the repeated group and appear inside it, so this input had
    exponentially many parses. The rewritten pattern is linear, so a
    rejection is effectively instant.
    """
    pathological = "9.9.9+" + "--" * 5_000 + "!"

    start = time.perf_counter()
    assert dependencies._VERSION_RE.match(pathological) is None
    assert time.perf_counter() - start < 1.0, "regex is backtracking"


@pytest.mark.parametrize(
    "hostile",
    [
        "../../../evil",
        "3.74.0/../../other",
        "latest?cb=1",
        "3.74.0 && rm -rf /",
        "https://evil.example.com/x.js",
        "not-a-version",
    ],
)
def test_invalid_pin_never_reaches_the_url(hostile, resolvable):
    """A bad pin is ignored rather than spliced into the CDN URL."""
    maidr.set_cdn_version(hostile)
    url = dependencies.maidr_js_cdn_url()

    assert hostile not in url
    # Falls through to normal resolution, which the fixture stubs.
    assert url == "https://cdn.jsdelivr.net/npm/maidr@9.9.9/dist/maidr.js"


# ---------------------------------------------------------------------------
# Network resolution
# ---------------------------------------------------------------------------


def test_latest_is_resolved_to_a_concrete_version(resolvable):
    assert dependencies.get_cdn_version() == "9.9.9"
    assert (
        dependencies.maidr_js_cdn_url()
        == "https://cdn.jsdelivr.net/npm/maidr@9.9.9/dist/maidr.js"
    )
    assert len(resolvable) == 1, "resolution should need a single round trip"


def test_resolution_is_cached_for_the_process(resolvable):
    for _ in range(5):
        dependencies.maidr_js_cdn_url()
        dependencies.maidr_css_cdn_url()

    assert len(resolvable) == 1, "version lookup must not repeat per render"


def test_reset_cache_forces_a_new_lookup(resolvable):
    dependencies.get_cdn_version()
    dependencies.reset_cdn_version_cache()
    dependencies.get_cdn_version()

    assert len(resolvable) == 2


def test_falls_back_to_npm_registry_when_jsdelivr_fails(monkeypatch):
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    calls: list[str] = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        if "jsdelivr" in request.full_url:
            raise OSError("jsDelivr unreachable")
        return _json_response({"latest": "4.1.0"})

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)

    assert dependencies.get_cdn_version() == "4.1.0"
    assert len(calls) == 2


def test_offline_falls_back_to_latest_tag(monkeypatch):
    """No network: the URL degrades to the historical ``@latest`` form."""
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    calls: list[str] = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        raise OSError("network is unreachable")

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)

    assert dependencies.maidr_js_cdn_url() == dependencies.MAIDR_JS_CDN_URL
    # Failure is cached too, so an offline session does not stall on a
    # doomed request for every figure it renders.
    dependencies.maidr_js_cdn_url()
    dependencies.maidr_css_cdn_url()
    assert len(calls) == len(dependencies._RESOLVER_ENDPOINTS)


def test_malformed_resolver_response_falls_back(monkeypatch):
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)

    def fake_urlopen(request, timeout=None):
        return _FakeResponse(b"<!DOCTYPE html><html>error</html>")

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)
    assert dependencies.get_cdn_version() == "latest"


def test_hostile_resolver_version_is_rejected(monkeypatch):
    """A compromised resolver cannot steer the URL at another path."""
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)

    def fake_urlopen(request, timeout=None):
        return _json_response({"version": "../../evil", "latest": "../../evil"})

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)

    assert dependencies.get_cdn_version() == "latest"
    assert "evil" not in dependencies.maidr_js_cdn_url()


def test_timeout_env_var_is_honoured(monkeypatch):
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    monkeypatch.setenv(dependencies.CDN_TIMEOUT_ENV_VAR, "0.25")
    dependencies.set_cdn_version(None)
    seen: list[float | None] = []

    def fake_urlopen(request, timeout=None):
        seen.append(timeout)
        return _json_response({"version": "9.9.9"})

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)
    dependencies.get_cdn_version()

    assert seen == [0.25]


@pytest.mark.parametrize("bad", ["", "abc", "-1", "0"])
def test_invalid_timeout_falls_back_to_default(bad, monkeypatch):
    monkeypatch.setenv(dependencies.CDN_TIMEOUT_ENV_VAR, bad)
    assert dependencies._cdn_timeout() == dependencies._DEFAULT_CDN_TIMEOUT


# ---------------------------------------------------------------------------
# End-to-end: emitted HTML
# ---------------------------------------------------------------------------


def test_save_html_use_cdn_true_emits_versioned_url(bar_plot, tmp_path):
    maidr.set_cdn_version("3.74.0")
    out = tmp_path / "plot.html"
    maidr.save_html(bar_plot, file=str(out), use_cdn=True)

    contents = out.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/npm/maidr@3.74.0/dist/maidr.js" in contents
    assert "cdn.jsdelivr.net/npm/maidr@3.74.0/dist/maidr.css" in contents
    assert "maidr@latest" not in contents, (
        "the mutable @latest dist-tag must not survive into the output"
    )


def test_save_html_use_cdn_auto_emits_versioned_url(bar_plot, tmp_path):
    maidr.set_cdn_version("3.74.0")
    out = tmp_path / "plot.html"
    maidr.save_html(bar_plot, file=str(out), use_cdn="auto")

    contents = out.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/npm/maidr@3.74.0/dist/maidr.js" in contents
    assert "maidr@latest" not in contents
    # The offline fallback to the bundled copy must still be wired up.
    assert f"lib/maidr-{dependencies.maidr_js_version()}/maidr.js" in contents


def test_render_use_cdn_false_never_resolves(bar_plot, monkeypatch):
    """Offline rendering must not make a version-lookup request."""
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)

    def explode(*_args, **_kwargs):
        raise AssertionError("use_cdn=False must not touch the network")

    monkeypatch.setattr(dependencies, "urlopen", explode)
    maidr.render(bar_plot, use_cdn=False)


def test_dedup_selector_matches_the_emitted_script_src(bar_plot, tmp_path):
    """The ``querySelector`` guard must use the same URL as the ``src``."""
    maidr.set_cdn_version("3.74.0")
    out = tmp_path / "plot.html"
    maidr.save_html(bar_plot, file=str(out), use_cdn=True)

    contents = out.read_text(encoding="utf-8")
    expected = "https://cdn.jsdelivr.net/npm/maidr@3.74.0/dist/maidr.js"
    assert f'script[src=\\"{expected}\\"]' in contents or (
        f'script[src="{expected}"]' in contents
    )
