"""BokehMaidr's page: dispatch, embedding, loading and the highlight map."""

from __future__ import annotations

import json
import re
from unittest import mock

import pytest

bokeh = pytest.importorskip("bokeh")

from bokeh.layouts import gridplot  # noqa: E402
from bokeh.models import ColumnDataSource  # noqa: E402
from bokeh.plotting import figure  # noqa: E402
from bokeh.transform import dodge, linear_cmap  # noqa: E402

import maidr  # noqa: E402
from maidr.api import _is_bokeh_model  # noqa: E402
from maidr.bokeh import BokehMaidr, is_bokeh_model  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402


@pytest.fixture
def bar():
    p = figure(x_range=["a", "b", "c"], title="Sales")
    p.vbar(x=["c", "a", "b"], top=[3, 1, 2], width=0.9)
    return p


@pytest.fixture
def lines():
    p = figure(title="Trend")
    p.line([1, 2, 3], [1, 2, 3], legend_label="up")
    p.line([1, 2, 3], [8, 7, 6], legend_label="down")
    return p


def _html(model, **kwargs) -> str:
    kwargs.setdefault("use_cdn", False)
    return str(BokehMaidr(model)._create_html_tag(use_iframe=False, **kwargs))


def _script_value(html: str, name: str):
    """The JSON literal the page script assigns to ``var <name>``."""
    match = re.search(rf"var {name} = (.*?);\n", html)
    assert match, name
    return json.loads(match.group(1))


class TestDetection:
    def test_a_figure_and_a_layout_are_bokeh_models(self, bar):
        assert is_bokeh_model(bar)
        assert _is_bokeh_model(gridplot([[bar]]))

    def test_other_objects_are_not(self):
        assert not is_bokeh_model(object())
        assert not is_bokeh_model(ColumnDataSource())


class TestDispatch:
    def test_render_returns_the_page(self, bar):
        html = str(maidr.render(bar, use_cdn=False))

        assert "Bokeh.embed.embed_item" in html
        layer = _script_value(html, "schema")["subplots"][0][0]["layers"][0]
        assert layer["type"] == "bar"

    def test_save_html_writes_the_page(self, bar, tmp_path):
        out = tmp_path / "bokeh.html"

        result = maidr.save_html(bar, str(out), use_cdn=False)

        assert result == str(out)
        text = out.read_text(encoding="utf-8")
        assert "Bokeh.embed.embed_item" in text
        assert (tmp_path / "lib").is_dir()

    def test_show_in_a_browser_saves_and_opens(self, bar):
        with mock.patch("webbrowser.open") as opened:
            maidr.show(bar, renderer="browser", use_cdn=False)

        opened.assert_called_once()
        assert opened.call_args[0][0].endswith("maidr_bokeh_plot.html")

    def test_close_is_a_no_op(self, bar):
        maidr.close(bar)


class TestPage:
    def test_bokehjs_comes_from_the_installed_version(self, bar):
        html = _html(bar)

        release = "https://cdn.bokeh.org/bokeh/release"
        assert f"{release}/bokeh-{bokeh.__version__}.min.js" in html

    def test_the_plot_is_serialized_by_json_item(self, bar):
        item = _script_value(_html(bar), "item")

        assert item["root_id"] == bar.id
        assert "doc" in item

    def test_the_schema_lands_after_embed_item_resolves(self, bar):
        html = _html(bar)

        # The payload is attached inside `bind`, which is the `then` of the
        # promise `embed_item` returns -- never before BokehJS has drawn.
        assert ".embed_item(item, targetId).then(bind" in html
        assert "wrapper.setAttribute('maidr-data'" in html

    def test_a_late_runtime_is_told_through_bindchart(self, bar):
        html = _html(bar)

        assert "maidr:bindchart" in html

    def test_use_cdn_false_ships_the_bundle_as_a_dependency(self, bar, tmp_path):
        out = tmp_path / "offline.html"
        maidr.save_html(bar, str(out), use_cdn=False)
        text = out.read_text(encoding="utf-8")

        assert re.search(r'<script src="lib/maidr-[^"]+/maidr\.js"', text)
        assert "cdn.jsdelivr.net/npm/maidr@" not in text

    def test_use_cdn_true_loads_maidr_from_jsdelivr(self, bar):
        html = _html(bar, use_cdn=True)

        assert "cdn.jsdelivr.net/npm/maidr@latest/dist/maidr.js" in html

    def test_use_cdn_auto_falls_back_to_the_bundle(self, bar):
        html = _html(bar, use_cdn="auto")

        assert "cdn.jsdelivr.net/npm/maidr@latest/dist/maidr.js" in html
        assert re.search(r"fb\.src = 'lib/maidr-[^']+/maidr\.js'", html)

    def test_a_title_cannot_close_the_script(self):
        p = figure(x_range=["a"], title="</script><b>")
        p.vbar(x=["a"], top=[1], width=0.5)

        html = _html(p)

        assert "</script><b>" not in html

    def test_a_title_cannot_open_a_comment_that_swallows_the_end_tag(self):
        # ``<!--<script>`` puts the tokenizer in a state where the real
        # ``</script>`` no longer ends the element.
        p = figure(x_range=["a"], title="<!--<script>")
        p.vbar(x=["a"], top=[1], width=0.5)

        html = _html(p)

        assert "<!--" not in html
        assert _script_value(html, "schema")["subplots"][0][0]["layers"][0][
            "title"
        ] == "<!--<script>"

    @pytest.mark.parametrize("title", ["Sales __LOADER__", "Wait __WAIT_MS__"])
    def test_a_title_naming_a_placeholder_is_left_as_written(self, title):
        p = figure(x_range=["a"], title=title)
        p.vbar(x=["a"], top=[1], width=0.5)

        html = _html(p, use_cdn=True)

        layer = _script_value(html, "schema")["subplots"][0][0]["layers"][0]
        assert layer["title"] == title
        assert title in json.dumps(_script_value(html, "item"))

    def test_a_notebook_render_is_an_iframe_reading_the_parent_stash(self, bar):
        with mock.patch.object(Environment, "is_notebook", return_value=True):
            tag = BokehMaidr(bar)._create_html_tag(use_iframe=True, use_cdn=False)
        html = str(tag)

        assert html.startswith("<iframe")
        assert 'title="Sales, accessible chart"' in html
        assert "__maidrJsSource" in html

    def test_a_shiny_render_carries_the_bundle_inline(self, bar):
        with mock.patch.object(Environment, "is_shiny", return_value=True):
            html = str(maidr.render(bar, use_cdn=False))

        assert html.startswith("<iframe")
        assert "maidrLive" in html  # the bundle itself, inlined


class TestHighlightMap:
    def _highlight(self, model) -> tuple[dict, dict]:
        html = _html(model)
        return _script_value(html, "schema"), _script_value(html, "highlight")

    def test_a_bar_selects_its_source_row_in_drawn_order(self, bar):
        schema, highlight = self._highlight(bar)
        layer = schema["subplots"][0][0]["layers"][0]
        renderer = bar.renderers[0].id

        # Drawn a, b, c; the source holds c, a, b.
        assert highlight[layer["id"]] == {
            "kind": "select",
            "grid": [[[renderer, 1], [renderer, 2], [renderer, 0]]],
        }

    def test_a_scatter_maps_each_point_index(self):
        p = figure()
        p.scatter([1, 2, 3], [4, 5, 6])
        schema, highlight = self._highlight(p)
        layer = schema["subplots"][0][0]["layers"][0]

        assert highlight[layer["id"]] == {
            "kind": "points",
            "points": [[p.renderers[0].id, i] for i in range(3)],
        }

    def test_a_line_moves_a_cursor_to_each_point(self, lines):
        html = _html(lines)
        schema = _script_value(html, "schema")
        highlight = _script_value(html, "highlight")
        item = _script_value(html, "item")
        entry = highlight[schema["subplots"][0][0]["layers"][0]["id"]]

        assert entry["kind"] == "cursor"
        assert entry["grid"] == [
            [[1, 1], [2, 2], [3, 3]],
            [[1, 8], [2, 7], [3, 6]],
        ]
        # The cursor was serialized with the plot, so the page can find it.
        assert f'"id": "{entry["cursor"]}"' in json.dumps(item)

    def test_a_date_cursor_is_in_epoch_milliseconds(self):
        import pandas as pd

        p = figure(x_axis_type="datetime")
        p.line(pd.date_range("2024-01-01", periods=2), [1, 2])
        schema, highlight = self._highlight(p)
        entry = highlight[schema["subplots"][0][0]["layers"][0]["id"]]

        assert entry["grid"] == [[[1704067200000.0, 1], [1704153600000.0, 2]]]

    def test_a_heatmap_is_keyed_bottom_row_first(self):
        import pandas as pd

        frame = pd.DataFrame(
            {"x": ["a", "b", "a", "b"], "y": ["u", "u", "v", "v"], "v": [1, 2, 3, 4]}
        )
        p = figure(x_range=["a", "b"], y_range=["u", "v"])
        p.rect(
            x="x", y="y", width=1, height=1, source=frame,
            fill_color=linear_cmap("v", "Viridis256", 1, 4),
        )
        schema, highlight = self._highlight(p)
        entry = highlight[schema["subplots"][0][0]["layers"][0]["id"]]
        rid = p.renderers[0].id

        # The core reverses the emitted rows, so its row 0 is ``u``, the
        # bottom factor -- source rows 0 and 1.
        assert entry["grid"] == [[[rid, 0], [rid, 1]], [[rid, 2], [rid, 3]]]

    def test_a_stack_names_each_segment_renderer(self):
        p = figure(x_range=["A", "B"])
        rs = p.vbar_stack(
            ["s1", "s2"], x="c", width=0.9,
            source={"c": ["A", "B"], "s1": [1, 2], "s2": [3, 4]},
        )
        schema, highlight = self._highlight(p)
        entry = highlight[schema["subplots"][0][0]["layers"][0]["id"]]

        assert entry["grid"] == [
            [[rs[0].id, 0], [rs[0].id, 1]],
            [[rs[1].id, 0], [rs[1].id, 1]],
        ]


    def test_markers_on_a_line_from_one_source_get_a_cursor(self):
        # Selecting the row would draw the line with its nonselection glyph,
        # which fades it away; the markers are pointed at instead.
        source = ColumnDataSource({"x": [1, 2, 3], "y": [4, 6, 5]})
        p = figure()
        p.line("x", "y", source=source)
        p.scatter("x", "y", source=source)
        schema, highlight = self._highlight(p)
        by_type = {
            layer["type"]: highlight[layer["id"]]
            for layer in schema["subplots"][0][0]["layers"]
        }

        assert by_type["point"]["kind"] == "cursor"
        assert by_type["point"]["points"] == [[1, 4], [2, 6], [3, 5]]
        # One cursor serves the plot, whichever layer is being read.
        assert by_type["point"]["cursor"] == by_type["line"]["cursor"]

    def test_bars_sharing_a_source_with_another_mark_point_at_the_bar_end(self):
        source = ColumnDataSource({"c": ["A", "B"], "v": [3, 5], "w": [1, 2]})
        p = figure(y_range=["A", "B"])
        for column, offset in (("v", 0.2), ("w", -0.2)):
            p.hbar(
                y=dodge("c", offset, range=p.y_range), right=column, height=0.3,
                source=source,
            )
        p.text(x="v", y="c", text="c", source=source)
        with pytest.warns(UserWarning, match="Text"):
            schema, highlight = self._highlight(p)
        entry = highlight[schema["subplots"][0][0]["layers"][0]["id"]]

        # Left-hand group first, each cursor at the bar's end, the category
        # carrying the offset it is drawn at.
        assert entry["kind"] == "cursor"
        assert entry["grid"] == [
            [[1, ["A", -0.2]], [2, ["B", -0.2]]],
            [[3, ["A", 0.2]], [5, ["B", 0.2]]],
        ]

    def test_bins_and_cells_get_a_cursor_at_their_centre(self):
        source = ColumnDataSource(
            {"left": [0, 1], "right": [1, 2], "top": [4, 2], "n": [4, 2]}
        )
        p = figure()
        p.quad(left="left", right="right", top="top", bottom=0, source=source)
        p.line(x="left", y="top", source=source)
        schema, highlight = self._highlight(p)
        entry = next(
            highlight[layer["id"]]
            for layer in schema["subplots"][0][0]["layers"]
            if layer["type"] == "hist"
        )

        assert entry == {
            "kind": "cursor",
            "grid": [[[0.5, 2.0], [1.5, 1.0]]],
            "cursor": entry["cursor"],
        }

    def test_a_hidden_mark_on_the_source_does_not_count(self):
        source = ColumnDataSource({"x": [1, 2], "y": [4, 6]})
        p = figure()
        p.scatter("x", "y", source=source)
        p.line("x", "y", source=source, visible=False)
        schema, highlight = self._highlight(p)
        layer = schema["subplots"][0][0]["layers"][0]

        assert highlight[layer["id"]]["kind"] == "points"


class TestSubplotPanels:
    """What lets MAIDR measure which way a layout's rows run on the page."""

    def _plot(self, title):
        p = figure(title=title)
        p.line([1, 2], [1, 2])
        return p

    def test_each_subplot_names_a_panel_and_a_gap_has_no_plot(self):
        from bokeh.layouts import column, row

        top, right, under = self._plot("a"), self._plot("b"), self._plot("c")
        html = _html(row(top, column(right, under)))
        schema = _script_value(html, "schema")
        panels = _script_value(html, "panels")

        cells = [cell for row_ in schema["subplots"] for cell in row_]
        assert [cell["selector"] for cell in cells] == [
            f'div[id="{panel_id}"]' for panel_id, _ in panels
        ]
        assert [plot_id for _, plot_id in panels] == [top.id, right.id, None, under.id]

    def test_a_single_plot_has_none(self, bar):
        html = _html(bar)

        assert "selector" not in _script_value(html, "schema")["subplots"][0][0]
        assert _script_value(html, "panels") == []


class TestFigureIsNotMutated:
    def test_rendering_leaves_the_renderers_as_they_were(self, lines):
        before = list(lines.renderers)
        ids = [r.id for r in before]

        _html(lines)
        maidr.render(lines, use_cdn=False)

        assert list(lines.renderers) == before
        assert [r.id for r in lines.renderers] == ids
        assert lines.document is None

    def test_a_free_figure_can_still_join_a_document(self, lines):
        from bokeh.document import Document

        _html(lines)

        # ``json_item`` alone leaves it owned by a throwaway document, and
        # this would raise "Models must be owned by only a single document".
        Document().add_root(lines)

    def test_the_cursor_is_removed_even_when_serializing_fails(self, lines):
        before = list(lines.renderers)

        with mock.patch("bokeh.embed.json_item", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                _html(lines)

        assert list(lines.renderers) == before

    def test_a_figure_in_a_document_stays_in_it_unchanged(self, lines):
        from bokeh.document import Document

        doc = Document()
        doc.add_root(lines)
        models_before = {m.id for m in doc.models}

        _html(lines)

        assert lines.document is doc
        assert {m.id for m in doc.models} == models_before
