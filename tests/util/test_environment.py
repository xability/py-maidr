"""Tests for the IPython and Shiny probes in :mod:`maidr.util.environment`.

``is_notebook()`` runs during ``import maidr`` and ``get_renderer()`` /
``is_shiny()`` run on every render, so importing the package they probe
for charged every plain script the whole import (~200 ms for IPython,
~0.2 s for Shiny) just to learn it was not in use (#707).  A shell or a
session cannot exist unless its package is already in ``sys.modules``,
which is therefore the only thing the probes may consult before importing.
"""

from __future__ import annotations

import importlib.abc
import sys
import types


from maidr.util.environment import Environment


class _RefusingFinder(importlib.abc.MetaPathFinder):
    """Fail the test the moment anything tries to import ``package``."""

    def __init__(self, package: str) -> None:
        self._package = package

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self._package or fullname.startswith(self._package + "."):
            raise AssertionError(f"the probe imported {fullname}")
        return None


class _RecordingFinder(importlib.abc.MetaPathFinder):
    """Note every attempt to import ``package`` and let it proceed."""

    def __init__(self, package: str) -> None:
        self._package = package
        self.attempts: list[str] = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self._package or fullname.startswith(self._package + "."):
            self.attempts.append(fullname)
        return None


def _unload(monkeypatch, package: str) -> None:
    for name in [m for m in sys.modules if m == package or m.startswith(package + ".")]:
        monkeypatch.delitem(sys.modules, name)


def test_probes_do_not_import_ipython(monkeypatch):
    """A plain script must not load IPython to learn it is not a notebook."""
    _unload(monkeypatch, "IPython")
    monkeypatch.setattr(sys, "meta_path", [_RefusingFinder("IPython"), *sys.meta_path])

    assert Environment.is_notebook() is False
    assert Environment.is_interactive_shell() is False
    assert Environment.get_renderer() == "browser"
    assert "IPython" not in sys.modules


def test_probes_still_see_a_loaded_kernel_shell(monkeypatch):
    """The short-circuit must not hide a real kernel.

    Every notebook host runs user code inside an ipykernel shell, and
    ``ipykernel.kernelapp`` imports IPython at module level, so by the time
    user code runs the package is in ``sys.modules`` and the probes must
    go on to ask it.
    """

    class KernelShell:
        def __repr__(self) -> str:
            return "<ipykernel.zmqshell.ZMQInteractiveShell object>"

    shell = KernelShell()
    monkeypatch.setitem(
        sys.modules, "IPython", types.SimpleNamespace(get_ipython=lambda: shell)
    )

    assert Environment.is_notebook() is True
    assert Environment.get_renderer() == "ipython"


def test_a_blocked_ipython_import_is_not_a_notebook(monkeypatch):
    """``sys.modules["IPython"] = None`` is how an import is blocked.

    The entry exists but is not a package, so it must read as "not
    loaded" rather than as a shell to interrogate.
    """
    monkeypatch.setitem(sys.modules, "IPython", None)

    assert Environment.is_notebook() is False
    assert Environment.is_interactive_shell() is False
    assert Environment.get_renderer() == "browser"


def test_is_shiny_does_not_import_shiny(monkeypatch):
    """No live session without the package, so do not import it to ask.

    Recording rather than refusing, because ``is_shiny`` swallows every
    exception on purpose -- a refusing finder would be caught and the
    probe would look lazy whether or not it was.
    """
    _unload(monkeypatch, "shiny")
    finder = _RecordingFinder("shiny")
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])

    assert Environment.is_shiny() is False
    assert finder.attempts == []
    assert "shiny" not in sys.modules
