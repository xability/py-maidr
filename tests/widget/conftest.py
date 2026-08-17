"""Shared fixtures for the framework-integration tests.

The Shiny tests drive a renderer the way Shiny drives it -- inside a
session context -- without starting a server.  Only the three pieces of
:class:`shiny.session.Session` that a renderer touches are stubbed:
``ns`` (namespacing), ``output`` (auto-registration) and ``_process_ui``
(dependency resolution).
"""

from __future__ import annotations

from typing import Any

import pytest

shiny = pytest.importorskip("shiny")

from shiny import module  # noqa: E402
from shiny.session import session_context  # noqa: E402
from shiny.session._session import AppSession  # noqa: E402


class FakeApp:
    """Records the web dependencies a session registers."""

    lib_prefix = "lib"

    def __init__(self) -> None:
        self.registered: list[Any] = []

    def _register_web_dependency(self, dep: Any) -> None:
        self.registered.append(dep)


class FakeSession:
    """The subset of ``shiny.Session`` a custom renderer exercises."""

    ns = module.ResolvedId("")

    def __init__(self) -> None:
        self.app = FakeApp()
        self.outputs: list[Any] = []

    def output(self, renderer: Any) -> Any:
        """Stand in for auto-registration via ``Renderer._auto_register``."""
        self.outputs.append(renderer)
        return renderer

    # Borrowed from Shiny rather than reimplemented.  A hand-written copy
    # would let the tests assert a payload shape this package invented:
    # upstream could rename a key and every test would still pass while
    # production broke.  ``AppSession._process_ui`` touches only
    # ``self.app._register_web_dependency`` and ``self.app.lib_prefix``,
    # both of which :class:`FakeApp` provides, so it runs unmodified --
    # and an incompatible upstream change fails here loudly.
    _process_ui = AppSession._process_ui


@pytest.fixture
def fake_session():
    """Yield a :class:`FakeSession` with its session context active."""
    session = FakeSession()
    with session_context(session):  # type: ignore[arg-type]
        yield session
