"""What py-maidr puts in a notebook's own page never runs ``maidr.js``.

In a notebook every chart is a ``srcdoc`` frame that loads ``maidr.js`` for
itself, from the CDN or from the copy stashed on the page, and reads nothing
else from the page. ``init_notebook()`` -- run by ``import maidr`` and again
by every ``show()`` -- also put a ``<script src>`` for the CDN copy in the
page. On a page with require.js (classic Notebook, nbconvert's HTML exports)
that copy was taken for an anonymous module and broke the page's next
``require()``; everywhere else it ran, once more per chart, over the whole
notebook.

These pin that the page gets at most a ``<link rel="prefetch">`` instead,
whatever the mode and however the markup gets there, and that it names the
copy the frames load, so the frames still find it in the browser's cache.
``tests/browser/test_notebook_page.py`` opens such a page.
"""

from __future__ import annotations

import asyncio
from html.parser import HTMLParser

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402  # activates patches
from maidr import api as maidr_api  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util import cdn, dependencies  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402

#: Set by Quarto's Jupyter engine in the kernel it renders a document with.
QUARTO_VARIABLE = "QUARTO_FIG_FORMAT"

MODES = (True, False, "auto")


class _Tags(HTMLParser):
    """The ``<script>`` and ``<link>`` elements of one output, and nothing else.

    A chart's frame is an ``<iframe srcdoc>``, so what the frame runs is an
    attribute value here and not an element of the page.
    """

    def __init__(self, html: str) -> None:
        super().__init__()
        self.scripts: list[dict] = []
        self.links: list[dict] = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "script":
            self.scripts.append(dict(attrs))
        elif tag == "link":
            self.links.append(dict(attrs))


class _Kernel:
    """The part of the kernel's IPython shell the Quarto stash uses."""

    def __init__(self) -> None:
        self.user_ns: dict = {}

    def push(self, variables: dict, interactive: bool = True) -> None:
        self.user_ns.update(variables)


@pytest.fixture
def page(monkeypatch):
    """A notebook page: every output displayed on it, in order."""
    ipython = pytest.importorskip("IPython")
    ipython_display = pytest.importorskip("IPython.display")
    displayed: list[str] = []
    kernel = _Kernel()
    monkeypatch.delenv(QUARTO_VARIABLE, raising=False)
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))
    monkeypatch.setattr(ipython, "get_ipython", lambda: kernel)
    monkeypatch.setattr(maidr_api, "_NOTEBOOK_LOADED", False)
    monkeypatch.setattr(maidr_api, "_use_cdn_default", None)
    # A chart is displayed through htmltools, the stash and the prefetch
    # through IPython.display. The module is patched rather than replaced:
    # matplotlib reads IPython's version when a figure is created.
    monkeypatch.setattr(
        "htmltools._core.Tag.show",
        lambda self, *a, **k: displayed.append(str(self)),
    )
    monkeypatch.setattr(ipython_display, "HTML", lambda html: html)
    monkeypatch.setattr(ipython_display, "display", displayed.append)
    yield displayed


def _matplotlib(use_cdn) -> None:
    fig, ax = plt.subplots()
    ax.bar(["A", "B", "C"], [1.0, 2.0, 3.0])
    try:
        FigureManager.get_maidr(fig).show(
            renderer="ipython", clear_fig=False, use_cdn=use_cdn
        )
    finally:
        plt.close(fig)


def _plotly(use_cdn) -> None:
    go = pytest.importorskip("plotly.graph_objects")
    fig = go.Figure(go.Bar(x=["A", "B", "C"], y=[1.0, 2.0, 3.0]))
    maidr.show(fig, renderer="ipython", use_cdn=use_cdn)


def _bokeh(use_cdn) -> None:
    plotting = pytest.importorskip("bokeh.plotting")
    fig = plotting.figure(x_range=["A", "B", "C"])
    fig.vbar(x=["A", "B", "C"], top=[1.0, 2.0, 3.0], width=0.5)
    maidr.show(fig, renderer="ipython", use_cdn=use_cdn)


#: Each library's ``show()`` puts the stash in the page through the same
#: helper, ahead of its frame.
SHOW = {"matplotlib": _matplotlib, "plotly": _plotly, "bokeh": _bokeh}


def _import(mode) -> None:
    """``import maidr`` in a notebook whose default is ``mode``."""
    maidr_api.set_use_cdn(mode)
    maidr_api._init_notebook_on_import()


#: Every way py-maidr puts markup in a notebook's page.
PUT = {
    "import": _import,
    "init_notebook": lambda mode: maidr.init_notebook(use_cdn=mode, force=True),
    **{f"{library} show": show for library, show in SHOW.items()},
}


def _scripts_with_a_source(displayed: list[str]) -> list[dict]:
    return [s for html in displayed for s in _Tags(html).scripts if "src" in s]


def _prefetches(displayed: list[str]) -> list[str]:
    return [
        link["href"]
        for html in displayed
        for link in _Tags(html).links
        if link.get("rel") == "prefetch"
    ]


def in_loop(call):
    """Run ``call`` as a kernel runs a cell: on an event loop."""

    async def main():
        return call()

    return asyncio.run(main())


@pytest.mark.parametrize("put", PUT)
@pytest.mark.parametrize("mode", MODES)
def test_the_page_gets_no_script_that_loads_maidr_js(page, mode, put):
    """The page itself runs nothing: ``maidr.js`` runs in the frames only."""
    PUT[put](mode)

    assert page, "nothing was displayed"
    assert _scripts_with_a_source(page) == []


def _unreadable_bundle(monkeypatch) -> None:
    monkeypatch.setattr(
        dependencies,
        "read_bundled_js",
        lambda: (_ for _ in ()).throw(FileNotFoundError("bundle missing")),
    )


@pytest.mark.parametrize("mode", MODES)
def test_nor_when_the_bundle_cannot_be_read(page, monkeypatch, mode):
    """The CDN copy is all that is left, and it is still only prefetched.

    Under ``False`` not even that: those frames run only the stash, so a
    prefetch would be a request the caller opted out of, for nothing.
    """
    _unreadable_bundle(monkeypatch)

    maidr.init_notebook(use_cdn=mode, force=True)

    if mode is False:
        assert page == []
        return
    assert _scripts_with_a_source(page) == []
    assert len(_prefetches(page)) == 1
    assert "window.__maidrJsSource" not in page[0]


@pytest.mark.parametrize("readable", [True, False], ids=["bundle", "no bundle"])
@pytest.mark.parametrize("mode", MODES)
def test_nor_in_a_quarto_render(page, monkeypatch, mode, readable):
    """A call by hand there puts no copy in the page the render builds either.

    Its charts are written into the page and load ``maidr.js`` themselves
    (#895), at the version the render resolves (#888), which need not be
    the one a prefetch would name. So ``init_notebook()`` adds the stash
    and nothing else, as #896 left ``"auto"``.
    """
    monkeypatch.setenv(QUARTO_VARIABLE, "png")
    if not readable:
        _unreadable_bundle(monkeypatch)

    maidr.init_notebook(use_cdn=mode, force=True)

    assert _scripts_with_a_source(page) == []
    assert _prefetches(page) == []
    stashed = readable and mode is not True
    assert len(page) == (1 if stashed else 0)


@pytest.mark.parametrize("mode", MODES)
def test_the_stash_stays_where_the_frames_read_it(page, mode):
    """The frames' copy under ``False`` and ``"auto"`` is untouched."""
    maidr.init_notebook(use_cdn=mode, force=True)

    stashed = "window.__maidrJsSource = " in page[0]
    assert stashed is (mode is not True)
    assert ("window.__maidrMathCssSource = " in page[0]) is stashed
    assert len(_prefetches(page)) == (0 if mode is False else 1)


@pytest.mark.parametrize("library", SHOW)
@pytest.mark.parametrize("mode", [True, "auto"])
def test_the_prefetch_names_the_copy_the_frames_load(
    page, monkeypatch, forbid_network, library, mode
):
    """So a frame's own load of it is served from the browser's cache.

    As a notebook runs it on the default setting: no pin, and every cell on
    the kernel's event loop, where the frames load the bundled version
    rather than resolve one.
    """
    monkeypatch.delenv(cdn.CDN_VERSION_ENV_VAR, raising=False)
    cdn.set_cdn_version(None)
    cdn.reset_cdn_version_cache()

    def session() -> None:
        _import(mode)
        SHOW[library](mode)

    in_loop(session)

    frames = [html for html in page if "<iframe" in html]
    prefetched = _prefetches(page)
    bundled = f"maidr@{dependencies.maidr_js_version()}/dist/maidr.js"
    assert len(frames) == 1
    assert prefetched, "the page prefetches nothing"
    for url in prefetched:
        assert url.endswith(bundled)
        assert url in frames[0], f"the frame does not load {url}"
