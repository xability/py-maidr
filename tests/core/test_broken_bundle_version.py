"""An unreadable bundled version must not fall back to ``@latest`` in silence.

``_offline_version()`` ends at :data:`LATEST_TAG` when nothing better is
available. There are two roads there and only one of them is normal:

* a lookup that failed -- offline, blocked, a malformed response -- which is a
  routine operating condition and the documented safe degradation;
* a bundled ``VERSION`` that will not read, which is a broken install.

The second is a fault, and nobody but the user can fix it. The page still
works and the URL is well-formed, so without a word the only symptom is
someone occasionally being served a week-old ``maidr.js`` for reasons nothing
in the output explains (#364).

Warning on both would train people to ignore the message, so these pin the
split as much as the message.
"""

from __future__ import annotations

import logging

import pytest

from maidr.util import dependencies


@pytest.fixture
def no_pin(monkeypatch):
    """Clear every pin and cached lookup, and re-arm the one-shot warning."""
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    dependencies.reset_cdn_version_cache()
    dependencies._warned_keys.clear()
    yield
    dependencies.set_cdn_version(None)
    dependencies.reset_cdn_version_cache()
    # `maidr_js_version` is not cleared here. `monkeypatch` tears down after
    # this fixture, so the name still points at `break_bundle`'s stand-in --
    # a plain function, with no `cache_clear` on it. `break_bundle` clears the
    # real one on the way in, which is where it matters.


def break_bundle(monkeypatch, value: str = dependencies._UNKNOWN_VERSION) -> None:
    """Make the wheel look as though its ``VERSION`` will not read."""
    dependencies.maidr_js_version.cache_clear()
    monkeypatch.setattr(dependencies, "maidr_js_version", lambda: value)


def test_an_unreadable_bundle_version_says_so(monkeypatch, caplog, no_pin) -> None:
    """The fault is announced, and the announcement names the consequence.

    Not just "something is wrong": the reason this matters is the seven-day
    cache lifetime on the mutable tag, which is the part a reader cannot
    infer from a URL that looks perfectly valid.
    """
    break_bundle(monkeypatch)

    with caplog.at_level(logging.WARNING):
        version = dependencies._offline_version()

    assert version == dependencies.LATEST_TAG
    assert "missing or empty" in caplog.text
    assert dependencies.LATEST_TAG in caplog.text
    assert "cache" in caplog.text


def test_a_garbled_version_is_named_in_the_warning(
    monkeypatch, caplog, no_pin
) -> None:
    """A VERSION file holding nonsense is a different fault from a missing one.

    Both land here, and the message carries the value, so "the file is not
    there" and "the file says ``not-a-version``" are told apart by the log
    rather than by guessing.
    """
    break_bundle(monkeypatch, "not-a-version")

    with caplog.at_level(logging.WARNING):
        dependencies._offline_version()

    assert "not a version" in caplog.text
    assert "not-a-version" in caplog.text


def test_it_is_said_once_not_once_per_figure(monkeypatch, caplog, no_pin) -> None:
    """Every URL build reaches this, so it must not log per figure.

    A broken install renders as many figures as a working one; a line per
    figure would bury the message it is trying to deliver.
    """
    break_bundle(monkeypatch)

    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            dependencies._offline_version()

    assert caplog.text.count("maidr.js version") == 1


def test_a_failed_lookup_stays_quiet(monkeypatch, caplog, no_pin) -> None:
    """The routine degradation keeps its silence.

    An offline notebook falls back to the bundled version on every figure,
    and that is working as documented. Warning here as well would make the
    broken-install message indistinguishable from ordinary life on a train.

    Since #295 the failed lookup routes through `_offline_version` rather
    than straight to `latest`, so it now passes *through* the code that
    warns -- which is why this asserts the silence rather than assuming
    it. The warning is about the broken install, not about being offline,
    and a healthy bundle is what keeps it quiet here.
    """
    monkeypatch.setattr(dependencies, "_fetch_latest_version", lambda budget: None)

    with caplog.at_level(logging.WARNING):
        version = dependencies.get_cdn_version()

    assert version == dependencies.maidr_js_version()
    assert "maidr.js version" not in caplog.text


def test_a_working_bundle_stays_quiet(caplog, no_pin) -> None:
    """The control: the overwhelmingly common case says nothing."""
    with caplog.at_level(logging.WARNING):
        version = dependencies._offline_version()

    assert version == dependencies.maidr_js_version()
    assert "maidr.js version" not in caplog.text


def test_a_pin_is_answered_before_the_bundle(monkeypatch, caplog, no_pin) -> None:
    """A caller who named a version does not need telling about the bundle.

    The pin is answered before the bundle is ever consulted, so a broken
    install behind an explicit pin is not this warning's business.
    """
    break_bundle(monkeypatch)
    dependencies.set_cdn_version("3.74.0")

    with caplog.at_level(logging.WARNING):
        version = dependencies._offline_version()

    assert version == "3.74.0"
    assert "maidr.js version" not in caplog.text
