"""``hover_mode`` sets the chart's starting Hover Mode as ``hoverMode``.

maidr.js reads a top-level ``hoverMode`` -- ``"pointermove"``, ``"click"`` or
``"off"`` -- as the starting value of the reader's Hover Mode setting
(xability/maidr#1382). :func:`maidr.show`, :func:`maidr.render` and
:func:`maidr.save_html` take it for every backend that builds its schema in
Python; ``None`` leaves the field out, so maidr.js keeps its own default.

The schema is read back from the page each backend writes, rather than from
``_flatten_maidr``, so these fail if the value is accepted but never reaches
the reader. ``use_cdn=True`` keeps ``maidr.js`` itself, which names the
setting too, out of the page.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402
from maidr.core import maidr as core_module  # noqa: E402
from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402
from maidr.util.hover_mode import HOVER_MODES, with_hover_mode  # noqa: E402

_KEY = MaidrKey.HOVER_MODE.value


def _schema_after(page: str, marker: str) -> dict:
    """The JSON object the page assigns after ``marker``."""
    start = page.index(marker) + len(marker)
    schema, _ = json.JSONDecoder().raw_decode(page[start:])
    return schema


def _hover_modes(page: str) -> list[str]:
    """Every ``hoverMode`` value the page carries, escaped or not."""
    return re.findall(rf'"{_KEY}":\s*"([^"]*)"', html.unescape(page))


@pytest.fixture
def bar_ax():
    _, ax = plt.subplots()
    ax.bar(["a", "b", "c"], [1, 2, 3])
    return ax


def test_the_key_is_the_one_maidr_js_reads():
    assert _KEY == "hoverMode"
    assert HOVER_MODES == ("pointermove", "click", "off")


class TestHelper:
    def test_none_leaves_the_schema_as_it_was(self):
        assert with_hover_mode({"id": "x"}, None) == {"id": "x"}

    @pytest.mark.parametrize("mode", HOVER_MODES)
    def test_a_mode_is_set_at_the_top_level(self, mode):
        assert with_hover_mode({"id": "x"}, mode) == {"id": "x", _KEY: mode}

    @pytest.mark.parametrize("bad", ["hover", "", "OFF", True, 0])
    def test_anything_else_is_refused(self, bad):
        with pytest.raises(ValueError, match="'pointermove', 'click', 'off'"):
            with_hover_mode({}, bad)


class TestMatplotlib:
    def test_absent_by_default(self, bar_ax, tmp_path):
        assert _hover_modes(str(maidr.render(bar_ax, use_cdn=True))) == []
        out = maidr.save_html(bar_ax, str(tmp_path / "c.html"), use_cdn=True)
        assert _KEY not in Path(out).read_text(encoding="utf-8")

    @pytest.mark.parametrize("mode", HOVER_MODES)
    def test_render_carries_it(self, bar_ax, mode):
        page = str(maidr.render(bar_ax, use_cdn=True, hover_mode=mode))
        assert _hover_modes(page) == [mode]

    @pytest.mark.parametrize("mode", HOVER_MODES)
    def test_save_html_carries_it_at_the_top_level(self, bar_ax, tmp_path, mode):
        out = maidr.save_html(
            bar_ax,
            str(tmp_path / "c.html"),
            data_in_svg=False,
            use_cdn=True,
            hover_mode=mode,
        )
        schema = _schema_after(Path(out).read_text(encoding="utf-8"), "var maidr = ")
        assert schema[_KEY] == mode
        assert "subplots" in schema

    def test_show_in_a_browser_carries_it(self, bar_ax, tmp_path, monkeypatch):
        opened: list[str] = []
        monkeypatch.setattr(core_module.webbrowser, "open", opened.append)
        monkeypatch.setattr(core_module.tempfile, "gettempdir", lambda: str(tmp_path))
        monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: False))

        maidr.show(bar_ax, renderer="browser", use_cdn=True, hover_mode="off")

        assert len(opened) == 1
        page = Path(opened[0].removeprefix("file://")).read_text(encoding="utf-8")
        assert _hover_modes(page) == ["off"]


class TestPlotly:
    @pytest.fixture
    def fig(self):
        go = pytest.importorskip("plotly.graph_objects")
        return go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))

    def test_absent_by_default(self, fig):
        schema = _schema_after(
            str(maidr.render(fig, use_cdn=True)), "var maidrSchema = "
        )
        assert _KEY not in schema

    @pytest.mark.parametrize("mode", HOVER_MODES)
    def test_render_carries_it(self, fig, mode):
        page = str(maidr.render(fig, use_cdn=True, hover_mode=mode))
        assert _schema_after(page, "var maidrSchema = ")[_KEY] == mode

    @pytest.mark.parametrize("mode", HOVER_MODES)
    def test_save_html_carries_it(self, fig, tmp_path, mode):
        out = maidr.save_html(
            fig, str(tmp_path / "c.html"), use_cdn=True, hover_mode=mode
        )
        page = Path(out).read_text(encoding="utf-8")
        assert _schema_after(page, "var maidrSchema = ")[_KEY] == mode


class TestBokeh:
    @pytest.fixture
    def fig(self):
        plotting = pytest.importorskip("bokeh.plotting")
        p = plotting.figure(x_range=["a", "b"], title="Counts")
        p.vbar(x=["a", "b"], top=[1, 2], width=0.8)
        return p

    def test_absent_by_default(self, fig):
        schema = _schema_after(str(maidr.render(fig, use_cdn=True)), "var schema = ")
        assert _KEY not in schema

    @pytest.mark.parametrize("mode", HOVER_MODES)
    def test_render_carries_it(self, fig, mode):
        page = str(maidr.render(fig, use_cdn=True, hover_mode=mode))
        assert _schema_after(page, "var schema = ")[_KEY] == mode

    @pytest.mark.parametrize("mode", HOVER_MODES)
    def test_save_html_carries_it(self, fig, tmp_path, mode):
        out = maidr.save_html(
            fig, str(tmp_path / "c.html"), use_cdn=True, hover_mode=mode
        )
        page = Path(out).read_text(encoding="utf-8")
        assert _schema_after(page, "var schema = ")[_KEY] == mode


class TestPlotnine:
    @pytest.fixture
    def plot(self):
        p9 = pytest.importorskip("plotnine")
        import pandas as pd

        data = pd.DataFrame({"x": ["a", "b"], "y": [1, 2]})
        return p9.ggplot(data, p9.aes("x", "y")) + p9.geom_col()

    def test_absent_by_default(self, plot):
        assert _hover_modes(str(maidr.render(plot, use_cdn=True))) == []

    def test_render_carries_it(self, plot):
        page = str(maidr.render(plot, use_cdn=True, hover_mode="click"))
        assert _hover_modes(page) == ["click"]


class TestAltair:
    @pytest.fixture
    def chart(self):
        alt = pytest.importorskip("altair")
        import pandas as pd

        data = pd.DataFrame({"x": ["a", "b"], "y": [1, 2]})
        return alt.Chart(data).mark_bar().encode(x="x", y="y")

    def test_a_mode_warns_that_it_is_not_honored(self, chart):
        with pytest.warns(UserWarning, match="hover_mode='off' cannot be honored"):
            maidr.render(chart, use_cdn=True, hover_mode="off")

    def test_none_does_not_warn(self, chart, recwarn):
        maidr.render(chart, use_cdn=True)
        assert not [w for w in recwarn if "hover_mode" in str(w.message)]


class TestInvalid:
    def test_render_refuses_it(self, bar_ax):
        with pytest.raises(ValueError, match="hover_mode must be one of"):
            maidr.render(bar_ax, hover_mode="hover")

    def test_show_refuses_it(self, bar_ax):
        with pytest.raises(ValueError, match="hover_mode must be one of"):
            maidr.show(bar_ax, hover_mode="none")

    def test_save_html_refuses_it_before_writing(self, bar_ax, tmp_path):
        target = tmp_path / "c.html"
        with pytest.raises(ValueError, match="hover_mode must be one of"):
            maidr.save_html(bar_ax, str(target), hover_mode="hover")
        assert not target.exists()

    def test_the_message_names_the_values(self, bar_ax):
        with pytest.raises(ValueError) as caught:
            maidr.render(bar_ax, hover_mode="hover")
        for mode in HOVER_MODES:
            assert repr(mode) in str(caught.value)

    def test_it_is_keyword_only(self, bar_ax):
        with pytest.raises(TypeError):
            maidr.render(bar_ax, True, "off")  # type: ignore[misc]


class TestWidgets:
    def test_streamlit_html_carries_it(self, bar_ax):
        from maidr.widget.streamlit import maidr_html

        assert _hover_modes(maidr_html(bar_ax, use_cdn=True)) == []
        page = maidr_html(bar_ax, use_cdn=True, hover_mode="click")
        assert _hover_modes(page) == ["click"]

    def test_gradio_markup_carries_it(self, bar_ax):
        from maidr.widget.gradio import render_maidr

        page = render_maidr(bar_ax, use_cdn=True, hover_mode="off")
        # The chart is the frame's ``srcdoc``, escaped once more.
        assert _hover_modes(html.unescape(page)) == ["off"]

    def test_shiny_refuses_a_bad_mode_where_it_is_written(self):
        pytest.importorskip("shiny")
        from maidr.widget.shiny import render_maidr

        with pytest.raises(ValueError, match="hover_mode must be one of"):
            render_maidr(hover_mode="hover")
