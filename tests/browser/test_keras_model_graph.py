"""A Keras model's graph is driven from the keyboard.

``maidr.keras.plot_model`` emits a ``directed_graph`` layer, which only a
maidr.js carrying that trace can read, and the markup tests cannot tell
whether the bundled one does. This opens a model with a skip connection
around a nested ``Sequential`` block, drawn with ``expand_nested=True``:
Right walks the layers input to output, each saying what feeds it and what
it feeds and where the data branches and merges, Down opens the block onto
its own layers and Up closes it again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

MODEL = (
    Path(__file__).parent.parent / "tensorboard" / "fixtures" / "keras_graph.model.json"
)

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture
def page_path(tmp_path) -> Path:
    import maidr
    from maidr.keras import plot_model

    figure = plot_model(MODEL.read_text(), expand_nested=True)
    path = tmp_path / "model.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(figure, file=str(path), use_cdn=False)
    maidr.close(figure)
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_layers_and_scopes_of_a_model_graph_are_read(browser, page_path):
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
        assert "Layer is features" in spoken, spoken
        assert "Role is graph input" in spoken, spoken
        assert "Order is 1 of 5" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowRight")
        assert "Layer is dense_in" in spoken, spoken
        assert "Role is branch point" in spoken, spoken
        assert "To is residual_block, skip" in spoken, spoken

        spoken = _step(page, "ArrowRight")
        assert "Layer is residual_block, Scope is 2 nodes inside" in spoken, spoken

        # Down opens the nested model onto its own layers.
        spoken = _step(page, "ArrowDown")
        assert "Layer is block_dense_1, Path is residual_block" in spoken, spoken
        assert "Order is 1 of 2" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowRight")
        assert "Layer is block_dense_2" in spoken and "To is skip" in spoken, spoken

        # Up closes it again, and Right goes on past it to the merge.
        spoken = _step(page, "ArrowUp")
        assert "Layer is residual_block" in spoken, spoken
        spoken = _step(page, "ArrowRight")
        assert "Layer is skip" in spoken, spoken
        assert "Role is merge point" in spoken, spoken
        assert "From is dense_in, residual_block" in spoken, spoken
        assert not errors, errors
    finally:
        page.close()
