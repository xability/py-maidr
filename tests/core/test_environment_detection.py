"""Tests for :meth:`maidr.util.environment.Environment.is_shiny`.

``is_shiny`` decides whether a render is iframe-wrapped and where it
looks for ``maidr.js``, so answering it by asking whether Shiny is
*installed* rather than whether a Shiny session is *running* silently
changed the output of every render in any process that happened to have
Shiny on disk.
"""

from __future__ import annotations

import builtins

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402


@pytest.fixture
def bar_axes():
    """Yield the axes of a two-bar chart, closed afterwards."""
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    yield ax
    plt.close(fig)


def test_is_shiny_is_false_outside_a_session():
    """Importable but not running is not a Shiny environment."""
    pytest.importorskip("shiny")
    assert Environment.is_shiny() is False


def test_is_shiny_is_true_inside_a_session():
    """A live session is what the predicate is meant to detect."""
    pytest.importorskip("shiny")
    from shiny import module
    from shiny.session import session_context

    class MinimalSession:
        """Only what ``session_context`` itself reads."""

        ns = module.ResolvedId("")

    with session_context(MinimalSession()):  # type: ignore[arg-type]
        assert Environment.is_shiny() is True


def test_is_shiny_survives_a_broken_shiny_install(monkeypatch):
    """A probe must never be the reason a render fails.

    Shiny's import chain reaches ``shinychat`` and ``htmltools``, so a
    version skew raises ``ImportError`` for a missing name -- and other
    exception types are possible.  A user who never asked for Shiny should
    not see any of them.
    """
    real_import = builtins.__import__

    def exploding_import(name, *args, **kwargs):
        if name.startswith("shiny"):
            raise RuntimeError("half-installed shiny")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(__import__("sys").modules, "shiny.session", raising=False)
    monkeypatch.setattr(builtins, "__import__", exploding_import)
    assert Environment.is_shiny() is False


def test_render_outside_a_session_is_not_iframe_wrapped(bar_axes):
    """The case that bit every Streamlit and script user with Shiny installed.

    Before, merely having Shiny importable produced iframe-wrapped output
    with no ``HTMLDependency`` -- roughly twice the bytes, and in a
    Streamlit app an iframe nested inside Streamlit's own.
    """
    pytest.importorskip("shiny")
    html = str(maidr.render(bar_axes, use_cdn=True).get_html_string())
    assert "<iframe" not in html.lower()
