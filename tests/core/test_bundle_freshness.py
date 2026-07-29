"""Tests for bundled ``maidr.js`` staleness reporting.

The bundle is refreshed at py-maidr release time, so it can drift behind
upstream between releases.  A render that falls back to it then silently
runs older code — the gap that prompted this check was 8 minor versions.
These tests pin down what is reported, when it is surfaced, and that
surfacing it never reaches for the network.
"""

from __future__ import annotations

import contextlib
import warnings

import matplotlib.pyplot as plt
import pytest

import maidr
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


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bundled_version", "published", "is_behind", "is_stale"),
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
    ],
)
def test_bundle_status_comparison(
    bundled_version, published, is_behind, is_stale, bundled
):
    bundled(bundled_version)
    maidr.set_cdn_version(published)

    status = maidr.bundle_status()

    assert status.bundled == bundled_version
    assert status.published == published
    assert status.is_behind is is_behind
    assert status.is_stale is is_stale


def test_bundle_status_unknown_published_version_is_not_a_guess(bundled):
    """Pinned to ``latest``: no concrete version, so no claim either way."""
    bundled("3.66.1")
    maidr.set_cdn_version("latest")

    status = maidr.bundle_status()

    assert status.published is None
    assert status.is_behind is False
    assert status.is_stale is False


def test_bundle_status_missing_bundle_is_not_reported_as_stale(bundled):
    """``0.0.0`` means "no VERSION file", not "an ancient release"."""
    bundled("0.0.0")
    maidr.set_cdn_version("3.74.0")

    status = maidr.bundle_status()

    assert status.is_behind is False
    assert status.is_stale is False


def test_bundle_status_resolve_false_never_hits_the_network(monkeypatch, bundled):
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    bundled("3.66.1")

    def explode(*_args, **_kwargs):
        raise AssertionError("resolve=False must not touch the network")

    monkeypatch.setattr(dependencies, "urlopen", explode)

    status = maidr.bundle_status(resolve=False)
    assert status.published is None
    assert status.is_stale is False


# ---------------------------------------------------------------------------
# The warning
# ---------------------------------------------------------------------------


def test_warning_names_both_versions(bundled):
    bundled("3.66.1")
    maidr.set_cdn_version("3.74.0")

    with pytest.warns(UserWarning) as record:
        dependencies.warn_if_bundle_is_stale()

    message = str(record[0].message)
    assert "3.66.1" in message
    assert "3.74.0" in message
    assert dependencies.BUNDLE_WARNING_ENV_VAR in message, (
        "the warning must say how to silence itself"
    )


def test_warning_is_emitted_once_per_process(bundled):
    bundled("3.66.1")
    maidr.set_cdn_version("3.74.0")

    with pytest.warns(UserWarning):
        dependencies.warn_if_bundle_is_stale()

    with no_stale_bundle_warning():
        dependencies.warn_if_bundle_is_stale()


def test_no_warning_for_normal_drift(bundled):
    bundled("3.73.0")
    maidr.set_cdn_version("3.74.0")

    with no_stale_bundle_warning():
        dependencies.warn_if_bundle_is_stale()


@pytest.mark.parametrize("disabled", ["0", "false", "off", "no", "FALSE"])
def test_env_var_silences_the_warning(disabled, monkeypatch, bundled):
    monkeypatch.setenv(dependencies.BUNDLE_WARNING_ENV_VAR, disabled)
    bundled("3.66.1")
    maidr.set_cdn_version("3.74.0")

    with no_stale_bundle_warning():
        dependencies.warn_if_bundle_is_stale()


def test_warning_never_resolves_over_the_network(monkeypatch, bundled):
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    bundled("3.66.1")

    def explode(*_args, **_kwargs):
        raise AssertionError("the staleness check must not touch the network")

    monkeypatch.setattr(dependencies, "urlopen", explode)

    with no_stale_bundle_warning():
        dependencies.warn_if_bundle_is_stale()


# ---------------------------------------------------------------------------
# Render paths
# ---------------------------------------------------------------------------


def test_use_cdn_false_render_warns(bar_plot, bundled):
    """Offline mode runs the bundle exclusively, so its age matters most."""
    bundled("3.66.1")
    maidr.set_cdn_version("3.74.0")

    with pytest.warns(UserWarning, match="3.66.1"):
        maidr.render(bar_plot, use_cdn=False)


def test_use_cdn_auto_render_warns(bar_plot, bundled):
    bundled("3.66.1")
    maidr.set_cdn_version("3.74.0")

    with pytest.warns(UserWarning, match="3.66.1"):
        maidr.render(bar_plot, use_cdn="auto")


def test_use_cdn_true_render_does_not_warn(bar_plot, bundled):
    """CDN-only renders never execute the bundle, so its age is moot."""
    bundled("3.66.1")
    maidr.set_cdn_version("3.74.0")

    with no_stale_bundle_warning():
        maidr.render(bar_plot, use_cdn=True)


@pytest.mark.parametrize("use_cdn", [False, "auto"])
def test_plotly_render_warns(use_cdn, bundled):
    """The Plotly adapter wires the warning in independently of matplotlib.

    ``plotly_maidr.py`` calls ``warn_if_bundle_is_stale()`` from its own
    ``_create_html_tag``, so the matplotlib render tests above would not
    catch that wiring drifting.
    """
    pytest.importorskip("plotly")
    import plotly.graph_objects as go

    bundled("3.66.1")
    maidr.set_cdn_version("3.74.0")
    fig = go.Figure(data=[go.Bar(x=["A", "B"], y=[1, 2])])

    with pytest.warns(UserWarning, match="3.66.1"):
        maidr.render(fig, use_cdn=use_cdn)


def test_plotly_render_use_cdn_true_does_not_warn(bundled):
    """CDN-only Plotly renders never execute the bundle either."""
    pytest.importorskip("plotly")
    import plotly.graph_objects as go

    bundled("3.66.1")
    maidr.set_cdn_version("3.74.0")
    fig = go.Figure(data=[go.Bar(x=["A", "B"], y=[1, 2])])

    with no_stale_bundle_warning():
        maidr.render(fig, use_cdn=True)


def test_offline_render_with_unknown_published_version_is_silent(
    bar_plot, monkeypatch, bundled
):
    """No network, nothing known: say nothing rather than guess."""
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    bundled("3.66.1")

    def explode(*_args, **_kwargs):
        raise AssertionError("use_cdn=False must not touch the network")

    monkeypatch.setattr(dependencies, "urlopen", explode)

    with no_stale_bundle_warning():
        maidr.render(bar_plot, use_cdn=False)


