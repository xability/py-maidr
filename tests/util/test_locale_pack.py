"""Where the bundled ``maidr.js`` finds its locale packs (#819).

``maidr.js`` 4.8.0 and later fetches every language but English as a pack
from beside its own URL, or from ``window.maidrLocaleBaseUrl``. The bundled
copy ships without the packs, so a document or frame that runs it has to
name where they are -- in that same window, ahead of it -- or a Korean
reader gets English. A document that loads ``maidr.js`` from the CDN must
declare nothing: the global wins over the script's own URL, and would hand
a newer CDN copy the bundled version's packs.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from contextlib import ExitStack
from unittest import mock

import matplotlib.pyplot as plt
import pytest

import maidr
from maidr.util import locale_pack
from maidr.util.dependencies import maidr_js_version
from maidr.util.environment import Environment

DECLARATION = re.compile(
    r"window\.maidrLocaleBaseUrl = window\.maidrLocaleBaseUrl \|\| "
    r'("(?:[^"\\]|\\.)*");'
)


@pytest.fixture(autouse=True)
def _unset(monkeypatch):
    monkeypatch.delenv(locale_pack.LOCALE_BASE_URL_ENV_VAR, raising=False)
    maidr.set_locale_base_url(None)
    yield
    maidr.set_locale_base_url(None)


def _bundled_dir() -> str:
    return f"https://cdn.jsdelivr.net/npm/maidr@{maidr_js_version()}/dist/"


def _declared(page: str) -> list[str]:
    """Every directory the page declares, decoded from its JS literal."""
    return [json.loads(m.group(1)) for m in DECLARATION.finditer(page)]


# ---------------------------------------------------------------------------
# The setting
# ---------------------------------------------------------------------------


def test_the_default_is_the_bundled_versions_packs_on_jsdelivr():
    assert maidr.get_locale_base_url() == _bundled_dir()
    assert locale_pack.locale_base_url(bundled=True) == _bundled_dir()
    # The CDN copy finds its packs beside itself.
    assert locale_pack.locale_base_url(bundled=False) is None


def test_the_environment_names_a_directory_for_every_document(monkeypatch):
    monkeypatch.setenv("MAIDR_LOCALE_BASE_URL", "https://intranet.example/maidr/")
    for bundled in (True, False):
        assert (
            locale_pack.locale_base_url(bundled=bundled)
            == "https://intranet.example/maidr/"
        )


@pytest.mark.parametrize("off", ["", "  ", "false", "0", "off"])
def test_an_empty_or_false_environment_value_declares_nothing(monkeypatch, off):
    monkeypatch.setenv("MAIDR_LOCALE_BASE_URL", off)
    assert maidr.get_locale_base_url() is None
    assert locale_pack.locale_fallback_js() == ""


@pytest.mark.parametrize("off", ["", False])
def test_the_setter_turns_it_off_and_wins_over_the_environment(monkeypatch, off):
    monkeypatch.setenv("MAIDR_LOCALE_BASE_URL", "https://intranet.example/")
    maidr.set_locale_base_url(off)
    assert maidr.get_locale_base_url() is None
    maidr.set_locale_base_url(None)
    assert maidr.get_locale_base_url() == "https://intranet.example/"


def test_the_setter_refuses_anything_else():
    with pytest.raises(TypeError):
        maidr.set_locale_base_url(True)  # type: ignore[arg-type]


def test_a_url_cannot_break_out_of_the_script_element():
    hostile = 'https://x.example/"</script><script>alert(1)</script><!--'
    script = locale_pack.locale_config_js(hostile)
    assert "<" not in script
    assert _declared(script) == [hostile]


def test_the_helpers_are_part_of_the_package_api():
    for name in (
        "set_locale_base_url",
        "get_locale_base_url",
        "LOCALE_BASE_URL_ENV_VAR",
    ):
        assert name in maidr.__all__


# ---------------------------------------------------------------------------
# Every path that runs the bundled copy declares it; no other path does
# ---------------------------------------------------------------------------


def _chart(library: str):
    if library == "matplotlib":
        fig, ax = plt.subplots()
        ax.bar(["a", "b"], [1, 2])
        return fig
    if library == "plotly":
        go = pytest.importorskip("plotly.graph_objects")
        return go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
    bokeh_plotting = pytest.importorskip("bokeh.plotting")
    p = bokeh_plotting.figure(x_range=["a", "b"])
    p.vbar(x=["a", "b"], top=[1, 2], width=0.9)
    return p


def _page(library: str, use_cdn, host: str, tmp_path) -> str:
    """The markup a reader's browser gets, entity-decoded out of ``srcdoc``."""
    chart = _chart(library)
    if host == "document":
        out = tmp_path / "chart.html"
        maidr.save_html(chart, str(out), use_cdn=use_cdn)
        return out.read_text(encoding="utf-8")
    with ExitStack() as stack:
        stack.enter_context(
            mock.patch.object(Environment, f"is_{host}", return_value=True)
        )
        page = str(maidr.render(chart, use_cdn=use_cdn))
    assert page.startswith("<iframe"), page[:80]
    return html_lib.unescape(page)


LIBRARIES = ["matplotlib", "plotly", "bokeh"]
HOSTS = ["document", "notebook", "shiny"]


def _bundle_position(page: str, host: str) -> int:
    """Where the bundled copy is put into the page, by host."""
    if host == "notebook":
        return page.index("s.text = jsSrc")
    if host == "shiny":
        return page.index("maidrLive")  # the bundle itself, inlined
    return page.index(f"maidr-{maidr_js_version()}/maidr.js")


@pytest.mark.parametrize("library", LIBRARIES)
@pytest.mark.parametrize("host", HOSTS)
def test_the_bundled_copy_is_told_where_its_packs_are_ahead_of_it(
    library, host, tmp_path
):
    page = _page(library, False, host, tmp_path)
    assert _declared(page) == [_bundled_dir()]
    assert DECLARATION.search(page).start() < _bundle_position(page, host)


@pytest.mark.parametrize("library", LIBRARIES)
@pytest.mark.parametrize("host", HOSTS)
def test_the_off_switch_declares_nothing(library, host, tmp_path, monkeypatch):
    monkeypatch.setenv("MAIDR_LOCALE_BASE_URL", "")
    for use_cdn in (False, "auto", True):
        assert not _declared(_page(library, use_cdn, host, tmp_path))


@pytest.mark.parametrize("library", LIBRARIES)
@pytest.mark.parametrize("host", HOSTS)
def test_a_cdn_document_declares_nothing(library, host, tmp_path):
    assert not _declared(_page(library, True, host, tmp_path))


@pytest.mark.parametrize("library", LIBRARIES)
@pytest.mark.parametrize("host", ["document", "notebook"])
def test_auto_declares_only_in_its_fallback(library, host, tmp_path):
    page = _page(library, "auto", host, tmp_path)
    assert _declared(page) == [_bundled_dir()]
    # After the CDN script's ``onerror`` begins, and before the bundled
    # copy is put in the page: never while the CDN copy may still load.
    declared = DECLARATION.search(page).start()
    fallback = page.rfind("onerror", 0, declared)
    if fallback == -1:
        fallback = page.rindex("function fallbackFromParent", 0, declared)
    assert fallback != -1
    if host == "notebook":
        assert declared < page.index("s.text = jsSrc", declared)
    else:
        assert declared < page.index("fb.src", declared)


@pytest.mark.parametrize("library", LIBRARIES)
def test_a_configured_directory_is_declared_in_every_document(library, tmp_path):
    maidr.set_locale_base_url("https://intranet.example/maidr/")
    for use_cdn in (False, True):
        page = _page(library, use_cdn, "document", tmp_path)
        assert _declared(page) == ["https://intranet.example/maidr/"]
