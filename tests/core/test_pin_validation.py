"""A typo in ``set_cdn_version()`` must not do nothing, quietly.

``maidr.set_cdn_version("3.74")`` -- a missing patch component -- logged a
line and was otherwise ignored: the next URL resolved exactly as if no pin
had been set. The caller got no return value, no exception, and a *log* line
they may never see, because logging is not configured by default (#294).

The leniency is right for ``MAIDR_CDN_VERSION``. Ambient configuration may be
set by something outside the caller's control -- a CI image, a container
base, a colleague's shell profile -- and crashing on it would be hostile. It
is wrong for an explicit call with a bad argument.

These pin the asymmetry as much as the warning, because the asymmetry is the
part someone reading only one half will think is a bug.
"""

from __future__ import annotations

import warnings

import pytest

import maidr
from maidr.util import dependencies
from maidr.util import warn as warn_module


@pytest.fixture(autouse=True)
def clean():
    """No pin, no cached lookup, and a fresh log-dedup set."""
    dependencies.set_cdn_version(None)
    dependencies.reset_cdn_version_cache()
    warn_module._warned_keys.clear()
    yield
    dependencies.set_cdn_version(None)
    dependencies.reset_cdn_version_cache()


#: Values that are neither a semver nor a recognised tag. The last four are
#: the hostile ones from `test_cdn_version.py`; a caller typing those has a
#: bigger problem than a typo, and should still be told.
UNUSABLE = [
    "3.74",
    "not-a-version",
    "v",
    "../../../evil",
    "3.74.0 && rm -rf /",
    "https://evil.example.com/x.js",
    "latest?cb=1",
]

USABLE = ["3.74.0", "v3.74.0", "  3.74.0  ", "bundled", "latest", "LATEST"]


@pytest.mark.parametrize("value", UNUSABLE)
def test_an_unusable_pin_says_so_at_the_call(value) -> None:
    """The warning names the call, not a module three frames down.

    `stacklevel=2` so the location Python attributes it to is the line the
    caller wrote. A deprecation pointing into `dependencies.py` tells them
    the library has a problem rather than that they do.
    """
    with pytest.warns(FutureWarning, match=r"set_cdn_version"):
        maidr.set_cdn_version(value)


@pytest.mark.parametrize("value", UNUSABLE)
def test_an_unusable_pin_is_still_ignored_for_now(value) -> None:
    """Today's behaviour is unchanged: warn, then resolve as if unpinned.

    Raising outright would break a script that has been quietly mistyping
    its pin and rendering fine. The warning is this release's change; the
    raise is a future major's, and the message says so.
    """
    with pytest.warns(FutureWarning, match="will raise ValueError"):
        maidr.set_cdn_version(value)

    assert dependencies._version_pin() is None


@pytest.mark.parametrize("value", USABLE)
def test_a_usable_pin_is_silent(value) -> None:
    """The overwhelmingly common case says nothing.

    Including the tags and the shapes a caller reasonably writes -- a
    ``v`` prefix, because that is how releases are spelled, and
    surrounding space, because that is what a copy-paste brings with it.
    """
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        maidr.set_cdn_version(value)

    assert [r for r in records if issubclass(r.category, FutureWarning)] == []


@pytest.mark.parametrize("value", [None, "", "   "])
def test_clearing_the_pin_is_silent(value, monkeypatch) -> None:
    """Clearing is not a mistake.

    A blank string is treated as ``None`` rather than as a malformed pin,
    which is a decision that predates this and would look like an
    oversight if the deprecation started shouting about it.

    The environment variable is removed for the duration: the suite's
    autouse fixture sets it, and with it in place a cleared override
    correctly falls through to it -- so asserting on the *pin* rather
    than on the override would be measuring the fixture.
    """
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)

    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        maidr.set_cdn_version(value)

    assert [r for r in records if issubclass(r.category, FutureWarning)] == []
    assert dependencies._version_pin() is None


def test_the_environment_variable_stays_lenient(monkeypatch) -> None:
    """The asymmetry, asserted rather than only documented.

    ``MAIDR_CDN_VERSION`` is ambient configuration. Someone whose CI image
    sets it wrongly should get a chart and a log line, not a warning they
    cannot act on from inside their own code -- and certainly not, later,
    an exception.
    """
    dependencies.set_cdn_version(None)
    monkeypatch.setenv(dependencies.CDN_VERSION_ENV_VAR, "3.74")

    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        resolved = dependencies._version_pin()

    assert resolved is None
    assert [r for r in records if issubclass(r.category, FutureWarning)] == []


def test_the_warning_is_a_futurewarning_not_a_deprecationwarning() -> None:
    """Category chosen for the audience, as elsewhere in this module.

    ``DeprecationWarning`` is silenced by default outside ``__main__``, so
    a call from inside a Shiny app or an imported module would never see
    it -- and would meet the eventual ``ValueError`` as a breakage rather
    than as a warning, which is the one thing a deprecation exists to
    prevent. Same reasoning as `_warn_placeholder_css`.
    """
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        maidr.set_cdn_version("3.74")

    categories = {r.category for r in records}
    assert FutureWarning in categories
    assert DeprecationWarning not in categories
