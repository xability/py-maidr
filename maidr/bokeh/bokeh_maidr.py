"""Render Bokeh plots with MAIDR accessibility.

Architecture
------------
Like the Plotly path, and unlike the Altair one, the MAIDR schema is built
here in Python, from the Bokeh *document model* -- the renderers, glyphs and
data sources the author created (see :mod:`maidr.bokeh.layers`) -- rather
than from anything BokehJS draws. The page then:

1. loads BokehJS from Bokeh's CDN, at the version installed here;
2. embeds the plot with ``Bokeh.embed.embed_item`` and waits for the
   promise it returns, BokehJS's own word that the views are built;
3. puts the schema on a wrapper element around the plot as ``maidr-data``
   and binds ``maidr.js`` to it (loading the bundle the same way the
   Plotly path does, per ``use_cdn``); and
4. hands ``maidr.js`` an ``onNavigate`` callback that highlights the mark
   being announced.

Highlight
---------
BokehJS draws into a ``<canvas>`` inside a shadow root, so the CSS selectors
MAIDR highlights an SVG chart with cannot reach a Bokeh mark. MAIDR's answer
for canvas charts is ``onNavigate``, a callback it calls with the position
it has just announced -- but a function cannot travel in ``maidr-data``,
which is JSON. It is registered instead through
``window.maidrLive.setData({...schema, onNavigate})`` once the chart has
mounted: ``maidr.js`` stores that object as the chart's data and builds its
controller from it on the next focus-in, which is when the callback is
wired (``useMaidrController.ts``, ``Controller.registerNavigateCallback``).

The callback then selects the data-source row of a bar, bin, cell or point
(Bokeh's default ``nonselection_glyph`` dims the rest), and moves a small
cursor glyph onto a line, step or area, which have one path and no row to
select. That cursor is added to the plot only while the document is being
serialized and removed again in a ``finally``, so the caller's figure is
left exactly as it was.

Limitations
-----------
* BokehJS always comes from ``cdn.bokeh.org``, whatever ``use_cdn`` says,
  exactly as plotly.js always comes from ``cdn.plot.ly`` on the Plotly
  path; ``use_cdn`` governs ``maidr.js`` alone.
* Selection is per data source, so renderers sharing one -- the segments of
  a ``vbar_stack``, the groups of a ``dodge()`` chart -- are highlighted
  together at the current category.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
import webbrowser
from contextlib import contextmanager
from typing import Any, Iterator, Literal, cast

from htmltools import HTML, HTMLDocument, Tag, tags

from maidr.bokeh.layers import BokehLayer, PlotReader
from maidr.bokeh.layout import place_plots
from maidr.bokeh.utils import warn
from maidr.util.bundle_capability import (
    schema_trace_types,
    warn_if_bundle_cannot_render,
)
from maidr.util.bundle_loader import (
    iframe_mode,
    maidr_bundle_children,
    maidr_loader_js,
)
from maidr.util.dotpad import dotpad_config_child, local_dotpad_sdk_dependency
from maidr.util.environment import Environment
from maidr.util.iframe_utils import (
    chart_title_of,
    with_chart_title,
    wrap_in_iframe_plotly,
)

#: The cursor a line, step or area is highlighted with: a ring in MAIDR's
#: own default highlight colour, drawn over everything else on the plot.
_CURSOR_COLOR = "#03c809"
_CURSOR_SIZE = 16
_CURSOR_LINE_WIDTH = 3

#: How long the page waits for BokehJS, and then for ``maidr.js`` to mount
#: the chart, before giving up on the step it is waiting for.
_WAIT_MS = 30000


def _script_json(value: Any) -> str:
    """
    Serialize ``value`` for a JS literal inside an HTML ``<script>``.

    ``</`` is escaped so a title reading ``</script>`` cannot end the
    element, and U+2028/U+2029 because JSON allows them where a JS string
    literal did not until ES2019.
    """
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


class BokehMaidr:
    """
    Render a Bokeh plot or layout with MAIDR accessibility.

    Parameters
    ----------
    model : bokeh.models.LayoutDOM
        A ``figure``, a ``gridplot``, a ``row``/``column`` or ``GridBox`` of
        figures, or a ``Tabs`` (whose active panel is read).
    """

    def __init__(self, model: Any) -> None:
        self._model = model
        self.maidr_id = str(uuid.uuid4())
        self._cells: list[tuple[int, int, list[BokehLayer]]] = [
            (placed.row, placed.col, PlotReader(placed.plot).layers())
            for placed in place_plots(model)
        ]
        if not any(layers for _, _, layers in self._cells):
            warn(
                "maidr found nothing it can read in this Bokeh figure; it is "
                "drawn without keyboard, sound or braille access."
            )

    # ------------------------------------------------------------------ #
    #  Public API, mirroring PlotlyMaidr                                   #
    # ------------------------------------------------------------------ #

    def render(self, use_cdn: bool | Literal["auto"] = "auto") -> Tag:
        """Return the maidr plot inside an iframe.

        Parameters
        ----------
        use_cdn : bool or {"auto"}, default="auto"
            * ``True``: reference the public jsDelivr CDN only.
            * ``False``: reference the bundled ``maidr.js`` assets.
            * ``"auto"`` (default): attempt the CDN first and fall back
              to the bundled copy client-side if the CDN request fails.

            BokehJS itself is always loaded from Bokeh's CDN.
        """
        return self._create_html_tag(use_iframe=True, use_cdn=use_cdn)

    def show(
        self,
        renderer: Literal["auto", "ipython", "browser"] = "auto",
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> object:
        """Display the accessible Bokeh plot.

        Parameters
        ----------
        renderer : {"auto", "ipython", "browser"}, default="auto"
            Renderer to use.
        use_cdn : bool or {"auto"}, default="auto"
            See :meth:`render` for the three possible modes.
        """
        # Stash the bundle on the notebook ``window`` for the iframe loader;
        # see ``PlotlyMaidr.show``, which this mirrors.
        if use_cdn is not True and Environment.is_notebook():
            try:
                from maidr.api import init_notebook

                init_notebook(use_cdn=use_cdn, force=True)
            except Exception:
                pass

        if renderer == "auto":
            _renderer = cast(Literal["ipython", "browser"], Environment.get_renderer())
        else:
            _renderer = renderer

        if _renderer == "browser" and not Environment.is_notebook():
            return self._open_plot_in_browser(use_cdn=use_cdn)

        html = self._create_html_tag(use_iframe=True, use_cdn=use_cdn)
        return html.show(_renderer)

    def save_html(
        self,
        file: str,
        *,
        lib_dir: str | None = "lib",
        include_version: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> str:
        """Save the accessible HTML representation to a file.

        Parameters
        ----------
        file : str
            Destination HTML file path.
        lib_dir : str | None, default="lib"
            Folder (relative to ``file``) used for static dependencies.
        include_version : bool, default=True
            Whether to stamp the dependency folder name with a version.
        use_cdn : bool or {"auto"}, default="auto"
            See :meth:`render` for the three possible modes.  When set
            to ``False`` or ``"auto"`` the bundled MAIDR JS assets are
            copied into ``lib_dir`` alongside the saved HTML.
        """
        html = self._create_html_doc(
            use_iframe=False,
            use_cdn=use_cdn,
            prelude=local_dotpad_sdk_dependency(
                use_cdn=use_cdn, lib_prefix=lib_dir, include_version=include_version
            ),
        )
        return html.save_html(file, libdir=lib_dir, include_version=include_version)

    def destroy(self) -> None:
        """Clean up resources."""
        del self._cells
        del self._model

    # ------------------------------------------------------------------ #
    #  Schema                                                              #
    # ------------------------------------------------------------------ #

    @property
    def layers(self) -> list[BokehLayer]:
        """Every layer, subplot by subplot in reading order."""
        return [layer for _, _, layers in self._cells for layer in layers]

    def _flatten_maidr(self) -> dict | None:
        """
        Build the MAIDR schema, one subplot per plot of the layout.

        Returns
        -------
        dict or None
            The schema, or ``None`` when no plot yielded a layer -- there is
            then nothing for ``maidr.js`` to bind, and the plot is drawn
            without it.
        """
        if not self.layers:
            return None
        grid: list[list[dict]] = [
            [{"id": str(uuid.uuid4()), "layers": []} for _ in row_]
            for row_ in self._grid()
        ]
        for row, col, layers in self._compacted_cells():
            grid[row][col]["layers"].extend(layer.schema for layer in layers)
        return {"id": self.maidr_id, "subplots": grid}

    def _compacted_cells(self) -> list[tuple[int, int, list[BokehLayer]]]:
        """
        The plots maidr can read, on a grid with no row or column left empty.

        A plot that yields no layer -- only unsupported glyphs, say -- takes
        no cell: the grid describes what a reader can reach, and an empty
        cell would be one more stop on the way to the readable plot beside
        it. The Plotly path drops such cells for the same reason (#702).

        Returns
        -------
        list of tuple of (int, int, list of BokehLayer)
            ``(row, col, layers)`` for each plot with layers, renumbered so
            every row and every column holds at least one.
        """
        kept = [cell for cell in self._cells if cell[2]]
        rows = {row: i for i, row in enumerate(sorted({r for r, _, _ in kept}))}
        cols = {col: i for i, col in enumerate(sorted({c for _, c, _ in kept}))}
        return [(rows[r], cols[c], layers) for r, c, layers in kept]

    def _grid(self) -> list[list[Any]]:
        """
        The plot drawn in each cell of the subplot grid, ``None`` for a hole.

        Returns
        -------
        list of list
            Rows top first, each as wide as the widest row; the plot at each
            cell a reader can reach, or ``None`` where the layout leaves a
            gap (``row(a, column(b, c))`` has nothing under ``a``).
        """
        cells = self._compacted_cells()
        rows = 1 + max((row for row, _, _ in cells), default=-1)
        cols = 1 + max((col for _, col, _ in cells), default=-1)
        grid: list[list[Any]] = [[None] * cols for _ in range(rows)]
        for row, col, layers in cells:
            grid[row][col] = layers[0].plot
        return grid

    def _highlight_map(self, cursors: dict[tuple, str]) -> dict[str, dict]:
        """
        What the page's ``onNavigate`` needs, keyed by layer id.

        Parameters
        ----------
        cursors : dict
            The cursor renderer placed for each ``(plot id, x range name,
            y range name)``; see :meth:`_cursors`.

        Returns
        -------
        dict
            Layer id to its highlight entry, with a cursor layer's entry
            naming the renderer that draws its cursor.
        """
        out: dict[str, dict] = {}
        for layer in self.layers:
            if layer.highlight is None:
                continue
            entry = dict(layer.highlight)
            if entry["kind"] == "cursor":
                cursor = cursors.get(_cursor_key(layer))
                if cursor is None:
                    continue
                entry["cursor"] = cursor
            out[str(layer.schema["id"])] = entry
        return out

    @contextmanager
    def _cursors(self) -> Iterator[dict[tuple, str]]:
        """
        Add the highlight cursors to the plots that need one, for a moment.

        One per plot and pair of ranges, since a line on a twin axis is
        placed against that axis. Empty until the page moves it, so it
        neither draws nor widens an auto-ranged axis until a reader is on a
        point -- which is always inside the range already.

        Yields
        ------
        dict
            ``(plot id, x range name, y range name)`` to cursor renderer id.
        """
        from bokeh.models import ColumnDataSource, GlyphRenderer, Scatter

        added: list[tuple[Any, Any]] = []
        ids: dict[tuple, str] = {}
        try:
            for layer in self.layers:
                if not layer.highlight or layer.highlight["kind"] != "cursor":
                    continue
                key = _cursor_key(layer)
                if key in ids:
                    continue
                cursor = GlyphRenderer(
                    data_source=ColumnDataSource(data={"x": [], "y": []}),
                    glyph=Scatter(
                        x="x",
                        y="y",
                        marker="circle",
                        size=_CURSOR_SIZE,
                        fill_color=None,
                        line_color=_CURSOR_COLOR,
                        line_width=_CURSOR_LINE_WIDTH,
                    ),
                    x_range_name=layer.x_range_name,
                    y_range_name=layer.y_range_name,
                    level="overlay",
                    name="maidr-highlight-cursor",
                )
                layer.plot.renderers.append(cursor)
                added.append((layer.plot, cursor))
                ids[key] = cursor.id
            yield ids
        finally:
            for plot, cursor in reversed(added):
                plot.renderers.remove(cursor)

    # ------------------------------------------------------------------ #
    #  HTML                                                                #
    # ------------------------------------------------------------------ #

    def _bokeh_scripts(self) -> list[Tag]:
        """
        The BokehJS ``<script>`` tags this model needs, from Bokeh's CDN.

        Asks Bokeh which of its bundles the model uses -- widgets and
        tables are separate files -- the way ``bokeh.embed.file_html``
        does, falling back to the full CDN set if that helper moves.
        """
        from bokeh.resources import CDN

        raw: list[str] = []
        try:
            from bokeh.embed.bundle import bundle_for_objs_and_resources

            bundle = bundle_for_objs_and_resources([self._model], CDN)
            urls = [str(getattr(u, "url", u)) for u in bundle.js_files]
            raw = list(bundle.js_raw)
        except Exception:
            urls = list(CDN.js_files)
        return [tags.script(src=url) for url in urls] + [
            tags.script(HTML(code)) for code in raw
        ]

    def _build_init_script(
        self,
        item: dict,
        schema: dict | None,
        highlight: dict,
        *,
        wrapper_id: str,
        target_id: str,
        use_cdn: bool | Literal["auto"],
        iframe_in_notebook: bool,
    ) -> str:
        """
        Build the JS that embeds the plot, then binds MAIDR to it.

        The payload lands only after ``embed_item`` resolves, and only
        after the document has parsed: ``maidr.js`` scans the page for
        ``maidr-data`` once, at ``DOMContentLoaded``, and waiting for that
        scan to have happened is what lets the script tell the two cases
        apart. A runtime already on the page is told about the chart with
        the ``maidr:bindchart`` event; one not yet loaded is loaded now,
        and finds the payload on its own first scan. Doing both would
        mount the chart twice and drop the highlight callback with the
        first mount.

        Parameters
        ----------
        item : dict
            The plot as ``bokeh.embed.json_item`` serializes it.
        schema : dict or None
            The MAIDR schema; ``None`` embeds the plot and binds nothing.
        highlight : dict
            See :meth:`_highlight_map`.
        wrapper_id : str
            The element the schema is put on.
        target_id : str
            The element BokehJS renders into, inside the wrapper.
        use_cdn : bool or {"auto"}
            See :meth:`render`.
        iframe_in_notebook : bool
            See :func:`maidr.util.bundle_loader.iframe_mode`.

        Returns
        -------
        str
            The script, as an immediately invoked function.
        """
        loader = maidr_loader_js(use_cdn, iframe_in_notebook=iframe_in_notebook)
        return (
            _INIT_TEMPLATE.replace("__ITEM__", _script_json(item))
            .replace("__SCHEMA__", _script_json(schema))
            .replace("__HIGHLIGHT__", _script_json(highlight))
            .replace("__WRAPPER__", _script_json(wrapper_id))
            .replace("__TARGET__", _script_json(target_id))
            .replace("__WAIT_MS__", str(_WAIT_MS))
            .replace("__LOADER__", loader)
        )

    def _create_html_tag(
        self,
        use_iframe: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> Tag:
        """Create HTML with the interactive Bokeh plot and MAIDR bound to it.

        Parameters
        ----------
        use_iframe : bool, default=True
            Wrap the rendered output in a sandboxed iframe for
            notebook / Shiny / Flask environments.
        use_cdn : bool or {"auto"}, default="auto"
            See :meth:`render` for mode descriptions.
        """
        from bokeh.embed import json_item

        will_iframe, iframe_in_notebook, iframe_inline_bundle = iframe_mode(use_iframe)
        schema = self._flatten_maidr()
        if schema is not None and use_cdn is not True:
            warn_if_bundle_cannot_render(
                schema_trace_types(schema), bundle_is_primary=use_cdn is False
            )

        with _document_left_as_found(self._model), self._cursors() as cursors:
            item = json_item(self._model)
            highlight = self._highlight_map(cursors)

        wrapper_id = f"maidr-bokeh-{uuid.uuid4()}"
        target_id = f"{wrapper_id}-plot"
        init_script = self._build_init_script(
            item,
            schema,
            highlight,
            wrapper_id=wrapper_id,
            target_id=target_id,
            use_cdn=use_cdn,
            iframe_in_notebook=iframe_in_notebook,
        )

        children: list[Any] = maidr_bundle_children(
            use_cdn,
            iframe_in_notebook=iframe_in_notebook,
            iframe_inline_bundle=iframe_inline_bundle,
        )
        children.extend(self._bokeh_scripts())
        children.append(tags.div(tags.div(id=target_id), id=wrapper_id))
        children.append(tags.script(HTML(init_script), type="text/javascript"))

        dotpad_child = dotpad_config_child(inline=will_iframe)
        if dotpad_child is not None:
            children.insert(0, dotpad_child)

        base_html = tags.div(*children)
        chart_title = chart_title_of(schema or {})
        if will_iframe:
            # BokehJS and maidr.js both mount after ``iframe.onload``, which
            # is the case the Plotly wrapper's delayed resizing handles.
            base_html = wrap_in_iframe_plotly(base_html, chart_title)
        return with_chart_title(base_html, chart_title)

    def _create_html_doc(
        self,
        use_iframe: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
        *,
        prelude: Any = None,
    ) -> HTMLDocument:
        """Create a full HTML document."""
        tag = self._create_html_tag(use_iframe, use_cdn=use_cdn)
        children = [tag] if prelude is None else [prelude, tag]
        return HTMLDocument(*children, lang="en")

    def _open_plot_in_browser(self, use_cdn: bool | Literal["auto"] = "auto") -> None:
        """Open the rendered HTML in a browser via a temp file."""
        static_temp_dir = os.path.join(tempfile.gettempdir(), "maidr")
        os.makedirs(static_temp_dir, exist_ok=True)
        temp_file_path = os.path.join(static_temp_dir, "maidr_bokeh_plot.html")
        html_file_path = self.save_html(temp_file_path, use_cdn=use_cdn)
        webbrowser.open(f"file://{html_file_path}")


def _cursor_key(layer: BokehLayer) -> tuple:
    return (layer.plot.id, layer.x_range_name, layer.y_range_name)


@contextmanager
def _document_left_as_found(model: Any) -> Iterator[None]:
    """
    Undo the ``Document`` that serializing gives a model which had none.

    ``bokeh.embed.json_item`` adds a free-standing plot to a new document
    and leaves it there. A plot can belong to one document only, so a
    caller who went on to ``curdoc().add_root(p)`` -- a Bokeh server app
    that also saves an accessible copy -- would be refused with "Models
    must be owned by only a single document". A model that arrived in a
    document stays in it.
    """
    owner = model.document
    try:
        yield
    finally:
        if owner is None and model.document is not None:
            model.document.remove_root(model)


#: The page script. Built by placeholder replacement rather than as an
#: f-string, for the reason ``maidr.util.bundle_loader._parent_source``
#: gives: a JS body is all braces.
_INIT_TEMPLATE = """(function() {
    var item = __ITEM__;
    var schema = __SCHEMA__;
    var highlight = __HIGHLIGHT__;
    var wrapper = document.getElementById(__WRAPPER__);
    var targetId = __TARGET__;
    var started = Date.now();

    function whenParsed(then) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', then);
        } else {
            then();
        }
    }

    function whenBokeh(then) {
        if (window.Bokeh && window.Bokeh.embed && window.Bokeh.embed.embed_item) {
            then();
        } else if (Date.now() - started < __WAIT_MS__) {
            setTimeout(function() { whenBokeh(then); }, 50);
        } else if (window.console) {
            console.error('[maidr] BokehJS did not load, so the chart cannot be drawn.');
        }
    }

    function bokehDocument() {
        var docs = (window.Bokeh && window.Bokeh.documents) || [];
        for (var i = docs.length - 1; i >= 0; i--) {
            if (docs[i].get_model_by_id(item.root_id)) return docs[i];
        }
        return null;
    }

    // --- Highlight: MAIDR's onNavigate, answered in the Bokeh document. ---
    function highlighter(doc) {
        function model(id) { return doc.get_model_by_id(id); }
        function sources() {
            var out = [];
            Object.keys(highlight).forEach(function(layerId) {
                var entry = highlight[layerId];
                var cells = entry.kind === 'points' ? entry.points
                    : entry.kind === 'select' ? [].concat.apply([], entry.grid) : [];
                cells.forEach(function(cell) {
                    var r = cell && model(cell[0]);
                    if (r && out.indexOf(r.data_source) < 0) out.push(r.data_source);
                });
            });
            return out;
        }
        var selectable = sources();
        function clear() {
            selectable.forEach(function(source) {
                if (source.selected.indices.length) source.selected.indices = [];
            });
            Object.keys(highlight).forEach(function(layerId) {
                var entry = highlight[layerId];
                var cursor = entry.kind === 'cursor' && model(entry.cursor);
                if (cursor && cursor.data_source.data.x.length) {
                    cursor.data_source.data = { x: [], y: [] };
                }
            });
        }
        function onNavigate(info) {
            clear();
            if (!info) return;
            var entry = highlight[info.layerId];
            if (!entry) return;
            if (entry.kind === 'points') {
                var byRenderer = {};
                (info.pointIndices || []).forEach(function(i) {
                    var cell = entry.points[i];
                    if (cell) (byRenderer[cell[0]] = byRenderer[cell[0]] || []).push(cell[1]);
                });
                Object.keys(byRenderer).forEach(function(id) {
                    var r = model(id);
                    if (r) r.data_source.selected.indices = byRenderer[id];
                });
                return;
            }
            var row = entry.grid[info.row];
            var cell = row && row[info.col];
            if (!cell) return;
            if (entry.kind === 'select') {
                var r = model(cell[0]);
                if (r) r.data_source.selected.indices = [cell[1]];
            } else if (entry.kind === 'cursor') {
                var cursor = model(entry.cursor);
                if (cursor) cursor.data_source.data = { x: [cell[0]], y: [cell[1]] };
            }
        }
        return { onNavigate: onNavigate, clear: clear };
    }

    // The callback cannot travel in maidr-data, which is JSON, so it is
    // handed over through the live-data API once the chart has mounted:
    // maidr.js builds the chart's controller from the data stored there on
    // the next focus-in, and that is where onNavigate is wired.
    function registerHighlight(doc) {
        if (!doc || !Object.keys(highlight).length) return;
        var hl = highlighter(doc);
        var article = 'maidr-article-' + schema.id;
        var full = Object.assign({}, schema, { onNavigate: hl.onNavigate });
        function attempt() {
            if (Date.now() - started > 2 * __WAIT_MS__) return;
            if (!window.maidrLive || !document.getElementById(article)) {
                setTimeout(attempt, 50);
                return;
            }
            // The article is committed a frame before the chart registers
            // itself for live data, in an effect.
            requestAnimationFrame(function() {
                requestAnimationFrame(function() {
                    if (!window.maidrLive.setData(full)) setTimeout(attempt, 100);
                });
            });
        }
        attempt();
        // MAIDR tears its controller down when focus leaves the chart and
        // reports nothing, so the highlight is cleared here instead.
        document.addEventListener('focusout', function() {
            setTimeout(function() {
                var el = document.getElementById(article);
                if (el && !el.contains(document.activeElement)) hl.clear();
            }, 0);
        });
    }

    function bind() {
        if (!schema || !wrapper) return;
        wrapper.setAttribute('maidr-data', JSON.stringify(schema));
        if (window.maidrLive) {
            wrapper.dispatchEvent(new CustomEvent('maidr:bindchart', { bubbles: true }));
        } else {
__LOADER__
        }
        registerHighlight(bokehDocument());
    }

    whenParsed(function() {
        whenBokeh(function() {
            window.Bokeh.embed.embed_item(item, targetId).then(bind, function(error) {
                if (window.console) console.error('[maidr] Bokeh could not draw the chart:', error);
            });
        });
    });
})();"""
