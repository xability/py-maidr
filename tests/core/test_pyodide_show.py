"""``maidr.show`` in a bare Pyodide page (``micropip.install("maidr")``).

There is no IPython and no browser to launch there, so the chart used to go
to ``webbrowser.open`` and nothing appeared.  It is appended to the page's
``<body>`` instead.
"""

from __future__ import annotations

import sys
import types

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402


class _Element:
    def __init__(self) -> None:
        self.innerHTML = ""
        self.children: list[_Element] = []

    def appendChild(self, child: "_Element") -> None:
        self.children.append(child)


@pytest.fixture
def page(monkeypatch):
    """A fake Pyodide page: ``sys.platform`` and a ``js.document``."""
    body = _Element()
    document = types.SimpleNamespace(body=body, createElement=lambda _tag: _Element())
    monkeypatch.setitem(sys.modules, "js", types.SimpleNamespace(document=document))
    monkeypatch.setattr(sys, "platform", "emscripten")
    return body


def _bar():
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    return fig, ax


def test_is_pyodide_page_needs_a_document(monkeypatch):
    monkeypatch.setitem(sys.modules, "js", types.SimpleNamespace())
    monkeypatch.setattr(sys, "platform", "emscripten")
    assert Environment.is_pyodide_page() is False


def test_is_pyodide_page_is_false_off_emscripten():
    assert Environment.is_pyodide_page() is False


def test_show_embeds_the_chart_in_the_page(page, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: opened.append(a))
    _, ax = _bar()

    maidr.show(ax, use_cdn=False)

    assert opened == []
    assert len(page.children) == 1
    html = page.children[0].innerHTML
    assert "<iframe" in html and "srcdoc" in html
    # The frame carries its own runtime: there is no notebook stash to read.
    assert "__maidrJsSource" not in html
    plt.close("all")


def _plotly():
    go = pytest.importorskip("plotly.graph_objects")
    return go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))


def _bokeh():
    figure = pytest.importorskip("bokeh.plotting").figure
    p = figure(x_range=["a", "b"])
    p.vbar(x=["a", "b"], top=[1, 2], width=0.5)
    return p


def _altair():
    alt = pytest.importorskip("altair")
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"x": ["a", "b"], "y": [1, 2]})
    return alt.Chart(df).mark_bar().encode(x="x", y="y")


@pytest.mark.filterwarnings("ignore:maidr:UserWarning")
@pytest.mark.parametrize("make", [_plotly, _bokeh, _altair])
def test_other_libraries_embed_in_the_page(page, monkeypatch, make):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: opened.append(a))

    maidr.show(make(), use_cdn=False)

    assert opened == []
    assert len(page.children) == 1
    assert "<iframe" in page.children[0].innerHTML


def test_is_pyodide_page_is_false_in_a_notebook_shell(page, monkeypatch):
    """JupyterLite has IPython, so it is not handled as a bare page."""
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))
    assert Environment.is_pyodide_page() is False


def test_a_page_iframes_with_an_inline_bundle(page):
    from maidr.util.bundle_loader import iframe_mode

    assert iframe_mode(True) == (True, False, True)


def test_no_page_means_no_iframe():
    from maidr.util.bundle_loader import iframe_mode

    assert iframe_mode(True) == (False, False, False)


@pytest.mark.filterwarnings("ignore:maidr:UserWarning")
@pytest.mark.parametrize("make", [_plotly, _bokeh, _altair])
def test_other_libraries_skip_the_page_in_a_notebook(page, monkeypatch, make):
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))
    shown = []
    monkeypatch.setattr(
        "htmltools.Tag.show", lambda self, *a, **k: shown.append(a), raising=False
    )

    maidr.show(make(), renderer="ipython", use_cdn=True)

    assert page.children == []
