"""A figure whose axes leave a hole in the grid still becomes navigable.

``tests/core/test_subplot_grid_gaps.py`` asserts that every emitted grid
position carries ``layers``. That is a schema check, and a schema check
cannot tell whether the core accepts the schema -- which is the whole
question here, because the core is where the cost lands: ``Subplot``'s
constructor reads ``subplot.layers.length`` unguarded, so one bare
position throws during figure construction and *no* part of the chart
initialises.

The failure is silent in the way that matters most. The SVG draws, the
page looks finished, and pressing the key that should start navigation
does nothing at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

#: Built only once the core has finished constructing the figure, so its
#: presence is the initialisation this test is about. Chosen over a node
#: count, which moves whenever the UI gains a wrapper.
_RUNTIME_UI = "#maidr-text-container"

#: Installed on `window` by the bundle, so it appears once the ~1.5 MB of
#: inlined JavaScript has parsed. Waited on rather than slept through: the
#: other browser tests settle on a fixed timeout because they have a server
#: to outlast as well, and a static file has no such thing to wait for.
_BUNDLE_READY = "() => window.maidrLive !== undefined"

#: Only how long that parse may take on a slow runner, not a pacing guess.
_PARSE_TIMEOUT_MS = 30_000


def _page_with(browser, path: Path):
    """Open a saved chart and return the page plus its uncaught errors."""
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.goto(path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    return page, errors


def _save(fig, path: Path) -> Path:
    import maidr

    # Bundled rather than CDN: this must not depend on a network, and the
    # bundle is what an offline reader gets anyway.
    maidr.save_html(fig, file=str(path), use_cdn=False)
    return path


@pytest.fixture
def gapped_chart(tmp_path):
    """``subplots(1, 3)`` with the middle axes never drawn on."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import maidr  # noqa: F401  # activates patches

    fig, axs = plt.subplots(1, 3)
    axs[0].bar(["p", "q"], [1, 2])
    axs[2].bar(["p", "q"], [3, 4])
    try:
        yield _save(fig, tmp_path / "gapped.html")
    finally:
        plt.close("all")


def test_a_grid_with_an_empty_position_still_starts(browser, gapped_chart):
    """Activation builds the runtime UI and raises nothing."""
    page, errors = _page_with(browser, gapped_chart)
    try:
        page.click("svg[maidr]", force=True)
        page.keyboard.press("Enter")
        page.wait_for_timeout(2_000)

        assert not errors, (
            f"activation threw {errors}. A position with no `layers` makes "
            f"the core's Subplot constructor read `.length` of undefined, "
            f"which aborts the whole figure -- not just the empty position."
        )
        assert page.query_selector(_RUNTIME_UI) is not None, (
            "the runtime UI was never built, so the chart cannot be driven "
            "from the keyboard however complete its SVG looks."
        )
    finally:
        page.close()
