"""A Plotly chart in a notebook's frame is as tall as the notebook draws it.

A figure with no height of its own -- in its layout or its template's -- was
drawn by plotly.js at 450px, where the notebook's own renderer draws it at
360px (JupyterLab's, Notebook 7's, VS Code's) or 525px (plotly's HTML
renderers: ``notebook``, ``colab`` and the like), as the first of
``plotly.io.renderers.default`` says. A figure with a height keeps it, and a
document of its own (``save_html``) keeps plotly's default.
"""

from __future__ import annotations

import html as html_module
import re

import pytest

# Guarded here, not in conftest.py: see tests/plotly/conftest.py.
go = pytest.importorskip("plotly.graph_objects")
pio = pytest.importorskip("plotly.io")

import maidr  # noqa: E402
from maidr.plotly.plotly_maidr import notebook_default_height  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402


def _figure(**layout) -> go.Figure:
    fig = go.Figure(go.Bar(x=["Q1", "Q2", "Q3"], y=[5, 7, 3]))
    fig.update_layout(**layout)
    return fig


def _plot_height(html: str) -> str:
    """The height plotly's fragment gives the chart.

    On the graph div, or, from plotly 7, on the div plotly puts around it.
    """
    text = html_module.unescape(html)
    graph = text.index('class="plotly-graph-div"')
    around = text.rfind("<div", 0, text.rfind("<div", 0, graph))
    heights = re.findall(r"height:\s*([^;\"]+)", text[around : text.index(">", graph)])
    sized = [height for height in heights if height != "100%"]
    return sized[0] if sized else "100%"


@pytest.fixture
def notebook(monkeypatch):
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))


@pytest.mark.parametrize(
    "renderer, height",
    [
        ("plotly_mimetype+notebook", 360),
        ("jupyterlab", 360),
        ("vscode", 360),
        ("notebook_connected", 525),
        ("colab", 525),
        ("iframe", 525),
    ],
)
def test_the_first_renderer_sets_the_default_height(monkeypatch, renderer, height):
    monkeypatch.setattr(pio.renderers, "default", renderer)

    assert notebook_default_height() == height


def test_a_figure_without_a_height_is_as_tall_as_the_notebook_draws_it(
    notebook, monkeypatch
):
    monkeypatch.setattr(pio.renderers, "default", "plotly_mimetype+notebook")

    assert _plot_height(str(maidr.render(_figure()))) == "360px"


def test_a_figure_with_a_height_keeps_it(notebook):
    assert _plot_height(str(maidr.render(_figure(height=300)))) == "300px"


def test_a_templates_height_is_the_figures(notebook):
    template = go.layout.Template(layout={"height": 280})

    assert _plot_height(str(maidr.render(_figure(template=template)))) == "280px"


def test_a_document_of_its_own_keeps_plotlys_default(tmp_path):
    path = tmp_path / "chart.html"
    maidr.save_html(_figure(), str(path))

    assert _plot_height(path.read_text(encoding="utf-8")) == "100%"


def test_the_frame_is_a_notebook_frame(notebook):
    html = str(maidr.render(_figure()))

    assert 'srcdoc="&lt;style&gt;' in html
    assert "var fitsOutput = true;" in html_module.unescape(html)
