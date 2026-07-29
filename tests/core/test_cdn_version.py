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
import logging
import re
import threading
import time
import warnings
from pathlib import Path

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


def test_latest_tag_opts_out_of_resolution(forbid_network):
    """``latest`` keeps the legacy URL and makes no network request."""
    maidr.set_cdn_version("latest")

    assert dependencies.get_cdn_version() == "latest"
    assert dependencies.maidr_js_cdn_url() == dependencies.MAIDR_JS_CDN_URL


def test_bundled_tag_uses_shipped_version(forbid_network):
    maidr.set_cdn_version("bundled")

    assert dependencies.get_cdn_version() == dependencies.maidr_js_version()


def test_bundled_version_file_is_read_once(monkeypatch):
    """Pinning to ``bundled`` must not re-read VERSION per URL build.

    ``_normalise_version_pin`` runs on every URL build — twice per figure
    — so without the cache this would be a package-resource read per
    call for anyone pinning ``bundled`` (e.g. air-gapped CI).
    """
    dependencies.maidr_js_version.cache_clear()
    reads = {"n": 0}
    real_files = dependencies.files

    def counting_files(*args, **kwargs):
        reads["n"] += 1
        return real_files(*args, **kwargs)

    monkeypatch.setattr(dependencies, "files", counting_files)
    try:
        maidr.set_cdn_version("bundled")
        for _ in range(10):
            dependencies.maidr_js_cdn_url()
            dependencies.maidr_css_cdn_url()
        assert reads["n"] == 1, f"read VERSION {reads['n']} times, expected 1"
    finally:
        # Drop the value cached through the counting stub.
        dependencies.maidr_js_version.cache_clear()


def test_bundled_tag_with_broken_version_stays_offline(monkeypatch, forbid_network):
    """A corrupt bundle must not turn ``bundled`` into a network lookup.

    Choosing ``bundled`` implies staying local, so a missing ``VERSION``
    degrades to ``latest`` rather than resolving over the network.
    """
    monkeypatch.setattr(
        dependencies, "maidr_js_version", lambda: dependencies._UNKNOWN_VERSION
    )
    maidr.set_cdn_version("bundled")

    assert dependencies.get_cdn_version() == dependencies.LATEST_TAG
    assert dependencies.maidr_js_cdn_url() == dependencies.MAIDR_JS_CDN_URL


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


def test_invalid_pin_logs_once_not_once_per_render(resolvable, caplog):
    """A typo'd pin must not log two lines for every figure rendered."""
    maidr.set_cdn_version("3.74")  # missing patch component

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        for _ in range(5):
            dependencies.maidr_js_cdn_url()
            dependencies.maidr_css_cdn_url()

    complaints = [r for r in caplog.records if "invalid CDN version pin" in r.message]
    assert len(complaints) == 1, f"logged {len(complaints)} times, expected 1"


def test_a_second_bad_pin_still_warns(resolvable, caplog):
    """Deduplication is per value, so a new mistake stays audible."""

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        maidr.set_cdn_version("3.74")
        dependencies.maidr_js_cdn_url()
        maidr.set_cdn_version("nonsense")
        dependencies.maidr_js_cdn_url()

    complaints = [r for r in caplog.records if "invalid CDN version pin" in r.message]
    assert len(complaints) == 2


def test_warned_keys_stays_bounded(resolvable):
    """Many distinct bad pins must not grow the dedup set without bound."""
    for i in range(dependencies._MAX_WARNED_KEYS * 3):
        maidr.set_cdn_version(f"bad-{i}")
        dependencies.maidr_js_cdn_url()

    assert len(dependencies._warned_keys) <= dependencies._MAX_WARNED_KEYS


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


def test_no_render_path_references_the_unresolved_constants():
    """The ``@latest`` constants must not leak back into emitted HTML.

    ``MAIDR_JS_CDN_URL`` / ``MAIDR_CSS_CDN_URL`` are kept for backwards
    compatibility and as the lookup's fallback, but a render path that
    reaches for one silently reintroduces the stale-cache bug this module
    exists to fix. Only ``dependencies.py`` itself may name them.
    """
    package_root = Path(dependencies.__file__).resolve().parent.parent
    offenders = [
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*.py")
        if path.resolve() != Path(dependencies.__file__).resolve()
        and re.search(r"MAIDR_(?:JS|CSS)_CDN_URL", path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"{offenders} reference the unresolved @latest CDN constants; "
        "call maidr_js_cdn_url()/maidr_css_cdn_url()/cdn_url() instead"
    )


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

    assert len(seen) == 1
    assert 0 < seen[0] <= 0.25


def test_timeout_is_a_total_budget_across_endpoints(monkeypatch):
    """A fallback endpoint must not double how long a first render blocks."""
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    monkeypatch.setenv(dependencies.CDN_TIMEOUT_ENV_VAR, "2.0")
    dependencies.set_cdn_version(None)
    seen: list[float] = []

    def fake_urlopen(request, timeout=None):
        seen.append(timeout)
        # Burn part of the budget, as a blackholed connection would.
        time.sleep(0.2)
        raise OSError("unreachable")

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)

    assert dependencies.get_cdn_version() == "latest"

    assert len(seen) == len(dependencies._RESOLVER_ENDPOINTS)
    # Each attempt gets only what is left of the budget, so the timeouts
    # shrink. This is the deterministic part of the guarantee; a
    # wall-clock assertion would add nothing but CI flakiness, since the
    # budget bounds the timeouts we hand out, not the scheduler.
    assert seen[1] < seen[0] <= 2.0
    assert sum(seen) < 2.0 * len(seen), "timeouts were not sharing a budget"


def test_budget_exhaustion_skips_remaining_endpoints(monkeypatch):
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    monkeypatch.setenv(dependencies.CDN_TIMEOUT_ENV_VAR, "0.15")
    dependencies.set_cdn_version(None)
    calls: list[str] = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        time.sleep(0.2)  # spends the whole budget on the first attempt
        raise OSError("unreachable")

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)

    assert dependencies.get_cdn_version() == "latest"
    assert len(calls) == 1, "second endpoint should be skipped once spent"


@pytest.mark.parametrize("bad", ["", "abc", "-1", "0", "nan", "inf", "-inf"])
def test_invalid_timeout_falls_back_to_default(bad, monkeypatch):
    monkeypatch.setenv(dependencies.CDN_TIMEOUT_ENV_VAR, bad)
    assert dependencies._cdn_timeout() == dependencies._DEFAULT_CDN_TIMEOUT


def test_oversized_timeout_is_clamped(monkeypatch, caplog):
    """A millisecond-looking value must not hang the first render.

    ``MAIDR_CDN_TIMEOUT=3000`` read as seconds would block for fifty
    minutes before a plot appeared.
    """
    monkeypatch.setenv(dependencies.CDN_TIMEOUT_ENV_VAR, "3000")

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        assert dependencies._cdn_timeout() == dependencies._MAX_CDN_TIMEOUT

    assert any("clamped" in r.message for r in caplog.records), (
        "clamping must be visible, not silent"
    )


def test_timeout_just_under_the_cap_is_honoured(monkeypatch):
    monkeypatch.setenv(dependencies.CDN_TIMEOUT_ENV_VAR, "29")
    assert dependencies._cdn_timeout() == 29.0


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


def test_render_use_cdn_false_never_resolves(bar_plot, monkeypatch, forbid_network):
    """Offline rendering must not make a version-lookup request."""
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
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


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------
#
# The module carries three locks and docstrings that reason explicitly
# about GIL versus free-threaded (PEP 703) behaviour, but single-threaded
# tests cannot exercise any of it.  These drive real contention with a
# barrier so every thread arrives together, and assert on counts rather
# than timing, so they are deterministic rather than flaky.
#
# Their strength differs, and it is worth being precise about which is
# which.  Only the resolution test can currently fail without its lock:
# it was verified by removing the lock and watching 32 threads each make
# their own request.  The two warning tests below cannot, because their
# critical sections are a few bytecodes of pure Python that CPython does
# not preempt -- measured at 0 races in 40 trials of 32 threads at the
# minimum switch interval.  They are kept as forward-looking guards:
# under a free-threaded build (PEP 703) there is no GIL holding those
# sequences together, which is the case the locks were added for.


def _run_concurrently(target, threads=32):
    """Run ``target`` on ``threads`` threads released simultaneously."""
    barrier = threading.Barrier(threads)
    errors: list[BaseException] = []

    def runner():
        try:
            barrier.wait()
            target()
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    workers = [threading.Thread(target=runner) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert not errors, f"worker raised: {errors[:3]}"


def test_concurrent_resolution_makes_one_lookup(monkeypatch):
    """Double-checked locking must not let two threads both resolve.

    This one has teeth: with the lock removed, all 32 threads make their
    own request instead of one.
    """
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    calls: list[str] = []
    calls_lock = threading.Lock()

    def fake_urlopen(request, timeout=None):
        with calls_lock:
            calls.append(request.full_url)
        # Hold the "connection" open briefly. A real lookup takes
        # milliseconds, and that is exactly the window in which a second
        # thread can enter an unguarded critical section — an instant
        # stub closes the window and makes the test prove nothing.
        time.sleep(0.05)
        return _json_response({"version": "9.9.9", "latest": "9.9.9"})

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)

    results: list[str] = []
    results_lock = threading.Lock()

    def resolve():
        value = dependencies.get_cdn_version()
        with results_lock:
            results.append(value)

    _run_concurrently(resolve)

    assert len(calls) == 1, f"resolved {len(calls)} times under contention"
    assert set(results) == {"9.9.9"}, "threads disagreed on the version"


def test_concurrent_warn_once_emits_once(monkeypatch):
    """``_warn_once`` emits once under contention.

    Cannot fail on CPython without its lock (see the note above), so read
    this as a free-threading guard and a smoke test, not as evidence that
    the lock is load-bearing today.
    """
    monkeypatch.setattr(dependencies, "_warned_keys", set())
    emitted: list[tuple] = []
    emit_lock = threading.Lock()

    def record(*args, **_kwargs):
        with emit_lock:
            emitted.append(args)

    monkeypatch.setattr(dependencies._logger, "warning", record)

    _run_concurrently(lambda: dependencies._warn_once("same-key", "msg"))

    assert len(emitted) == 1, f"emitted {len(emitted)} times, expected 1"


def test_concurrent_staleness_warning_emits_once(monkeypatch):
    """``warn_if_bundle_is_stale`` emits once under contention.

    Same caveat as ``test_concurrent_warn_once_emits_once``: the guarded
    sequence is too short for CPython to preempt, so this earns its keep
    on free-threaded builds rather than here.
    """
    monkeypatch.setattr(dependencies, "_bundle_warning_emitted", False)
    monkeypatch.setattr(dependencies, "maidr_js_version", lambda: "3.66.1")
    monkeypatch.setattr(dependencies, "_resolved_cdn_version", "3.74.0")
    monkeypatch.setattr(dependencies, "_resolution_attempted", True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _run_concurrently(dependencies.warn_if_bundle_is_stale)

    stale = [w for w in caught if "bundled copy of maidr.js" in str(w.message)]
    assert len(stale) == 1, f"warned {len(stale)} times, expected 1"


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_blank_pin_clears_rather_than_falling_through(blank, resolvable):
    """A blank pin means "no pin", not "a pin that happens to be unusable"."""
    maidr.set_cdn_version("3.70.1")
    maidr.set_cdn_version(blank)

    assert dependencies._cdn_version_override is None
    assert dependencies.get_cdn_version() == "9.9.9"


def test_bundle_status_type_is_exported():
    """The return type must be reachable for type hints and isinstance."""
    assert maidr.BundleStatus is dependencies.BundleStatus
    assert "BundleStatus" in maidr.__all__


@pytest.mark.parametrize(
    ("lower", "higher"),
    [
        ("3.74.0-rc.1", "3.74.0-rc.2"),
        ("3.74.0-rc.9", "3.74.0-rc.10"),
        ("3.74.0-alpha", "3.74.0-alpha.1"),
        ("3.74.0-alpha.1", "3.74.0-beta"),
        ("3.74.0-1", "3.74.0-alpha"),
        ("3.74.0-rc.1", "3.74.0"),
    ],
)
def test_prerelease_precedence_follows_semver(lower, higher):
    """Semver §11: numeric identifiers compare numerically and rank below
    alphanumeric ones, and a shorter identifier run sorts lower."""
    assert dependencies._version_key(lower) < dependencies._version_key(higher)


def test_build_metadata_is_ignored_for_precedence():
    """Semver §10: build metadata carries no precedence."""
    assert dependencies._version_key("3.74.0+build.1") == dependencies._version_key(
        "3.74.0+build.9"
    )


@pytest.mark.parametrize("bad", ["abc", "-1", "0", "nan", "inf"])
def test_unusable_timeout_is_reported_not_silently_replaced(bad, monkeypatch, caplog):
    """The clamp warns, so the other rejections should too."""
    monkeypatch.setenv(dependencies.CDN_TIMEOUT_ENV_VAR, bad)

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        assert dependencies._cdn_timeout() == dependencies._DEFAULT_CDN_TIMEOUT

    assert caplog.records, f"{bad!r} was replaced with the default in silence"


def test_version_regex_rejects_trailing_newline():
    """``$`` would accept this; ``\\Z`` does not.

    The comment claims parity with the shell guard, so a value Python
    accepts and ``grep`` would treat differently is a real divergence.
    """
    assert dependencies._VERSION_RE.match("3.74.0\n") is None


def test_bundle_status_resolves_even_when_pinned_to_latest(monkeypatch):
    """The documented opt-out does not cover ``bundle_status()``.

    ``MAIDR_CDN_VERSION=latest`` stops URL building from resolving, but
    ``bundle_status()`` ignores pins by design — asking what is published
    has no answer otherwise. Pin the behaviour so the docs and the code
    cannot drift apart.
    """
    monkeypatch.setenv(dependencies.CDN_VERSION_ENV_VAR, dependencies.LATEST_TAG)
    dependencies.set_cdn_version(None)
    calls: list[str] = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return _json_response({"version": "9.9.9", "latest": "9.9.9"})

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)

    assert maidr.bundle_status().published == "9.9.9"
    assert calls, "bundle_status() should resolve despite the pin"

    # ...and resolve=False is the way to keep it quiet.
    dependencies.reset_cdn_version_cache()
    calls.clear()
    assert maidr.bundle_status(resolve=False).published is None
    assert not calls


@pytest.mark.parametrize("value", ["0.5", "3", "15", "29.9"])
def test_ordinary_timeout_passes_through_untouched(value, monkeypatch, caplog):
    """Between the floor and the cap, the value is used as given.

    The boundaries are covered elsewhere; this closes the loop by
    asserting the common case is neither clamped nor complained about.
    """
    monkeypatch.setenv(dependencies.CDN_TIMEOUT_ENV_VAR, value)

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        assert dependencies._cdn_timeout() == float(value)

    assert not caplog.records, f"{value!r} should be accepted silently"


@pytest.mark.parametrize(
    "hostile",
    ["3.74.0-" + "9" * 5000, "9" * 5000 + ".1.0", "3.74.0+" + "a" * 5000],
)
def test_absurdly_long_versions_are_rejected_before_parsing(hostile):
    """A valid *shape* is not enough; size has to be bounded too.

    ``int()`` raises above CPython's 4300-digit conversion limit, so an
    unbounded numeric field would validate, reach the URL, and then
    explode out of ``render()`` during the staleness comparison.
    """
    assert not dependencies._is_valid_version(hostile)
    assert dependencies._version_key(hostile) is None


def test_version_key_never_raises_on_a_shape_that_slips_through(monkeypatch):
    """Defence in depth: parsing is advisory and must not break a render."""
    monkeypatch.setattr(dependencies, "_MAX_VERSION_LEN", 10_000)
    assert dependencies._version_key("3.74.0-" + "9" * 5000) is None


def test_resolver_response_read_is_capped(monkeypatch):
    """An oversized body must be truncated, not slurped whole."""
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    requested: list[int | None] = []

    class _HugeResponse(_FakeResponse):
        def read(self, size=-1):  # noqa: D102 - mirrors io.BytesIO
            requested.append(size)
            return super().read(size)

    payload = b'{"version": "9.9.9", "pad": "' + b"x" * (256 * 1024) + b'"}'
    monkeypatch.setattr(
        dependencies, "urlopen", lambda request, timeout=None: _HugeResponse(payload)
    )

    dependencies.get_cdn_version()

    assert requested and requested[0] == dependencies._MAX_RESOLVER_BYTES, (
        f"read the body with size={requested[0]!r}, expected the cap"
    )


def test_non_oserror_from_urlopen_does_not_escape(bar_plot, monkeypatch):
    """The broad ``except`` exists for exactly this; prove it holds.

    ``pytest-socket`` raises ``SocketBlockedError``, which derives from
    ``Exception`` rather than ``OSError``. A narrower handler would let it
    propagate out of ``render()``.
    """

    class SocketBlockedError(Exception):
        pass

    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)

    def blocked(*_args, **_kwargs):
        raise SocketBlockedError("network access blocked in this environment")

    monkeypatch.setattr(dependencies, "urlopen", blocked)

    # Degrades to @latest rather than raising, and caches the failure.
    assert dependencies.get_cdn_version() == dependencies.LATEST_TAG
    maidr.render(bar_plot, use_cdn="auto")


def test_bundled_cdn_url_needs_no_lookup(forbid_network):
    """``init_notebook`` depends on this being network-free."""
    url = dependencies.bundled_cdn_url(dependencies.MAIDR_JS_FILENAME)

    assert f"maidr@{dependencies.maidr_js_version()}/" in url
    assert "maidr@latest" not in url


def test_bundled_cdn_url_degrades_when_version_unknown(monkeypatch, forbid_network):
    """With no usable bundled VERSION there is no better offline answer."""
    monkeypatch.setattr(
        dependencies, "maidr_js_version", lambda: dependencies._UNKNOWN_VERSION
    )
    assert dependencies.bundled_cdn_url(
        dependencies.MAIDR_JS_FILENAME
    ) == dependencies.MAIDR_JS_CDN_URL


def test_freshness_workflow_imports_resolve():
    """Guard the inline Python in check-bundle-freshness.yml.

    That workflow imports these two names; a rename would break a job
    nothing else exercises until it fires on a schedule.
    """
    from maidr import bundle_status
    from maidr.util.dependencies import STALE_MINOR_GAP

    assert isinstance(STALE_MINOR_GAP, int)
    status = bundle_status(resolve=False)
    assert hasattr(status, "published")
    assert hasattr(status, "is_stale")
    assert hasattr(status, "is_behind")
