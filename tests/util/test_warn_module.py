"""The shared warning policy, and the property that lets it be shared.

``maidr.util.warn`` exists so the halves of the ``dependencies.py`` split
(#293) can both warn without one importing a private helper from the
other. That only works while it stays a leaf.
"""

from __future__ import annotations

import ast
import pathlib

from maidr.util import warn


def test_the_warn_module_imports_nothing_from_maidr():
    """It has to sit at the bottom of the stack, and stay there.

    ``dependencies`` and ``bundle_capability`` both import this eagerly.
    The moment it imports back into the package it becomes a cycle, and
    the fix would be another lazy shim -- for a module whose whole purpose
    is to be simple enough not to need one.

    Asserted on the parse tree rather than on ``sys.modules``: importing
    any submodule initialises the ``maidr`` package first, so at runtime
    everything looks imported no matter what this file does.
    """
    tree = ast.parse(pathlib.Path(warn.__file__).read_text())

    offenders = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and "maidr" in ast.unparse(node)
    ]

    assert not offenders, (
        f"maidr.util.warn imports from the package: {offenders}. It is the "
        "shared bottom of the warning stack and has to stay a leaf."
    )


def test_warn_once_is_quiet_the_second_time(monkeypatch):
    """The property every caller depends on."""
    seen: list[str] = []
    monkeypatch.setattr(warn, "_warned_keys", set())
    monkeypatch.setattr(warn._logger, "warning", lambda msg, *a: seen.append(msg % a))

    warn.warn_once("a-key", "%s happened", "something")
    warn.warn_once("a-key", "%s happened", "something")

    assert seen == ["something happened"]


def test_a_different_key_still_warns(monkeypatch):
    """Deduplication is per key, so a second distinct fault stays audible."""
    seen: list[str] = []
    monkeypatch.setattr(warn, "_warned_keys", set())
    monkeypatch.setattr(warn._logger, "warning", lambda msg, *a: seen.append(msg % a))

    warn.warn_once("first", "%s", "one")
    warn.warn_once("second", "%s", "two")

    assert seen == ["one", "two"]


def test_the_env_var_silences_the_bundle_warning(monkeypatch):
    """The other half of the shared policy."""
    monkeypatch.delenv(warn.BUNDLE_WARNING_ENV_VAR, raising=False)
    assert warn.bundle_warning_enabled()

    for off in ("0", "false", "no", "off", "OFF"):
        monkeypatch.setenv(warn.BUNDLE_WARNING_ENV_VAR, off)
        assert not warn.bundle_warning_enabled(), off
