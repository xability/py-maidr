"""Render Altair charts with MAIDR accessibility via the upstream Vega-Lite adapter.

Architecture
------------
This module no longer pre-renders Altair specs to SVG on the Python side.
Instead it ships the Vega-Lite spec into an iframe that loads the upstream
``maidr@<ver>/dist/vegalite.js`` adapter (which itself bundles the MAIDR
React UI) plus the Vega/Vega-Lite/Vega-Embed peer dependencies, then calls
``window.maidrVegaLite.embed(container, spec, options)``.

That entry point performs the rendering via ``vegaEmbed`` and then invokes
``bindVegaLite`` which runs the visual-order sort/reorder pipeline
(``sortSimpleBarsByVisualOrder``, ``reorderSegmentedSeriesByVisualBottom``,
``sortHistogramBinsByVisualOrder``, ``applySegmentedDomMappings``,
``sortHeatmapCellsByVisualOrder``, ``sortLinesByVisualOrder``,
``buildBoxPlotSelectorsFromDom``). All MAIDR JSON construction is therefore
delegated to the upstream adapter.

Limitations
-----------
* Only single-view (``alt.Chart``) and layered (``alt.LayerChart`` /
  ``c1 + c2``) specs are supported. Facet (``alt.Chart.facet(...)``),
  repeat (``alt.Chart.repeat(...)``), and concat
  (``alt.hconcat`` / ``alt.vconcat`` / ``alt.concat``) composite specs
  are intentionally rejected by ``is_altair_chart`` and will not render
  through this adapter.
* CDN-only: vega/vega-lite/vega-embed are loaded from jsDelivr. Offline
  rendering for Altair charts will be added in a follow-up that bundles
  these peer libraries into ``maidr/static/``.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Literal, cast

from htmltools import HTML, HTMLDocument, Tag, tags

from maidr.util.environment import Environment
from maidr.util.iframe_utils import wrap_in_iframe_plotly


# ---------------------------------------------------------------------------
# CDN configuration for the Altair adapter. Tracks ``maidr@latest`` so the
# vegalite.js adapter, the React UI bundle, and the maidr.css stylesheet
# stay in sync with upstream releases. Pin to a specific version here only
# for short-lived testing.
# ---------------------------------------------------------------------------
_MAIDR_VERSION = "latest"
_VEGA_CDN = "https://cdn.jsdelivr.net/npm/vega@5"
_VEGA_LITE_CDN = "https://cdn.jsdelivr.net/npm/vega-lite@5"
_VEGA_EMBED_CDN = "https://cdn.jsdelivr.net/npm/vega-embed@6"
_MAIDR_VEGALITE_CDN = (
    f"https://cdn.jsdelivr.net/npm/maidr@{_MAIDR_VERSION}/dist/vegalite.js"
)
_MAIDR_CSS_CDN = f"https://cdn.jsdelivr.net/npm/maidr@{_MAIDR_VERSION}/dist/maidr.css"


def _spec_to_safe_json(spec: dict) -> str:
    """Serialise a Vega-Lite spec for safe embedding in an HTML ``<script>``.

    Escapes ``</`` so the spec string cannot terminate the surrounding
    ``<script>`` tag, and escapes the line/paragraph separators U+2028 and
    U+2029 which are valid JSON whitespace but illegal in JavaScript string
    literals.
    """
    payload = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    return (
        payload
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


class AltairMaidr:
    """Render an Altair chart with MAIDR accessibility features.

    Parameters
    ----------
    chart : altair.Chart or altair.LayerChart
        A single-view chart (``alt.Chart``) or a layered composite
        (``alt.LayerChart`` / ``c1 + c2``). Facet, repeat, and concat
        composite specs are not supported.
    """

    def __init__(self, chart: Any) -> None:
        self._chart = chart
        self._spec = chart.to_dict()
        self._maidr_id = str(uuid.uuid4())
        self._container_id = f"maidr-altair-{self._maidr_id}"

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def render(self) -> Tag:
        """Return the maidr plot as an HTML tag (with iframe for notebooks)."""
        return self._create_html_tag(use_iframe=True)

    def save_html(
        self,
        file: str,
        *,
        lib_dir: str | None = "lib",
        include_version: bool = True,
        data_in_svg: bool = True,
    ) -> str:
        """Save the accessible chart as a self-contained HTML file.

        Parameters
        ----------
        file : str
            Output HTML path.
        lib_dir : str, optional
            Subdirectory (relative to ``file``) where MAIDR static
            dependencies are copied.
        include_version : bool, default True
            Forwarded to :meth:`htmltools.HTMLDocument.render`.
        data_in_svg : bool, default True
            Retained for API compatibility with the matplotlib pathway.
            Ignored by this adapter: the Vega-Lite spec is always embedded
            in the page so the browser can render and bind via
            ``maidrVegaLite.embed``.
        """
        del data_in_svg  # kept for signature parity; not meaningful here
        html = self._create_html_doc(use_iframe=False)

        destdir = str(Path(file).resolve().parent)
        if lib_dir:
            dep_destdir = os.path.join(destdir, lib_dir)
        else:
            dep_destdir = destdir

        rendered = html.render(lib_prefix=lib_dir, include_version=include_version)
        for dep in rendered["dependencies"]:
            dep.copy_to(dep_destdir, include_version=include_version)

        with open(file, "w", encoding="utf-8") as f:
            f.write(rendered["html"])
        return file

    def show(
        self,
        renderer: Literal["auto", "ipython", "browser"] = "auto",
    ) -> object:
        """Display the accessible chart."""
        html = self._create_html_tag(use_iframe=True)

        if renderer == "auto":
            _renderer = cast(Literal["ipython", "browser"], Environment.get_renderer())
        else:
            _renderer = renderer

        if _renderer == "browser" and not Environment.is_notebook():
            return self._open_in_browser()

        return html.show(_renderer)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _create_html_tag(self, use_iframe: bool = True) -> Tag:
        """Build the HTML tree for an embedded Vega-Lite spec."""
        base_html = self._build_inner_html()

        if use_iframe and (
            Environment.is_flask()
            or Environment.is_notebook()
            or Environment.is_shiny()
        ):
            return self._wrap_in_iframe(base_html)
        return base_html

    def _create_html_doc(self, use_iframe: bool = True) -> HTMLDocument:
        return HTMLDocument(self._create_html_tag(use_iframe), lang="en")

    def _build_inner_html(self) -> Tag:
        """Build the in-iframe document: stylesheet + script tags + container."""
        spec_json = _spec_to_safe_json(self._spec)
        # The chart id passed to ``maidrVegaLite.embed`` becomes the
        # maidr-side identifier. Use the same UUID we generated for the
        # Python wrapper so logs/debugging line up.
        bootstrap = f"""
            (function() {{
                function showError(msg) {{
                    var el = document.getElementById({json.dumps(self._container_id)});
                    if (!el) return;
                    el.innerHTML = '';
                    var pre = document.createElement('pre');
                    pre.style.cssText = 'color:#b00020;background:#fdecea;'
                        + 'border:1px solid #f5c2c0;padding:8px;'
                        + 'font:12px/1.4 monospace;white-space:pre-wrap;';
                    pre.textContent = '[maidr] ' + msg;
                    el.appendChild(pre);
                }}
                function bootstrap() {{
                    if (!window.maidrVegaLite || typeof window.maidrVegaLite.embed !== 'function') {{
                        showError('maidrVegaLite.embed is unavailable. '
                            + 'Check that vegalite.js loaded successfully.');
                        return;
                    }}
                    var spec;
                    try {{
                        spec = JSON.parse({json.dumps(spec_json)});
                    }} catch (e) {{
                        showError('Failed to parse Vega-Lite spec: ' + e.message);
                        return;
                    }}
                    try {{
                        window.maidrVegaLite.embed(
                            '#' + {json.dumps(self._container_id)},
                            spec,
                            {{ id: {json.dumps(self._maidr_id)} }}
                        ).catch(function(err) {{
                            showError(String(err && err.message ? err.message : err));
                        }});
                    }} catch (err) {{
                        showError(String(err && err.message ? err.message : err));
                    }}
                }}
                function startBootstrap() {{
                    // Double rAF: first rAF fires before paint; second rAF
                    // fires after the browser has completed at least one
                    // layout+paint cycle, so getBoundingClientRect() returns
                    // real coordinates for SVG elements. This is required
                    // inside iframes where DOMContentLoaded fires before
                    // layout completes — the upstream visual-order sort
                    // functions (buildBoxPlotSelectorsFromDom,
                    // sortSimpleBarsByVisualOrder, sortHistogramBinsByVisualOrder,
                    // sortHeatmapCellsByVisualOrder,
                    // reorderSegmentedSeriesByVisualBottom) all bail out via
                    // isLaidOutForSort when bboxes are zero-dimensional.
                    requestAnimationFrame(function() {{
                        requestAnimationFrame(bootstrap);
                    }});
                }}
                if (document.readyState === 'loading') {{
                    document.addEventListener('DOMContentLoaded', startBootstrap);
                }} else {{
                    startBootstrap();
                }}
            }})();
        """

        children: list[Any] = [
            tags.link(rel="stylesheet", href=_MAIDR_CSS_CDN),
            tags.script(src=_VEGA_CDN),
            tags.script(src=_VEGA_LITE_CDN),
            tags.script(src=_VEGA_EMBED_CDN),
            tags.script(src=_MAIDR_VEGALITE_CDN),
            tags.div(id=self._container_id),
            tags.script(HTML(bootstrap), type="text/javascript"),
        ]
        return tags.div(*children)

    def _wrap_in_iframe(self, inner: Tag) -> Tag:
        """Wrap ``inner`` in an auto-resizing iframe (notebook / Shiny / Flask).

        Delegates to :func:`maidr.util.iframe_utils.wrap_in_iframe_plotly`
        because Altair's runtime characteristics match Plotly's: external
        libraries (vega/vega-lite/vega-embed/vegalite.js) load from CDN and
        the chart + MAIDR React UI mount asynchronously *after*
        ``iframe.onload`` has already fired. The Plotly helper handles this
        with delayed retries (500/1500/3000 ms) plus a ResizeObserver
        (MutationObserver fallback) on ``document.body``.
        """
        return wrap_in_iframe_plotly(inner)

    def _open_in_browser(self) -> None:
        """Save to a temp HTML file and open it in the default browser."""
        system_temp_dir = tempfile.gettempdir()
        static_temp_dir = os.path.join(system_temp_dir, "maidr")
        os.makedirs(static_temp_dir, exist_ok=True)

        temp_file_path = os.path.join(static_temp_dir, "maidr_plot.html")
        html_file_path = self.save_html(temp_file_path)

        if Environment.is_wsl():
            wsl_distro_name = Environment.get_wsl_distro_name()
            if not wsl_distro_name:
                raise ValueError("WSL_DISTRO_NAME environment variable is not set.")
            html_file_path = Path(html_file_path).resolve().as_posix()
            url = f"file://wsl$/{wsl_distro_name}{html_file_path}"

            explorer_path = Environment.find_explorer_path()
            if explorer_path:
                try:
                    result = subprocess.run(
                        [explorer_path, url],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        return
                    else:
                        webbrowser.open(url)
                except (subprocess.TimeoutExpired, Exception):
                    webbrowser.open(url)
            else:
                webbrowser.open(url)
        else:
            webbrowser.open(f"file://{html_file_path}")
