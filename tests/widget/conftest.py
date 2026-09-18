"""Shared fixtures for the framework-integration tests.

The Shiny tests drive a renderer the way Shiny drives it -- inside a
session context -- without starting a server.  Only the five pieces of
:class:`shiny.session.Session` that a renderer touches are stubbed:
``ns`` (namespacing), ``output`` (auto-registration), ``_process_ui``
(dependency resolution), and ``dynamic_route`` with ``on_ended`` (serving
the chart out of band for the life of the session).

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

        def __init__(self, id: str = "fake-session") -> None:  # noqa: A002
            #: What ``AppSession.dynamic_route`` puts in the URL it returns.
            self.id = id
            self.app = FakeApp()
            self.outputs: list[Any] = []
            #: Callbacks registered with ``on_ended``; ``end()`` runs them.
            self.ended: list[Any] = []
            #: The routes ``dynamic_route`` registers, name to handler, as
            #: ``AppSession`` keeps them.  A test fetches a served chart by
            #: calling the handler here, the way Shiny's request handler
            #: does.
            self._dynamic_routes: dict[str, Any] = {}

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

        # Same argument.  Touches only ``self._dynamic_routes`` and
        # ``self.id``, both above, and returns the URL shape the real
        # session returns, so the tests see the ``nonce`` query the
        # version has to join.
        dynamic_route = AppSession.dynamic_route

        def on_ended(self, fn: Any) -> Any:
            """Stand in for ``Session.on_ended``; see :meth:`end`."""
            self.ended.append(fn)
            return lambda: None

        def end(self) -> None:
            """Run what was registered with ``on_ended``, as the session would."""
            for fn in self.ended:
                fn()

    return FakeSession


@pytest.fixture
def fake_session():
    """Yield a ``FakeSession`` with its session context active."""
    pytest.importorskip("shiny")
    from shiny.session import session_context

    session = _fake_session_class()()
    with session_context(session):  # type: ignore[arg-type]
        yield session
