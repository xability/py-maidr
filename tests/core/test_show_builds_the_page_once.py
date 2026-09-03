"""``Maidr.show()`` builds the page exactly once, whichever way it is shown.

The browser path renders through ``save_html``, which builds the whole
document itself. Building the Tag before deciding on the renderer
rasterised the SVG and dumped the schema twice and threw the first copy
away -- roughly double the time of ``save_html`` alone on a 100k-point line.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core import maidr as module  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402


@pytest.fixture
def bar_plot():
    fig, ax = plt.subplots()
    ax.bar(["A", "B", "C"], [1.0, 2.0, 3.0])
    yield fig
    plt.close(fig)


@pytest.fixture
def build_count(monkeypatch):
    """Count calls to ``_create_html_tag`` without changing its result."""
    calls = []
    original = module.Maidr._create_html_tag

    def counted(self, *args, **kwargs):
        calls.append(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(module.Maidr, "_create_html_tag", counted)
    return calls


def test_show_in_browser_builds_the_document_once(bar_plot, build_count, monkeypatch):
    opened = []
    monkeypatch.setattr(module.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: False))
    monkeypatch.setattr(Environment, "get_renderer", staticmethod(lambda: "browser"))

    FigureManager.get_maidr(bar_plot).show(clear_fig=False)

    assert len(opened) == 1
    assert len(build_count) == 1


def test_show_in_ipython_builds_the_document_once(bar_plot, build_count, monkeypatch):
    """The reorder must not cost the notebook path its one build."""
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: False))
    monkeypatch.setattr("htmltools._core.Tag.show", lambda self, *a, **k: "shown")

    shown = FigureManager.get_maidr(bar_plot).show(renderer="ipython", clear_fig=False)

    assert shown == "shown"
    assert len(build_count) == 1
