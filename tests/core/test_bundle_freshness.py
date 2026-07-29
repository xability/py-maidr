"""Tests for bundled ``maidr.js`` staleness reporting.

The bundle is refreshed at py-maidr release time, so it can drift behind
upstream between releases.  A render that falls back to it then silently
runs older code — the gap that prompted this check was 8 minor versions.
These tests pin down what is reported, when it is surfaced, and that
surfacing it never reaches for the network.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import sys
import types
import warnings

import matplotlib.pyplot as plt
import pytest

import maidr
import maidr.util.environment
from maidr import api as maidr_api
from maidr.util import dependencies


@contextlib.contextmanager
def no_stale_bundle_warning():
    """Fail if a bundle-staleness warning is raised inside the block.

    Records rather than raising on *any* ``UserWarning`` so unrelated
    warnings from matplotlib or the maidr backend cannot masquerade as a
    failure here.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield
    offenders = [
        str(w.message)
        for w in caught
        if "bundled copy of maidr.js" in str(w.message)
    ]
    assert not offenders, f"unexpected staleness warning: {offenders}"


@pytest.fixture
def bar_plot():
    fig, ax = plt.subplots()
    ax.bar(["A", "B", "C"], [1, 2, 3])
    yield fig
    plt.close(fig)


@pytest.fixture
def bundled(monkeypatch):
    """Return a setter that fakes the version bundled in the wheel."""

    def _set(version: str) -> None:
        monkeypatch.setattr(dependencies, "maidr_js_version", lambda: version)

    return _set


class _FakeResponse(io.BytesIO):
    """Minimal ``urlopen`` stand-in supporting the ``with`` protocol."""

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


@pytest.fixture
def published(monkeypatch):
    """Return a setter that stubs what npm reports as published.

    Staleness must be driven by a real resolution, not by a pin — a pin
    says which version to *serve*, which is a different question.  Using
    ``set_cdn_version()`` to stand in for "published" is what let that
    conflation hide from these tests in the first place.
    """

    def _set(version: str) -> None:
        monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
        dependencies.set_cdn_version(None)

        def fake_urlopen(request, timeout=None):
            payload = json.dumps({"version": version, "latest": version})
            return _FakeResponse(payload.encode("utf-8"))

        monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)

    return _set


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bundled_version", "published_version", "is_behind", "is_stale"),
    [
        # The gap from the bug report: 8 minor versions behind.
        ("3.66.1", "3.74.0", True, True),
        # A release or two behind is normal drift, not worth a warning.
        ("3.73.0", "3.74.0", True, False),
        ("3.74.0", "3.74.0", False, False),
        ("3.74.0", "3.74.1", True, False),
        # Exactly at the threshold.
        ("3.69.0", "3.74.0", True, True),
        ("3.70.0", "3.74.0", True, False),
        # A major bump always matters.
        ("3.74.0", "4.0.0", True, True),
        # A dev install can legitimately run ahead of the CDN.
        ("3.75.0", "3.74.0", False, False),
        # Prereleases sort before the release they lead to.
        ("3.74.0-rc.1", "3.74.0", True, False),
        ("3.74.0", "3.74.0-rc.1", False, False),
        # ...and against each other, by semver identifier precedence.
        ("3.74.0-rc.1", "3.74.0-rc.2", True, False),
        ("3.74.0-rc.2", "3.74.0-rc.1", False, False),
        ("3.74.0-rc.9", "3.74.0-rc.10", True, False),  # numeric, not lexical
        ("3.74.0-alpha", "3.74.0-beta", True, False),
        ("3.74.0-rc", "3.74.0-rc.1", True, False),  # fewer fields sort lower
        ("3.74.0-1", "3.74.0-alpha", True, False),  # numeric below alphanumeric
        # Build metadata carries no precedence.
        ("3.74.0+build.1", "3.74.0+build.9", False, False),
    ],
)
def test_bundle_status_comparison(
    bundled_version, published_version, is_behind, is_stale, bundled, published
):
    bundled(bundled_version)
    published(published_version)

    status = maidr.bundle_status()

    assert status.bundled == bundled_version
    assert status.published == published_version
    assert status.is_behind is is_behind
    assert status.is_stale is is_stale


def test_a_pin_does_not_stand_in_for_the_published_version(bundled, published):
    """A pin says what to *serve*, not what npm published.

    Treating one as the other let ``set_cdn_version("9.9.9")`` — pinning
    an unreleased build to try it — report 9.9.9 as published and advise
    upgrading, and let a backwards pin hide a genuinely stale bundle.
    """
    bundled("3.66.1")
    published("3.74.0")
    maidr.set_cdn_version("9.9.9")

    status = maidr.bundle_status()

    assert status.published == "3.74.0", "published must come from the lookup"
    # The pin still decides what the emitted URL serves.
    assert "maidr@9.9.9/" in dependencies.maidr_js_cdn_url()


def test_backwards_pin_cannot_conceal_a_stale_bundle(bundled, published):
    bundled("3.66.1")
    published("3.74.0")
    maidr.set_cdn_version("3.66.1")  # pinning to the bundle's own version

    assert maidr.bundle_status().is_stale is True


def test_bundle_status_missing_bundle_is_not_reported_as_stale(bundled, published):
    """``0.0.0`` means "no VERSION file", not "an ancient release"."""
    bundled("0.0.0")
    published("3.74.0")

    status = maidr.bundle_status()

    assert status.is_behind is False
    assert status.is_stale is False


def test_bundle_status_resolve_false_never_hits_the_network(
    monkeypatch, bundled, forbid_network
):
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    bundled("3.66.1")

    status = maidr.bundle_status(resolve=False)
    assert status.published is None
    assert status.is_stale is False


# ---------------------------------------------------------------------------
# The warning
# ---------------------------------------------------------------------------


def test_warning_names_both_versions(bundled, published):
    bundled("3.66.1")
    published("3.74.0")

    maidr.bundle_status()  # establish the published version by resolving

    with pytest.warns(UserWarning) as record:
        dependencies.warn_if_bundle_is_stale()

    message = str(record[0].message)
    assert "3.66.1" in message
    assert "3.74.0" in message
    assert dependencies.BUNDLE_WARNING_ENV_VAR in message, (
        "the warning must say how to silence itself"
    )


def test_warning_is_emitted_once_per_process(bundled, published):
    bundled("3.66.1")
    published("3.74.0")

    maidr.bundle_status()  # establish the published version by resolving

    with pytest.warns(UserWarning):
        dependencies.warn_if_bundle_is_stale()

    with no_stale_bundle_warning():
        dependencies.warn_if_bundle_is_stale()


def test_no_warning_for_normal_drift(bundled, published):
    bundled("3.73.0")
    published("3.74.0")

    maidr.bundle_status()  # establish the published version

    with no_stale_bundle_warning():
        dependencies.warn_if_bundle_is_stale()


@pytest.mark.parametrize("disabled", ["0", "false", "off", "no", "FALSE"])
def test_env_var_silences_the_warning(disabled, monkeypatch, bundled, published):
    monkeypatch.setenv(dependencies.BUNDLE_WARNING_ENV_VAR, disabled)
    bundled("3.66.1")
    published("3.74.0")

    maidr.bundle_status()  # establish the published version

    with no_stale_bundle_warning():
        dependencies.warn_if_bundle_is_stale()


def test_warning_never_resolves_over_the_network(
    monkeypatch, bundled, forbid_network
):
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    bundled("3.66.1")

    with no_stale_bundle_warning():
        dependencies.warn_if_bundle_is_stale()


# ---------------------------------------------------------------------------
# Render paths
# ---------------------------------------------------------------------------


def test_use_cdn_false_render_warns_once_published_version_known(
    bar_plot, bundled, published
):
    """Offline mode runs the bundle exclusively, so its age matters most.

    It can only be reported once *something* has established the
    published version, since the check never resolves on its own — here
    an explicit ``bundle_status()`` call stands in for the CDN render or
    pinned lookup that would do it in real use.
    """
    bundled("3.66.1")
    published("3.74.0")
    maidr.bundle_status()

    with pytest.warns(UserWarning, match="3.66.1"):
        maidr.render(bar_plot, use_cdn=False)


def test_use_cdn_auto_render_reports_to_the_logger(
    bar_plot, bundled, published, caplog
):
    """``auto`` resolves while building its URL, so the drift is known.

    But the CDN copy is what normally loads there, so it is reported to
    the logger rather than as a warning — see
    ``test_auto_path_reports_drift_to_the_logger_not_as_a_warning``.
    """
    bundled("3.66.1")
    published("3.74.0")

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        with no_stale_bundle_warning():
            maidr.render(bar_plot, use_cdn="auto")

    assert any("3.66.1" in r.message for r in caplog.records)


def test_auto_render_first_does_not_swallow_a_later_offline_warning(
    bar_plot, bundled, published, caplog
):
    """The ordering that made the warning unreachable in practice.

    ``use_cdn="auto"`` is the default, so it is almost always the first
    render in a process, and it reports drift to the logger.  While the
    one-shot latch was a single process-wide flag, that first render
    consumed it and every later ``use_cdn=False`` render returned early
    — so the documented ``MaidrBundleStaleWarning`` never reached the
    offline audience it exists for.  The latch is per severity now.

    Both renders happen in one process here on purpose: each on its own
    passes either way.
    """
    bundled("3.66.1")
    published("3.74.0")

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        with no_stale_bundle_warning():
            maidr.render(bar_plot, use_cdn="auto")

    assert any("3.66.1" in r.message for r in caplog.records), (
        "the auto render must have reported the drift to the logger"
    )

    with pytest.warns(dependencies.MaidrBundleStaleWarning, match="3.66.1"):
        maidr.render(bar_plot, use_cdn=False)


def test_offline_render_first_does_not_swallow_a_later_auto_report(
    bar_plot, bundled, published, caplog
):
    """The mirror of the above: the loud severity must not eat the quiet one.

    Latching per severity has to work in both directions, or the fix just
    moves which of the two reports goes missing.
    """
    bundled("3.66.1")
    published("3.74.0")
    maidr.bundle_status()  # establish the published version by resolving

    with pytest.warns(dependencies.MaidrBundleStaleWarning, match="3.66.1"):
        maidr.render(bar_plot, use_cdn=False)

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        with no_stale_bundle_warning():
            maidr.render(bar_plot, use_cdn="auto")

    assert any("3.66.1" in r.message for r in caplog.records)


def test_use_cdn_true_render_does_not_warn(bar_plot, bundled, published):
    """CDN-only renders never execute the bundle, so its age is moot."""
    bundled("3.66.1")
    published("3.74.0")

    with no_stale_bundle_warning():
        maidr.render(bar_plot, use_cdn=True)


def test_plotly_auto_render_reports_to_the_logger(bundled, published, caplog):
    """The Plotly adapter wires the check in independently of matplotlib.

    ``plotly_maidr.py`` calls ``warn_if_bundle_is_stale()`` from its own
    ``_create_html_tag``, so the matplotlib render tests above would not
    catch that wiring drifting.
    """
    pytest.importorskip("plotly")
    import plotly.graph_objects as go

    bundled("3.66.1")
    published("3.74.0")
    fig = go.Figure(data=[go.Bar(x=["A", "B"], y=[1, 2])])

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        with no_stale_bundle_warning():
            maidr.render(fig, use_cdn="auto")

    assert any("3.66.1" in r.message for r in caplog.records)


def test_plotly_use_cdn_false_render_warns_once_published_version_known(
    bundled, published
):
    pytest.importorskip("plotly")
    import plotly.graph_objects as go

    bundled("3.66.1")
    published("3.74.0")
    maidr.bundle_status()
    fig = go.Figure(data=[go.Bar(x=["A", "B"], y=[1, 2])])

    with pytest.warns(UserWarning, match="3.66.1"):
        maidr.render(fig, use_cdn=False)


def test_plotly_render_use_cdn_true_does_not_warn(bundled, published):
    """CDN-only Plotly renders never execute the bundle either."""
    pytest.importorskip("plotly")
    import plotly.graph_objects as go

    bundled("3.66.1")
    published("3.74.0")
    fig = go.Figure(data=[go.Bar(x=["A", "B"], y=[1, 2])])

    with no_stale_bundle_warning():
        maidr.render(fig, use_cdn=True)


def test_init_notebook_use_cdn_false_never_resolves_when_bundle_missing(
    monkeypatch, forbid_network, caplog
):
    """A broken install must not turn ``use_cdn=False`` into a request.

    The missing-bundle fallback emits CDN tags so the notebook still
    works; building those URLs must not resolve a version, or an
    explicitly offline session pays for a lookup it opted out of.
    """
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)

    monkeypatch.setattr(
        maidr_api, "_NOTEBOOK_LOADED", False, raising=False
    )
    monkeypatch.setattr(
        dependencies,
        "read_bundled_js",
        lambda: (_ for _ in ()).throw(FileNotFoundError("bundle missing")),
    )
    monkeypatch.setattr(
        maidr.util.environment.Environment, "is_notebook", staticmethod(lambda: True)
    )

    displayed = {}
    fake_ipython = types.ModuleType("IPython.display")
    fake_ipython.HTML = lambda html: html
    fake_ipython.display = lambda html: displayed.setdefault("html", html)
    monkeypatch.setitem(sys.modules, "IPython.display", fake_ipython)

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        maidr.init_notebook(use_cdn=False)

    assert any("could not be read" in r.message for r in caplog.records), (
        "an offline caller silently served from the CDN must be told"
    )

    html = displayed.get("html", "")
    bundled = dependencies.maidr_js_version()
    assert f"cdn.jsdelivr.net/npm/maidr@{bundled}/" in html, (
        "the fallback should pin the bundled version, which needs no lookup"
    )
    assert "maidr@latest" not in html, (
        "@latest carries the seven-day cache lifetime this PR removes"
    )


def test_offline_render_with_unknown_published_version_is_silent(
    bar_plot, monkeypatch, bundled, forbid_network
):
    """No network, nothing known: say nothing rather than guess."""
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    bundled("3.66.1")

    with no_stale_bundle_warning():
        maidr.render(bar_plot, use_cdn=False)




def test_init_notebook_makes_no_network_call(monkeypatch, forbid_network):
    """``import maidr`` calls this, so it must never resolve.

    Resolving here would put a blocking request inside ``import maidr``,
    before the user can apply any of the documented opt-outs.
    """
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    monkeypatch.setattr(maidr_api, "_NOTEBOOK_LOADED", False, raising=False)
    monkeypatch.setattr(
        maidr.util.environment.Environment, "is_notebook", staticmethod(lambda: True)
    )

    fake = types.ModuleType("IPython.display")
    fake.HTML = lambda html: html
    fake.display = lambda html: None
    monkeypatch.setitem(sys.modules, "IPython.display", fake)

    for mode in (True, False, "auto"):
        monkeypatch.setattr(maidr_api, "_NOTEBOOK_LOADED", False, raising=False)
        maidr.init_notebook(use_cdn=mode)


def test_warning_uses_a_filterable_category(bundled, published):
    """The category is what lets ``-W error`` users filter narrowly.

    Asserting only ``UserWarning`` would not catch a regression to a bare
    ``UserWarning``, which is what the docs tell people to avoid needing.
    """
    bundled("3.66.1")
    published("3.74.0")
    maidr.bundle_status()

    with pytest.warns(dependencies.MaidrBundleStaleWarning):
        dependencies.warn_if_bundle_is_stale(bundle_is_primary=True)

    assert issubclass(dependencies.MaidrBundleStaleWarning, UserWarning)
    assert maidr.MaidrBundleStaleWarning is dependencies.MaidrBundleStaleWarning


def test_auto_path_reports_drift_to_the_logger_not_as_a_warning(
    bundled, published, caplog
):
    """Under ``auto`` the CDN copy loads, so a warning would name dead code.

    With ``-W error`` that would fail a downstream suite over a bundle
    that never executed, so the drift goes to the logger instead.
    """
    bundled("3.66.1")
    published("3.74.0")
    maidr.bundle_status()

    with caplog.at_level(logging.WARNING, logger=dependencies.__name__):
        with no_stale_bundle_warning():
            dependencies.warn_if_bundle_is_stale(bundle_is_primary=False)

    assert any("bundled copy of maidr.js" in r.message for r in caplog.records), (
        "the drift must still be reported, just not as a warning"
    )
