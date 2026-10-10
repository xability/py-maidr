"""A Quarto render that builds a web page writes its charts into it (#895).

In a render whose output is a page a browser runs -- an ``html`` document,
website, book or dashboard, or a ``revealjs`` deck -- a matplotlib chart is
written into the page rather than an iframe of its own. These pin what that
takes, as markup: when it happens and when the iframe stays, that every
chart's ids and selectors are its own, that the SVG's ``<style>`` and
``<metadata>`` stay out of the page, that the chart carries the bundle under
the same rule as a frame does, and in the same output as the chart. Whether
the result works in a browser is ``tests/browser/test_quarto_inline.py``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from lxml import etree  # noqa: E402

import maidr  # noqa: E402, F401  # activates patches
from maidr import api as maidr_api  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util import inline_chart  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402
from maidr.util.inline_chart import InlineScope, InlineUnsupported  # noqa: E402

SVG = "http://www.w3.org/2000/svg"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class _Kernel:
    """The part of the kernel's IPython shell the stash uses."""

    def __init__(self) -> None:
        self.user_ns: dict = {}

    def push(self, variables: dict, interactive: bool = True) -> None:
        self.user_ns.update(variables)


def _execute_info(tmp_path, writer: str) -> str:
    """A file shaped like the one ``QUARTO_EXECUTE_INFO`` names."""
    path = tmp_path / f"info-{writer}.json"
    # The figure format is each writer's default in Quarto 1.10.
    figure_format = "retina" if writer in ("html", "revealjs") else "png"
    document_format = {
        "pandoc": {"to": writer},
        "execute": {"fig-format": figure_format},
    }
    path.write_text(
        json.dumps({"document-path": "doc.qmd", "format": document_format}),
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def quarto(monkeypatch, tmp_path):
    """The kernel of a Quarto render; call it with the format's pandoc writer."""
    ipython = pytest.importorskip("IPython")
    kernel = _Kernel()
    monkeypatch.setenv("QUARTO_FIG_FORMAT", "png")
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))
    monkeypatch.setattr(ipython, "get_ipython", lambda: kernel)
    monkeypatch.setattr(maidr_api, "_NOTEBOOK_LOADED", False)

    def render_to(writer: str = "html") -> _Kernel:
        monkeypatch.setenv("QUARTO_EXECUTE_INFO", _execute_info(tmp_path, writer))
        return kernel

    return render_to


def _bar(title: str = "Sales", gid: str | None = None):
    fig, ax = plt.subplots()
    ax.bar(["A", "B", "C"], [1.0, 2.0, 3.0], gid=gid)
    ax.set_title(title)
    return fig


def _line(gid: str):
    """A line, whose selector names its group by ``gid`` (a bar's names a uuid)."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [3.0, 1.0, 2.0], gid=gid)
    return fig


def _render(fig, use_cdn="auto") -> str:
    try:
        return str(FigureManager.get_maidr(fig).render(use_cdn=use_cdn))
    finally:
        plt.close(fig)


def _shown(fig, use_cdn="auto") -> str:
    """A chart as ``show()`` renders it: displayed in the page at once."""
    with inline_chart.showing():
        return _render(fig, use_cdn)


def _svg(html: str):
    """The chart's ``<svg>`` as an element, parsed from the chart's output."""
    start = html.index("<svg")
    end = html.index("</svg>", start) + len("</svg>")
    return etree.fromstring(html[start:end].encode())


def _schema(svg) -> dict:
    return json.loads(svg.get("maidr"))


def _selectors(value):
    """Every selector string in a schema, at any depth."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("selector", "selectors"):
                yield from _strings(item)
            else:
                yield from _selectors(item)
    elif isinstance(value, list):
        for item in value:
            yield from _selectors(item)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


# --- When a chart is written into the page -----------------------------------


def test_the_writer_is_read_from_the_file_quarto_names(monkeypatch, tmp_path):
    monkeypatch.setenv("QUARTO_FIG_FORMAT", "png")
    monkeypatch.setenv("QUARTO_EXECUTE_INFO", _execute_info(tmp_path, "revealjs"))
    assert Environment.quarto_writer() == "revealjs"
    assert Environment.is_quarto_page() is True


@pytest.mark.parametrize("writer", ["html", "html4", "html5", "revealjs"])
def test_a_page_is_html_or_a_deck(monkeypatch, tmp_path, writer):
    monkeypatch.setenv("QUARTO_FIG_FORMAT", "png")
    monkeypatch.setenv("QUARTO_EXECUTE_INFO", _execute_info(tmp_path, writer))
    assert Environment.is_quarto_page() is True


@pytest.mark.parametrize("writer", ["ipynb", "commonmark", "latex", "docx", "typst"])
def test_other_formats_are_not_pages(monkeypatch, tmp_path, writer):
    monkeypatch.setenv("QUARTO_FIG_FORMAT", "png")
    monkeypatch.setenv("QUARTO_EXECUTE_INFO", _execute_info(tmp_path, writer))
    assert Environment.is_quarto_page() is False


def test_no_render_no_page(monkeypatch, tmp_path):
    """Outside a render, and under a Quarto older than 1.8, there is none."""
    monkeypatch.setenv("QUARTO_EXECUTE_INFO", _execute_info(tmp_path, "html"))
    monkeypatch.delenv("QUARTO_FIG_FORMAT", raising=False)
    assert Environment.quarto_writer() is None

    monkeypatch.setenv("QUARTO_FIG_FORMAT", "png")
    monkeypatch.delenv("QUARTO_EXECUTE_INFO")
    assert Environment.quarto_writer() is None


@pytest.mark.parametrize("content", ["{", "[]", '{"format": {}}', "null"])
def test_a_file_that_cannot_be_read_keeps_the_iframe(monkeypatch, tmp_path, content):
    path = tmp_path / "info.json"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setenv("QUARTO_FIG_FORMAT", "png")
    monkeypatch.setenv("QUARTO_EXECUTE_INFO", str(path))
    assert Environment.quarto_writer() is None
    assert Environment.is_quarto_page() is False


def test_a_missing_file_keeps_the_iframe(monkeypatch, tmp_path):
    monkeypatch.setenv("QUARTO_FIG_FORMAT", "png")
    monkeypatch.setenv("QUARTO_EXECUTE_INFO", str(tmp_path / "gone.json"))
    assert Environment.is_quarto_page() is False


def test_the_file_is_read_again_when_it_changes(monkeypatch, tmp_path):
    """``quarto preview`` keeps one kernel, and one file, across renders."""
    path = tmp_path / "info.json"
    monkeypatch.setenv("QUARTO_FIG_FORMAT", "png")
    monkeypatch.setenv("QUARTO_EXECUTE_INFO", str(path))
    path.write_text(json.dumps({"format": {"pandoc": {"to": "html"}}}))
    assert Environment.quarto_writer() == "html"

    path.write_text(json.dumps({"format": {"pandoc": {"to": "ipynb"}}}))
    assert Environment.quarto_writer() == "ipynb"


def _later_render(kernel) -> None:
    """What a kept-alive kernel goes through between two renders: ``%reset``."""
    kernel.user_ns.clear()


def test_a_kept_alive_kernel_trusts_the_file_while_its_format_is_this_renders(
    quarto, monkeypatch
):
    """``quarto preview`` and a second render in the same format."""
    from maidr.util import environment

    kernel = quarto("html")
    assert Environment.quarto_writer() == "html"

    _later_render(kernel)
    monkeypatch.setattr(environment, "_figure_format", lambda: "retina")
    assert Environment.quarto_writer() == "html"


def test_a_kept_alive_kernel_remembers_a_file_quarto_has_deleted(quarto, monkeypatch):
    """A second ``quarto render`` deletes the first render's file, not the variable."""
    import os

    from maidr.util import environment

    kernel = quarto("html")
    assert Environment.quarto_writer() == "html"

    _later_render(kernel)
    os.remove(os.environ["QUARTO_EXECUTE_INFO"])
    monkeypatch.setattr(environment, "_figure_format", lambda: "retina")
    assert Environment.quarto_writer() == "html"


def test_a_kept_alive_kernel_serving_another_format_keeps_the_iframe(
    quarto, monkeypatch
):
    """One ``quarto render`` of html then ipynb: the file still names html."""
    from maidr.util import environment

    kernel = quarto("html")
    assert Environment.quarto_writer() == "html"

    _later_render(kernel)
    monkeypatch.setattr(environment, "_figure_format", lambda: "png")
    assert Environment.quarto_writer() is None
    assert "<iframe" in _render(_bar())


def test_the_figure_format_quarto_set_up_is_read_off_the_display_formatter():
    """The setup cell's ``set_matplotlib_formats`` is what is left of it."""
    pytest.importorskip("matplotlib_inline")
    from IPython.core.interactiveshell import InteractiveShell
    from matplotlib_inline.backend_inline import set_matplotlib_formats

    from maidr.util import environment

    shell = InteractiveShell.instance()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("IPython.get_ipython", lambda: shell)
        for figure_format in ("retina", "png", "svg"):
            set_matplotlib_formats(figure_format)
            assert environment._figure_format() == figure_format


def test_a_page_gets_the_chart_itself(quarto):
    quarto("html")
    html = _render(_bar())

    assert 'class="maidr-inline"' in html
    assert "<iframe" not in html
    assert _svg(html).get("maidr")


@pytest.mark.parametrize("writer", ["ipynb", "commonmark"])
def test_a_format_that_is_not_a_page_keeps_the_iframe(quarto, writer):
    quarto(writer)
    html = _render(_bar())

    assert "<iframe" in html
    assert "maidr-inline" not in html


def test_a_quarto_older_than_1_8_keeps_the_iframe(quarto, monkeypatch):
    quarto("html")
    monkeypatch.delenv("QUARTO_EXECUTE_INFO")
    html = _render(_bar())

    assert "<iframe" in html
    assert "maidr-inline" not in html


def test_a_notebook_keeps_the_iframe(quarto, monkeypatch):
    """Not a render at all: the iframe keeps Jupyter's keys off the chart."""
    quarto("html")
    monkeypatch.delenv("QUARTO_FIG_FORMAT")
    html = _render(_bar())

    assert "<iframe" in html
    assert "maidr-inline" not in html


@pytest.mark.parametrize("host", ["is_shiny", "is_flask"])
def test_a_host_with_its_own_frame_keeps_it(quarto, monkeypatch, host):
    quarto("html")
    monkeypatch.setattr(Environment, host, staticmethod(lambda: True))
    html = _render(_bar())

    assert "maidr-inline" not in html


def test_save_html_is_still_a_document_of_its_own(quarto, tmp_path):
    quarto("html")
    fig = _bar()
    try:
        path = FigureManager.get_maidr(fig).save_html(str(tmp_path / "chart.html"))
    finally:
        plt.close(fig)
    html = (tmp_path / "chart.html").read_text(encoding="utf-8")

    assert path
    assert "maidr-inline" not in html


def test_a_document_of_its_own_made_during_a_render_stays_one(quarto):
    """Streamlit, Gradio and an MLflow artifact are never one of the page's charts."""
    from maidr.widget import _document

    kernel = quarto("html")
    fig = _bar()
    try:
        html, _title = _document.render(fig, use_cdn="auto", stacklevel=2)
    finally:
        plt.close(fig)

    assert "maidr-inline" not in html
    assert maidr_api._QUARTO_STASHED not in kernel.user_ns


# --- One chart's ids are its own ---------------------------------------------


def test_every_id_is_the_charts_own(quarto):
    quarto("html")
    first, second = _svg(_render(_line("series"))), _svg(_render(_line("series")))

    def ids(svg):
        return {element.get("id") for element in svg.iter() if element.get("id")}

    assert ids(first).isdisjoint(ids(second))


def test_matplotlib_ids_keep_the_start_maidr_js_reads(quarto):
    """maidr.js finds a panel by ``g[id^="axes_"]``: a suffix, not a prefix."""
    quarto("html")
    svg = _svg(_render(_bar()))
    ids = [element.get("id") for element in svg.iter() if element.get("id")]

    assert any(re.fullmatch(r"axes_1-m[0-9a-f]{12}", i) for i in ids)
    assert any(re.fullmatch(r"figure_1-m[0-9a-f]{12}", i) for i in ids)


def test_only_the_svgs_own_id_is_left_as_it_is(quarto):
    """It is the schema's, which maidr.js finds the chart by, and new per render."""
    quarto("html")
    svg = _svg(_render(_bar()))

    assert svg.get("id") == _schema(svg)["id"]
    for element in svg.iter():
        if element is not svg and element.get("id"):
            assert re.search(r"-m[0-9a-f]{12}$", element.get("id")), element.get("id")


def test_one_figure_shown_twice_shares_nothing_between_its_outputs(quarto):
    """py-maidr mints a figure's group ids and marks once, not per render."""
    quarto("html")
    fig = _bar()
    try:
        maidr_figure = FigureManager.get_maidr(fig)
        first = _svg(str(maidr_figure.render()))
        second = _svg(str(maidr_figure.render()))
    finally:
        plt.close(fig)

    def names(svg):
        return {
            value
            for element in svg.iter()
            for value in (element.get("id"), element.get("maidr"))
            if value and not value.startswith("{")
        }

    def selectors(svg):
        return set(_selectors(_schema(svg)))

    assert names(first).isdisjoint(names(second))
    assert selectors(first).isdisjoint(selectors(second))


def test_every_reference_finds_its_own_chart(quarto):
    quarto("html")
    svg = _svg(_render(_bar()))
    ids = {element.get("id") for element in svg.iter() if element.get("id")}
    xlink = "{http://www.w3.org/1999/xlink}href"

    references = []
    for element in svg.iter():
        for name, value in element.attrib.items():
            if name == "maidr":
                continue
            references += re.findall(r"url\(#([^)]+)\)", value)
            if name in ("href", xlink) and value.startswith("#"):
                references.append(value[1:])
    assert references
    assert set(references) <= ids


def test_a_shared_gid_names_each_charts_own_group(quarto):
    """Two charts drawn with the same gid: each selector finds only its own."""
    quarto("html")
    first, second = _svg(_render(_line("series"))), _svg(_render(_line("series")))

    for svg in (first, second):
        groups = {element.get("id") for element in svg.iter(f"{{{SVG}}}g")}
        named = [
            match
            for selector in _selectors(_schema(svg))
            for match in re.findall(r"\[id='([^']+)'\]", selector)
        ]
        assert named
        assert set(named) <= groups
        assert all(name.startswith("series-m") for name in named)


def test_every_selector_is_anchored_to_its_chart(quarto):
    quarto("html")
    svg = _svg(_render(_line("series")))
    key = re.search(r"-(m[0-9a-f]{12})", svg.find(f"{{{SVG}}}g").get("id")).group(1)

    for selector in _selectors(_schema(svg)):
        for part in inline_chart._split_selector(selector):
            assert UUID.search(part) or key in part, selector


def test_a_gid_that_only_contains_a_uuid_is_made_the_charts_own(quarto):
    """Only an id py-maidr minted is unique already; a user's may repeat."""
    quarto("html")
    gid = "series-6f1c2c1e-6d2b-4f8e-9a0b-1c2d3e4f5a6b"
    first, second = _svg(_render(_line(gid))), _svg(_render(_line(gid)))

    def ids(svg):
        return {element.get("id") for element in svg.iter() if element.get("id")}

    assert ids(first).isdisjoint(ids(second))


def _scope(markup: str, schema: dict, name: str = "Chart") -> tuple[InlineScope, dict]:
    svg = etree.fromstring(markup.encode())
    scope = InlineScope(name)
    return scope, scope.scope(svg, schema)


SVG_ID = "6f1c2c1e-6d2b-4f8e-9a0b-1c2d3e4f5a6b"


def test_a_selector_that_names_nothing_of_its_own_is_scoped_to_the_chart():
    """The violin and regression layers' fallback names every chart's marks."""
    markup = (
        f'<svg xmlns="{SVG}" id="{SVG_ID}"><g id="maidr-{SVG_ID}"><path/></g></svg>'
    )
    scope, schema = _scope(
        markup, {"layers": [{"selectors": ["g[id^='maidr-'] path", "path, g"]}]}
    )

    assert schema["layers"][0]["selectors"] == [
        f"[id=\"{SVG_ID}\"] g[id^='maidr-'] path",
        f'[id="{SVG_ID}"] path,[id="{SVG_ID}"] g',
    ]


def test_a_uuid_outside_an_id_test_does_not_make_a_selector_the_charts_own():
    markup = f'<svg xmlns="{SVG}" id="{SVG_ID}"><g id="maidr-{SVG_ID}"/></svg>'
    scope, schema = _scope(
        markup, {"selectors": f"g[id^='maidr-'] path[data-x='{SVG_ID}']"}
    )

    assert schema["selectors"].startswith(f'[id="{SVG_ID}"] ')


def test_a_style_names_the_charts_own_definitions():
    markup = (
        f'<svg xmlns="{SVG}" id="{SVG_ID}"><defs><linearGradient id="grad"/></defs>'
        "<style>path { fill: url(#grad) }</style></svg>"
    )
    scope, _schema = _scope(markup, {})

    assert f"url(#grad-{scope.key})" in scope.css


def test_an_id_that_starts_another_is_renamed_on_its_own():
    markup = f'<svg xmlns="{SVG}" id="{SVG_ID}"><g id="series"/><g id="series2"/></svg>'
    scope, schema = _scope(
        markup, {"selectors": ["g[id='series'] path", "g[id='series2'] path"]}
    )

    assert schema["selectors"] == [
        f"g[id='series-{scope.key}'] path",
        f"g[id='series2-{scope.key}'] path",
    ]


def test_selector_commas_inside_brackets_and_parentheses_are_not_split():
    parts = inline_chart._split_selector(
        "g[id='a,b'] > :nth-child(n+2 of use, path), g[maidr='x']"
    )
    assert parts == ["g[id='a,b'] > :nth-child(n+2 of use, path)", " g[maidr='x']"]


def test_the_selectors_of_boxes_and_candles_are_scoped_at_any_depth():
    markup = f'<svg xmlns="{SVG}" id="{SVG_ID}"><g id="box"/></svg>'
    _scope_, schema = _scope(
        markup,
        {
            "selectors": [
                {"iq": "g[id='box'] > path", "q2": None, "min": ["g[id='box']"]}
            ]
        },
    )
    box = schema["selectors"][0]

    assert box["iq"].startswith("g[id='box-m")
    assert box["q2"] is None
    assert box["min"][0].startswith("g[id='box-m")


def test_aria_references_follow_their_ids():
    markup = (
        f'<svg xmlns="{SVG}" id="{SVG_ID}"><title id="t">T</title>'
        f'<g id="g" aria-labelledby="t missing"/></svg>'
    )
    svg = etree.fromstring(markup.encode())
    InlineScope("Chart").scope(svg, {})
    group = svg.find(f"{{{SVG}}}g")

    title_id = svg.find(f"{{{SVG}}}title").get("id")
    assert group.get("aria-labelledby") == f"{title_id} missing"


# --- What stays out of the page ----------------------------------------------


def test_the_svg_keeps_no_style_or_metadata(quarto):
    quarto("html")
    svg = _svg(_render(_bar()))

    assert next(svg.iter(f"{{{SVG}}}style"), None) is None
    assert next(svg.iter(f"{{{SVG}}}metadata"), None) is None


def test_the_style_is_scoped_to_its_chart(quarto):
    """matplotlib's ``*{stroke-linejoin: round}`` would restyle the whole page."""
    quarto("html")
    html = _render(_bar())
    svg = _svg(html)
    chart_class = next(
        c
        for c in svg.get("class").split()
        if re.fullmatch(r"maidr-inline-m[0-9a-f]{12}", c)
    )

    rules = re.findall(r"<style>([^<]*stroke-linejoin[^<]*)</style>", html)
    assert rules
    for selector in re.findall(r"([^{}]+)\{", rules[0]):
        for part in selector.split(","):
            assert part.strip().startswith(f".{chart_class}"), part


@pytest.mark.parametrize(
    "inside", ["<script>alert(1)</script>", "<foreignObject><div/></foreignObject>"]
)
def test_an_svg_that_cannot_be_scoped_is_left_as_it_was(inside):
    markup = f'<svg xmlns="{SVG}" id="{SVG_ID}"><g id="axes_1"/>{inside}</svg>'
    svg = etree.fromstring(markup.encode())
    before = etree.tostring(svg)

    with pytest.raises(InlineUnsupported):
        InlineScope("Chart").scope(svg, {})
    assert etree.tostring(svg) == before


def test_a_style_with_an_at_rule_cannot_be_scoped():
    markup = (
        f'<svg xmlns="{SVG}" id="{SVG_ID}"><g id="axes_1"/>'
        f"<style>@media print {{ * {{ fill: none }} }}</style></svg>"
    )
    svg = etree.fromstring(markup.encode())
    before = etree.tostring(svg)

    with pytest.raises(InlineUnsupported):
        InlineScope("Chart").scope(svg, {})
    assert etree.tostring(svg) == before


def test_a_chart_that_cannot_be_scoped_is_framed_as_before(quarto, monkeypatch):
    quarto("html")

    def refuse(self, svg, schema):
        raise InlineUnsupported("the test said so")

    monkeypatch.setattr(InlineScope, "scope", refuse)
    with pytest.warns(UserWarning, match="iframe rather than in the page"):
        html = _render(_bar())

    assert "<iframe" in html
    assert "maidr-inline" not in html


@pytest.mark.parametrize("use_cdn", [False, True, "auto"])
def test_nothing_a_chart_writes_reads_as_a_dashboard_component(quarto, use_cdn):
    """Quarto's dashboard filter lifts any output holding ``bslib-`` out of its card.

    In a Lua pattern the ``-`` is a lazy quantifier, so ``bsli`` anywhere is
    enough: a chart that held it left its card, and a card with nothing else
    in it disappeared, title and all.
    """
    quarto("html")
    html = _shown(_bar(), use_cdn=use_cdn)

    assert "bsli" not in html


def test_the_svg_carries_no_indentation_into_the_page(quarto):
    """It is text in the page, which a site's search indexes."""
    quarto("html")
    svg = _svg(_render(_bar()))
    text_elements = {f"{{{SVG}}}{tag}" for tag in ("text", "tspan", "title", "desc")}

    for element in svg.iter():
        if element.tag not in text_elements:
            assert element.text is None or element.text.strip(), element.tag
        assert element.tail is None or element.tail.strip(), element.tag


# --- Names -------------------------------------------------------------------


def _wrapper(html: str) -> str:
    return html[: html.index(">") + 1]


def test_the_chart_is_named_until_maidr_js_names_it(quarto):
    """On the wrapper: the svg is hidden, since a deck reads its text aloud."""
    quarto("html")
    html = _render(_bar(title="Sales"))
    svg = _svg(html)

    assert _wrapper(html) == (
        '<div class="maidr-inline" role="img" aria-label="Sales, accessible chart"'
        ' data-maidr-inline="" data-lm-suppress-shortcuts="">'
    )
    assert svg.get("aria-hidden") == "true"
    assert svg.get("role") is None


def test_the_title_stays_as_a_description(quarto):
    """It named the frame (#453); inline.js points maidr's element at it."""
    quarto("html")
    html = _render(_bar(title="Sales"))
    svg_id = _svg(html).get("id")

    assert re.search(
        rf'<span id="{svg_id}-title" class="maidr-inline-title" hidden[^>]*>Sales</span>',
        html,
    )


def test_an_untitled_chart_has_no_description_to_carry(quarto):
    quarto("html")
    html = _render(_bar(title=""))

    assert 'class="maidr-inline-title"' not in html
    assert 'aria-label="Accessible chart"' in _wrapper(html)


# --- maidr.js and the bundle -------------------------------------------------


def _copies(html: str) -> int:
    return html.count("window.__maidrJsSource = ")


def test_auto_stashes_the_bundle_once_per_render(quarto):
    kernel = quarto("html")
    outputs = [_shown(_bar()) for _ in range(3)]

    assert [_copies(html) for html in outputs] == [1, 0, 0]

    kernel.user_ns.clear()  # Quarto's ``%reset`` after a render
    assert _copies(_shown(_bar())) == 1


def test_a_render_that_may_never_be_displayed_takes_the_stash_from_no_one(quarto):
    """``render()`` returns the chart; only ``show()`` is sure it reaches the page."""
    quarto("html")

    assert _copies(_render(_bar())) == 1
    assert _copies(_shown(_bar())) == 1
    assert _copies(_shown(_bar())) == 0


def test_offline_every_chart_carries_the_bundle(quarto):
    quarto("html")
    outputs = [_shown(_bar(), use_cdn=False) for _ in range(2)]

    assert [_copies(html) for html in outputs] == [1, 1]


def test_the_cdn_alone_needs_no_bundle(quarto):
    kernel = quarto("html")
    html = _shown(_bar(), use_cdn=True)

    assert _copies(html) == 0
    assert maidr_api._QUARTO_STASHED not in kernel.user_ns


def test_an_unreadable_bundle_is_not_marked_as_stashed(quarto, monkeypatch):
    """A Plotly frame later in the render must not count on a copy never made."""
    kernel = quarto("html")
    monkeypatch.setattr(maidr_api, "_bundle_stash_script", lambda: None)
    html = _shown(_bar())

    assert _copies(html) == 0
    assert maidr_api._QUARTO_STASHED not in kernel.user_ns


def test_offline_with_an_unreadable_bundle_loads_the_same_version_by_url(
    quarto, monkeypatch, caplog
):
    quarto("html")
    monkeypatch.setattr(maidr_api, "_bundle_stash_script", lambda: None)
    html = _render(_bar(), use_cdn=False)

    assert "could not be read" in caplog.text
    assert "fromUrl(" in html
    assert "/maidr@" in html


def test_every_chart_carries_the_guards_and_a_loader(quarto):
    """So a chart whose cell hides its output takes nothing from the next."""
    quarto("html")
    outputs = [_shown(_bar()) for _ in range(2)]

    for html in outputs:
        assert "window.__maidrInline = true" in html
        assert "__maidrInlineLoader" in html
        assert "maidr-inline-contrast" in html  # inline.css


def test_the_chart_and_its_runtime_are_one_output(quarto, monkeypatch):
    """Quarto makes a figure of each output; a stash of its own split a fig- cell."""
    ipython_display = pytest.importorskip("IPython.display")
    displayed: list = []
    quarto("html")
    monkeypatch.setattr(ipython_display, "display", displayed.append)
    monkeypatch.setattr(
        "htmltools._core.Tag.show", lambda self, *a, **k: displayed.append(str(self))
    )
    fig = _bar()
    try:
        FigureManager.get_maidr(fig).show(renderer="ipython", clear_fig=False)
    finally:
        plt.close(fig)

    assert len(displayed) == 1
    assert _copies(displayed[0]) == 1


def test_a_render_puts_no_second_maidr_js_in_the_page(quarto, monkeypatch):
    """require.js would take it for a module, and an inline chart loads its own."""
    ipython_display = pytest.importorskip("IPython.display")
    displayed: list = []
    quarto("html")
    monkeypatch.setattr(ipython_display, "HTML", lambda html: html)
    monkeypatch.setattr(ipython_display, "display", displayed.append)
    maidr_api.init_notebook(use_cdn="auto", force=True)

    # The stash escapes every ``</`` inside it, so its own end is the only one.
    assert len(displayed) == 1
    assert displayed[0].count("</script>") == 1


def test_the_loader_in_each_mode():
    url = "https://cdn.jsdelivr.net/npm/maidr@1.2.3/dist/maidr.js"
    offline = inline_chart.loader_js(False, None, "")
    online = inline_chart.loader_js(True, url, "window.maidrLocaleBaseUrl = 'x';")
    auto = inline_chart.loader_js("auto", url, "window.maidrLocaleBaseUrl = 'x';")

    assert "fromStash('the page" in offline and "fromUrl(" not in offline
    for loader in (online, auto):
        assert f'fromUrl("{url}"' in loader
        assert "window.maidrLocaleBaseUrl = 'x';" in loader
    assert "window.maidrLocaleBaseUrl" not in offline


def test_a_chart_on_the_cdn_alone_falls_back_to_a_copy_another_chart_put_there():
    """A ``use_cdn=False`` chart after it must not be left without its runtime."""
    loader = inline_chart.loader_js(True, "https://x/maidr.js", "")
    on_error = loader[loader.index("fromUrl(") :]

    assert "fromStash(" in on_error


def test_every_loader_lets_a_copy_of_an_output_claim_ids_of_its_own():
    for mode in (False, True, "auto"):
        loader = inline_chart.loader_js(mode, "https://x/maidr.js", "")
        claim = loader.index("__maidrInlineClaim(document.currentScript)")
        assert claim < loader.index("if (window.maidrLive")


def test_a_url_cannot_close_the_loaders_script():
    loader = inline_chart.loader_js(True, "https://x/</script><script>alert(1)", "")
    assert "</script>" not in loader


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("mode", [False, True, "auto"])
def test_the_scripts_a_chart_carries_parse(tmp_path, mode):
    """The assets are shipped with their comments taken out; that must not break them."""
    scripts = {
        "inline.js": inline_chart._asset("inline.js"),
        "loader.js": inline_chart.loader_js(mode, "https://x/maidr.js", "var a = 1;"),
    }
    for name, source in scripts.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr


def test_the_stylesheet_survives_its_comments_being_taken_out():
    css = inline_chart._asset("inline.css")
    assert "/*" not in css and "*/" not in css
    assert css.count("{") == css.count("}")
    assert '.maidr-inline figure[id^="maidr-figure"] > div[tabindex="0"]:focus' in css


def test_the_assets_ship_in_the_package():
    """``maidr/assets`` is outside ``maidr/static``, which save_html copies whole."""
    from importlib import resources

    for name in ("inline.js", "inline.css"):
        assert resources.files("maidr").joinpath("assets", name).is_file()
