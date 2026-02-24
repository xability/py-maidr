"""Main AltairMaidr class for rendering Altair charts with MAIDR accessibility."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
import webbrowser
import subprocess
from pathlib import Path
from typing import Any, Literal, cast

from htmltools import HTML, HTMLDocument, Tag, tags

from maidr.core.enum.maidr_key import MaidrKey
from maidr.altair.data_extractor import extract_chart_data
from maidr.util.environment import Environment


class AltairMaidr:
    """Render an Altair chart with MAIDR accessibility features.

    Parameters
    ----------
    chart : altair.Chart or composite
        Any Altair chart object (Chart, LayerChart, HConcatChart,
        VConcatChart, FacetChart, ConcatChart, RepeatChart).
    """

    def __init__(self, chart: Any) -> None:
        self._chart = chart
        self._spec = chart.to_dict()
        self._maidr_id = str(uuid.uuid4())

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
        """Save the accessible chart as an HTML file."""
        html = self._create_html_doc(use_iframe=False, data_in_svg=data_in_svg)

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
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _create_html_tag(
        self, use_iframe: bool = True, data_in_svg: bool = True
    ) -> Tag:
        """Build the HTML structure with embedded SVG and MAIDR metadata."""
        schema = self._flatten_maidr()
        svg = self._get_svg(embed_data=data_in_svg, schema=schema)

        maidr_json = None
        if not data_in_svg:
            maidr_json = f"\nvar maidr = {json.dumps(schema, indent=2)}\n"

        return self._inject_plot(svg, maidr_json, self._maidr_id, use_iframe)

    def _create_html_doc(
        self, use_iframe: bool = True, data_in_svg: bool = True
    ) -> HTMLDocument:
        return HTMLDocument(self._create_html_tag(use_iframe, data_in_svg), lang="en")

    def _get_svg(self, embed_data: bool = True, schema: dict | None = None) -> HTML:
        """Generate SVG from the Altair chart using vl-convert-python."""
        try:
            import vl_convert as vlc
        except ImportError:
            raise ImportError(
                "vl-convert-python is required for Altair support in maidr. "
                "Install it with: pip install vl-convert-python"
            )

        svg_str = vlc.vegalite_to_svg(self._spec)

        # Parse and inject MAIDR attributes
        from lxml import etree

        etree.register_namespace("svg", "http://www.w3.org/2000/svg")
        tree_svg = etree.fromstring(svg_str.encode(), parser=None)

        root_svg = None
        for element in tree_svg.iter(tag="{http://www.w3.org/2000/svg}svg"):
            current_schema = schema if schema is not None else self._flatten_maidr()
            if isinstance(current_schema, dict) and "id" in current_schema:
                element.attrib["id"] = str(current_schema["id"])
            if embed_data:
                element.attrib["maidr"] = json.dumps(current_schema, indent=2)
            root_svg = element
            break

        if root_svg is None:
            # Fallback: use the raw SVG
            return HTML(svg_str)

        return HTML(etree.tostring(root_svg, pretty_print=True, encoding="unicode"))

    def _flatten_maidr(self) -> dict:
        """Build the MAIDR JSON schema from the Vega-Lite spec."""
        specs = self._collect_unit_specs(self._spec)

        subplot_grid: list[list[dict]] = []

        if len(specs) == 0:
            # Empty chart
            return {
                "id": self._maidr_id,
                "subplots": [[{"id": str(uuid.uuid4()), "layers": []}]],
            }

        if len(specs) == 1 and specs[0]["row"] == 0 and specs[0]["col"] == 0:
            # Single chart
            layers = [s["schema"] for s in specs]
            return {
                "id": self._maidr_id,
                "subplots": [[{"id": str(uuid.uuid4()), "layers": layers}]],
            }

        # Multi-chart: build grid
        max_row = max(s["row"] for s in specs)
        max_col = max(s["col"] for s in specs)

        subplot_grid = [
            [{"id": str(uuid.uuid4()), "layers": []} for _ in range(max_col + 1)]
            for _ in range(max_row + 1)
        ]

        for s in specs:
            subplot_grid[s["row"]][s["col"]]["layers"].append(s["schema"])

        return {"id": self._maidr_id, "subplots": subplot_grid}

    def _collect_unit_specs(self, spec: dict, row: int = 0, col: int = 0) -> list[dict]:
        """Recursively collect unit specs from potentially composite charts.

        Returns a list of dicts with keys: schema, row, col.
        """
        results = []

        # Layer chart: {"layer": [...]}
        if "layer" in spec:
            for layer_spec in spec["layer"]:
                # Inherit data from parent if not present
                child = _inherit_data(spec, layer_spec)
                schema = extract_chart_data(child)
                schema[MaidrKey.ID] = str(uuid.uuid4())
                results.append({"schema": schema, "row": row, "col": col})
            return results

        # Horizontal concatenation: {"hconcat": [...]}
        if "hconcat" in spec:
            for i, sub in enumerate(spec["hconcat"]):
                results.extend(self._collect_unit_specs(sub, row=row, col=col + i))
            return results

        # Vertical concatenation: {"vconcat": [...]}
        if "vconcat" in spec:
            for i, sub in enumerate(spec["vconcat"]):
                results.extend(self._collect_unit_specs(sub, row=row + i, col=col))
            return results

        # General concatenation: {"concat": [...]}
        if "concat" in spec:
            columns = spec.get("columns", len(spec["concat"]))
            for i, sub in enumerate(spec["concat"]):
                r = row + i // columns
                c = col + i % columns
                results.extend(self._collect_unit_specs(sub, row=r, col=c))
            return results

        # Facet chart: {"facet": ..., "spec": ...}
        if "facet" in spec and "spec" in spec:
            inner_spec = spec["spec"]
            # Inherit data from the outer spec
            inner_spec = _inherit_data(spec, inner_spec)
            schema = extract_chart_data(inner_spec)
            schema[MaidrKey.ID] = str(uuid.uuid4())
            results.append({"schema": schema, "row": row, "col": col})
            return results

        # Repeat chart: {"repeat": ..., "spec": ...}
        if "repeat" in spec and "spec" in spec:
            inner_spec = spec["spec"]
            inner_spec = _inherit_data(spec, inner_spec)
            schema = extract_chart_data(inner_spec)
            schema[MaidrKey.ID] = str(uuid.uuid4())
            results.append({"schema": schema, "row": row, "col": col})
            return results

        # Unit spec (has "mark")
        if "mark" in spec:
            schema = extract_chart_data(spec)
            schema[MaidrKey.ID] = str(uuid.uuid4())
            results.append({"schema": schema, "row": row, "col": col})
            return results

        return results

    def _open_in_browser(self) -> None:
        """Open the chart in a browser."""
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

    @staticmethod
    def _inject_plot(
        plot: HTML, maidr: str | None, maidr_id: str, use_iframe: bool = True
    ) -> Tag:
        """Embed the plot and MAIDR scripts into the HTML structure.

        This mirrors ``Maidr._inject_plot()`` from the matplotlib pathway.
        """
        MAIDR_TS_CDN_URL = "https://cdn.jsdelivr.net/npm/maidr@latest/dist/maidr.js"

        script = f"""
            (function() {{
                var existing = document.querySelector('script[src="{MAIDR_TS_CDN_URL}"]');
                if (!existing) {{
                    var s = document.createElement('script');
                    s.src = '{MAIDR_TS_CDN_URL}';
                    s.onload = function() {{ if (window.main) window.main(); }};
                    document.head.appendChild(s);
                }} else {{
                    if (document.readyState === 'loading') {{
                        document.addEventListener('DOMContentLoaded', function() {{ if (window.main) window.main(); }});
                    }} else {{
                        if (window.main) window.main();
                    }}
                }}
            }})();
        """

        children: list[Any] = [
            tags.link(
                rel="stylesheet",
                href="https://cdn.jsdelivr.net/npm/maidr@latest/dist/maidr_style.css",
            )
        ]
        if maidr is not None:
            children.append(tags.script(maidr, type="text/javascript"))
        children.append(tags.script(script, type="text/javascript"))
        children.append(tags.div(plot))

        base_html = tags.div(*children)

        if use_iframe and (
            Environment.is_flask()
            or Environment.is_notebook()
            or Environment.is_shiny()
        ):
            unique_id = "iframe_" + str(uuid.uuid4())
            resizing_script = f"""
                function resizeIframe() {{
                    let iframe = document.getElementById('{unique_id}');
                    if (iframe && iframe.contentWindow && iframe.contentWindow.document) {{
                        let iframeDocument = iframe.contentWindow.document;
                        let brailleContainer = iframeDocument.querySelector('[id^="maidr-braille-textarea"]');
                        let reviewInputContainer = iframeDocument.querySelector('.maidr-review-input');
                        iframe.style.height = 'auto';
                        let height = iframeDocument.body.scrollHeight;
                        let isBrailleActive = brailleContainer && (
                            brailleContainer === iframeDocument.activeElement ||
                            (typeof brailleContainer.contains === 'function' && brailleContainer.contains(iframeDocument.activeElement))
                        );
                        let isReviewInputActive = reviewInputContainer && (
                            reviewInputContainer === iframeDocument.activeElement ||
                            (typeof reviewInputContainer.contains === 'function' && reviewInputContainer.contains(iframeDocument.activeElement))
                        );
                        if (isBrailleActive) {{ height += 100; }}
                        else if (isReviewInputActive) {{ height += 50; }}
                        else {{ height += 50; }}
                        iframe.style.height = (height) + 'px';
                        iframe.style.width = iframeDocument.body.scrollWidth + 'px';
                    }}
                }}
                let iframe = document.getElementById('{unique_id}');
                resizeIframe();
                iframe.onload = function() {{
                    resizeIframe();
                    iframe.contentWindow.addEventListener('resize', resizeIframe);
                }};
                iframe.contentWindow.document.addEventListener('focusin', (e) => {{
                    try {{
                        const t = e && e.target ? e.target : null;
                        if (t && typeof t.id === 'string' && t.id.startsWith('maidr-braille-textarea')) resizeIframe();
                    }} catch (_) {{ resizeIframe(); }}
                }}, true);
                iframe.contentWindow.document.addEventListener('focusout', (e) => {{
                    try {{
                        const t = e && e.target ? e.target : null;
                        if (t && typeof t.id === 'string' && t.id.startsWith('maidr-braille-textarea')) resizeIframe();
                    }} catch (_) {{ resizeIframe(); }}
                }}, true);
                iframe.contentWindow.document.addEventListener('focusin', (e) => {{
                    try {{
                        const t = e && e.target ? e.target : null;
                        if (t && t.classList && t.classList.contains('maidr-review-input')) resizeIframe();
                    }} catch (_) {{ resizeIframe(); }}
                }}, true);
                iframe.contentWindow.document.addEventListener('focusout', (e) => {{
                    try {{
                        const t = e && e.target ? e.target : null;
                        if (t && t.classList && t.classList.contains('maidr-review-input')) resizeIframe();
                    }} catch (_) {{ resizeIframe(); }}
                }}, true);
            """

            base_html = tags.iframe(
                id=unique_id,
                srcdoc=str(base_html.get_html_string()),
                width="100%",
                height="100%",
                scrolling="no",
                style="background-color: #fff; position: relative; border: none",
                frameBorder=0,
                onload=resizing_script,
            )

        return base_html


def _inherit_data(parent: dict, child: dict) -> dict:
    """Inherit ``data`` and ``datasets`` from a parent spec if the child lacks them."""
    merged = dict(child)
    if "data" not in merged and "data" in parent:
        merged["data"] = parent["data"]
    if "datasets" not in merged and "datasets" in parent:
        merged["datasets"] = parent["datasets"]
    return merged
