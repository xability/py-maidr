"""A notebook's own page never runs ``maidr.js``; its charts' frames do.

``tests/core/test_notebook_page.py`` pins the markup. This opens it: a page
shaped like an nbconvert HTML export of a notebook that ran ``import maidr``
and then showed two charts, with the outputs those calls displayed, in order.
Its head has what such a page has there: require.js, which takes an anonymous
``define()`` for a module of its own and then fails the page's next
``require()`` over it -- here a stand-in that counts them. Every request to
jsDelivr for ``maidr.js`` is answered with the bundled copy, so a
``<script src>`` for it in the page would really run, as it did before.

For each ``use_cdn`` mode it checks that the page ran no ``maidr.js``, that
both frames did, and that the page fetched the copy the frames load only as
a prefetch. A page whose requests are routed is not cached, so that the
frames are then served the prefetched copy is not something it can show.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import matplotlib.pyplot as plt
import pytest

import maidr
from maidr import api as maidr_api
from maidr.util.dependencies import bundled_js_path
from maidr.util.environment import Environment

if TYPE_CHECKING:
    from playwright.sync_api import Browser

pytestmark = pytest.mark.browser

_PARSE_TIMEOUT_MS = 30_000

#: require.js, as far as a script that loads ``maidr.js`` can tell. Named
#: modules are left alone: only an anonymous one makes require.js fail.
_HEAD = """
<script>
  window.__anonymousDefines = 0;
  window.define = function (name) {
    if (typeof name !== 'string') window.__anonymousDefines += 1;
  };
  window.define.amd = {};
</script>
"""

_CDN = re.compile(r"^https://cdn\.jsdelivr\.net/npm/maidr@")

#: Read in the notebook's own page.
_PAGE = """() => ({
  anonymousDefines: window.__anonymousDefines,
  maidrLive: typeof window.maidrLive,
  scripts: [...document.querySelectorAll('script[src]')].map(s => s.src),
  prefetches: [...document.querySelectorAll('link[rel=prefetch]')].map(l => l.href),
  articles: document.querySelectorAll('article[id^=maidr-article-]').length,
})"""

_CHART_READY = "() => document.querySelector('article[id^=maidr-article-]') !== null"


def _notebook(tmp_path: Path, mode: bool | str) -> str:
    """
    A notebook's page: ``import maidr``, then two charts shown.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Where to write the page.
    mode : bool or {"auto"}
        The notebook's ``use_cdn`` setting.

    Returns
    -------
    str
        The page's ``file://`` URL.
    """
    displayed: list[str] = []
    with (
        mock.patch.dict("os.environ", {"QUARTO_FIG_FORMAT": ""}),
        mock.patch.object(Environment, "is_notebook", return_value=True),
        mock.patch.object(maidr_api, "_NOTEBOOK_LOADED", False),
        mock.patch.object(maidr_api, "_use_cdn_default", mode),
        mock.patch("IPython.display.HTML", lambda html: html),
        mock.patch("IPython.display.display", displayed.append),
        mock.patch(
            "htmltools._core.Tag.show",
            lambda self, *a, **k: displayed.append(str(self)),
        ),
    ):
        maidr_api._init_notebook_on_import()
        for title in ("First", "Second"):
            fig, ax = plt.subplots(figsize=(5, 3))
            ax.bar(["a", "b", "c"], [1, 3, 2])
            ax.set_title(title)
            try:
                maidr.show(fig, renderer="ipython")
            finally:
                plt.close(fig)
    assert sum("<iframe" in html for html in displayed) == 2
    body = "".join(f'<div class="output_html">{html}</div>' for html in displayed)
    out = tmp_path / "notebook.html"
    out.write_text(
        f'<!doctype html><html><head><meta charset="utf-8">{_HEAD}</head>'
        f"<body>{body}</body></html>",
        encoding="utf-8",
    )
    return out.as_uri()


@pytest.mark.parametrize("mode", [True, False, "auto"])
def test_only_the_frames_run_maidr_js(
    browser: Browser, tmp_path: Path, mode: bool | str
) -> None:
    requested: list[tuple[str, str]] = []

    def cdn(route, request) -> None:
        requested.append((request.url, request.resource_type))
        if request.url.endswith("/dist/maidr.js"):
            route.fulfill(
                path=str(bundled_js_path()),
                content_type="application/javascript; charset=utf-8",
            )
        else:
            route.abort()

    page = browser.new_page()
    try:
        page.route(_CDN, cdn)
        page.goto(_notebook(tmp_path, mode), wait_until="load")
        frames = page.frames[1:]
        assert len(frames) == 2
        for frame in frames:
            frame.wait_for_function(_CHART_READY, timeout=_PARSE_TIMEOUT_MS)
        notebook = page.evaluate(_PAGE)
    finally:
        page.close()

    assert notebook["anonymousDefines"] == 0, (
        "the notebook's page handed require.js an anonymous module"
    )
    assert notebook["maidrLive"] == "undefined", "maidr.js ran in the notebook's page"
    assert notebook["articles"] == 0
    assert not [src for src in notebook["scripts"] if "maidr" in src]

    loaded = {url for url, kind in requested if kind == "script"}
    if mode is False:
        # Each frame runs the stashed copy, and the page asks for nothing.
        assert requested == []
        assert notebook["prefetches"] == []
        return
    # Each frame loads the CDN copy itself, and the page prefetched that one:
    # fetches that run nothing, and one script per frame. How many links of
    # the page's become a fetch of their own is the browser's business.
    assert len(loaded) == 1
    assert set(notebook["prefetches"]) == loaded
    kinds = [kind for url, kind in requested if url in loaded]
    assert kinds.count("script") == 2
    assert "other" in kinds, "the page did not prefetch the frames' copy"
    assert set(kinds) == {"other", "script"}
