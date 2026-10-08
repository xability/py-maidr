"""A Bokeh graph drawn from a directed networkx graph is walked from the keyboard.

``from_networkx`` makes a ``GraphRenderer``; one made from a directed graph
is read as a ``directed_graph`` layer. maidr.js walks it in topological
order and reports the node being read as its index into the layer's data,
and the page answers by selecting that node's row of the node renderer's
source. The nodes are added to the graph out of topological order here, so
a highlight keyed on the walk's position rather than the node would select
the wrong one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

bokeh = pytest.importorskip("bokeh")
nx = pytest.importorskip("networkx")

_BOKEH_JS = Path(bokeh.__file__).parent / "server" / "static" / "js"
_BOKEH_CDN = re.compile(
    r"^https://cdn\.bokeh\.org/bokeh/release/(bokeh[a-z-]*)-[^/]+\.min\.js$"
)
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000
_TEXT = "#maidr-text-container"
_SELECTED = """(id) => {
  for (const doc of Bokeh.documents) {
    const model = doc.get_model_by_id(id);
    if (model) return [...model.data_source.selected.indices];
  }
  return null;
}"""


def _local_bokeh(route) -> None:
    name = _BOKEH_CDN.match(route.request.url).group(1)
    route.fulfill(
        path=str(_BOKEH_JS / f"{name}.min.js"),
        content_type="application/javascript",
    )


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(300)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_each_node_announced_is_the_node_selected(browser, tmp_path):
    from bokeh.plotting import figure, from_networkx

    import maidr

    graph = nx.DiGraph()
    # Source order: train, clean, load, features -- not the walk's order.
    graph.add_nodes_from(["train", "clean", "load", "features"])
    graph.add_edges_from(
        [("load", "clean"), ("clean", "features"), ("features", "train")]
    )
    p = figure(title="Pipeline")
    renderer = from_networkx(graph, nx.circular_layout)
    p.renderers.append(renderer)
    path = tmp_path / "graph.html"
    maidr.save_html(p, str(path), use_cdn=False)
    source_row = {"train": 0, "clean": 1, "load": 2, "features": 3}

    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.route(_BOKEH_CDN, _local_bokeh)
    page.goto(path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.wait_for_selector('article[id^="maidr-article"]', timeout=_PARSE_TIMEOUT_MS)
    page.wait_for_timeout(500)
    page.keyboard.press("Tab")
    page.wait_for_timeout(400)
    try:
        for name in ["load", "clean", "features", "train"]:
            spoken = _step(page, "ArrowRight")
            assert f"Node is {name}" in spoken, spoken
            assert page.evaluate(_SELECTED, renderer.node_renderer.id) == [
                source_row[name]
            ], name
        assert not errors, errors
    finally:
        page.close()
