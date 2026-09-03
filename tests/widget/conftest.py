"""Shared fixtures for the framework-integration tests.

The Shiny tests drive a renderer the way Shiny drives it -- inside a
session context -- without starting a server.  Only the three pieces of
:class:`shiny.session.Session` that a renderer touches are stubbed:
``ns`` (namespacing), ``output`` (auto-registration) and ``_process_ui``
(dependency resolution).

Shiny is imported inside the fixture, not here.  ``pytest.importorskip``
raises ``Skipped``, and a ``Skipped`` escaping a conftest is not "skip
this directory": pytest 7 imports every sub-conftest while collecting the
*session*, so the whole run collects nothing and exits 5, which CI reads
as a clean skip.  The modules that need Shiny (``test_shiny.py``,
``test_every_door_agrees.py``) guard themselves at module level, where a
``Skipped`` means exactly one module; ``test_streamlit.py`` does not need
it at all and must keep running without it.
"""

from __future__ import annotations

from typing import Any

import pytest


class FakeApp:
    """Records the web dependencies a session registers."""

    lib_prefix = "lib"

    def __init__(self) -> None:
        self.registered: list[Any] = []

    def _register_web_dependency(self, dep: Any) -> None:
        self.registered.append(dep)


def _fake_session_class() -> type:
    """Build the ``FakeSession`` class against the installed Shiny.

    Deferred so the two class attributes borrowed from Shiny are looked up
    only once a test actually asks for a session -- see the module
    docstring for why this file must import cleanly without Shiny.
    """
    from shiny import module
    from shiny.session._session import AppSession

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

        # Borrowed from Shiny rather than reimplemented.  A hand-written
        # copy would let the tests assert a payload shape this package
        # invented: upstream could rename a key and every test would still
        # pass while production broke.  ``AppSession._process_ui`` touches
        # only ``self.app._register_web_dependency`` and
        # ``self.app.lib_prefix``, both of which :class:`FakeApp` provides,
        # so it runs unmodified -- and an incompatible upstream change
        # fails here loudly.
        _process_ui = AppSession._process_ui

    return FakeSession


@pytest.fixture
def fake_session():
    """Yield a ``FakeSession`` with its session context active."""
    pytest.importorskip("shiny")
    from shiny.session import session_context

    session = _fake_session_class()()
    with session_context(session):  # type: ignore[arg-type]
        yield session
