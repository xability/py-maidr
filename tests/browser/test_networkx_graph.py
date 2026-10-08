"""A networkx drawing of a directed graph is driven from the keyboard.

``nx.draw_networkx`` draws every node as one point of a single collection,
and the ``directed_graph`` layer read from it addresses each node within that
collection. This opens a pipeline graph and walks it: Right moves node by
node, each announcing what feeds it and what it feeds and where the graph
branches and merges, with exactly that node outlined.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture(params=["one colour", "a colour per node"])
def page_path(request, tmp_path) -> Path:
    nx = pytest.importorskip("networkx")
    import matplotlib.pyplot as plt

    import maidr

    graph = nx.DiGraph(
        [
            ("load", "clean"),
            ("clean", "features"),
            ("clean", "labels"),
            ("features", "train"),
            ("labels", "train"),
        ]
    )
    colour = "lightblue" if request.param == "one colour" else ["r", "g", "b", "c", "m"]
    fig, ax = plt.subplots()
    nx.draw_networkx(
        graph, pos=nx.spring_layout(graph, seed=1), ax=ax, node_color=colour
    )
    path = tmp_path / "graph.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(fig, file=str(path), use_cdn=False)
    maidr.close(fig)
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_nodes_of_a_drawn_graph_are_walked(browser, page_path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.goto(page_path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)
    try:
        spoken = _step(page, "ArrowRight")
        assert "Node is load" in spoken and "Role is graph input" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowRight")
        assert "Node is clean" in spoken and "Role is branch point" in spoken, spoken
        assert "To is features, labels" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        for _ in range(2):
            spoken = _step(page, "ArrowRight")
        spoken = _step(page, "ArrowRight")
        assert "Node is train" in spoken and "merge point" in spoken, spoken
        assert "From is features, labels" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1
        assert not errors, errors
    finally:
        page.close()
