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
from maidr.altair.data_extractor import SELECTOR_PLACEHOLDER, extract_chart_data
from maidr.altair.utils import resolve_data
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

            # Inject maidr attributes on SVG mark groups and resolve selectors
            self._inject_selectors(element, current_schema)

            if embed_data:
                element.attrib["maidr"] = json.dumps(current_schema, indent=2)
            root_svg = element
            break

        if root_svg is None:
            # Fallback: use the raw SVG
            return HTML(svg_str)

        return HTML(etree.tostring(root_svg, pretty_print=True, encoding="unicode"))

    @staticmethod
    def _inject_selectors(svg_root: Any, schema: dict) -> None:
        """Inject ``maidr`` attributes on SVG mark groups and resolve selectors.

        Walks the SVG tree to find Vega-Lite mark groups (``<g>`` elements
        with ``role-mark`` in their class), assigns a unique ``maidr`` UUID
        to each, and replaces the ``__MAIDR_ID__`` placeholder in the
        corresponding schema layer's ``selectors`` field.
        """
        ns = "{http://www.w3.org/2000/svg}"

        # Collect all role-mark groups in document order
        mark_groups = [
            g
            for g in svg_root.iter(f"{ns}g")
            if "role-mark" in g.attrib.get("class", "")
        ]

        # Flatten layers from schema in row-major order
        layers: list[dict] = []
        for subplot_row in schema.get("subplots", []):
            for subplot in subplot_row:
                for layer in subplot.get("layers", []):
                    layers.append(layer)

        # Match mark groups to layers. For multiline charts a single layer
        # may own multiple mark groups (one per line).
        layer_idx = 0
        group_idx = 0
        while group_idx < len(mark_groups) and layer_idx < len(layers):
            layer = layers[layer_idx]
            sel = layer.get(MaidrKey.SELECTOR, "")

            # Determine how many mark groups this layer consumes.
            if isinstance(sel, list) and len(sel) > 0:
                # List selector (line / scatter): one selector string per
                # mark group.  For multiline, expand the list.
                new_selectors: list[str] = []
                first_template = sel[0] if sel else ""

                # Count consecutive mark groups that match the same mark type
                first_cls = mark_groups[group_idx].attrib.get("class", "")
                mark_type_token = _extract_mark_class(first_cls)
                n_consumed = 0
                peek = group_idx
                while peek < len(mark_groups):
                    peek_cls = mark_groups[peek].attrib.get("class", "")
                    if _extract_mark_class(peek_cls) != mark_type_token:
                        break
                    # Check we haven't wandered into the next layer's groups
                    # by also checking that the next layer (if any) hasn't
                    # already been assigned.
                    if n_consumed > 0 and layer_idx + 1 < len(layers):
                        # For multiline, all groups share the same mark type
                        pass
                    n_consumed += 1
                    peek += 1

                # If the layer data has multiple sub-arrays (multiline),
                # consume that many groups.
                layer_data = layer.get(MaidrKey.DATA, [])
                if (
                    isinstance(layer_data, list)
                    and len(layer_data) > 0
                    and isinstance(layer_data[0], list)
                ):
                    n_expected = len(layer_data)
                else:
                    n_expected = 1

                n_to_use = min(n_expected, n_consumed)
                for i in range(n_to_use):
                    mg = mark_groups[group_idx + i]
                    maidr_id = str(uuid.uuid4())
                    mg.attrib["maidr"] = maidr_id
                    resolved = first_template.replace(SELECTOR_PLACEHOLDER, maidr_id)
                    new_selectors.append(resolved)

                layer[MaidrKey.SELECTOR] = new_selectors
                group_idx += n_to_use

            elif isinstance(sel, str) and SELECTOR_PLACEHOLDER in sel:
                # String selector (bar / hist / heat / stacked / dodged)
                mg = mark_groups[group_idx]
                maidr_id = str(uuid.uuid4())
                mg.attrib["maidr"] = maidr_id
                layer[MaidrKey.SELECTOR] = sel.replace(SELECTOR_PLACEHOLDER, maidr_id)
                group_idx += 1

            else:
                # Empty or unsupported selector (e.g. box plots) – skip
                # but still consume one mark group so alignment stays correct.
                # Box plots in Vega-Lite generate multiple mark groups for
                # whiskers/boxes/medians; skip them all.
                layer_type = layer.get(MaidrKey.TYPE, "")
                if layer_type == "box":
                    # Consume all box-related mark groups
                    while group_idx < len(mark_groups):
                        cls = mark_groups[group_idx].attrib.get("class", "")
                        if "layer_" in cls or "role-mark" in cls:
                            # Check if this is still a box component
                            if any(
                                tok in cls
                                for tok in (
                                    "mark-rect",
                                    "mark-rule",
                                    "mark-symbol",
                                )
                            ):
                                group_idx += 1
                            else:
                                break
                        else:
                            break
                else:
                    group_idx += 1

            layer_idx += 1

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
                child = _inherit_data(spec, sub)
                results.extend(self._collect_unit_specs(child, row=row, col=col + i))
            return results

        # Vertical concatenation: {"vconcat": [...]}
        if "vconcat" in spec:
            for i, sub in enumerate(spec["vconcat"]):
                child = _inherit_data(spec, sub)
                results.extend(self._collect_unit_specs(child, row=row + i, col=col))
            return results

        # General concatenation: {"concat": [...]}
        if "concat" in spec:
            columns = spec.get("columns", len(spec["concat"]))
            for i, sub in enumerate(spec["concat"]):
                r = row + i // columns
                c = col + i % columns
                child = _inherit_data(spec, sub)
                results.extend(self._collect_unit_specs(child, row=r, col=c))
            return results

        # Facet chart: {"facet": ..., "spec": ...}
        if "facet" in spec and "spec" in spec:
            return self._collect_facet_specs(spec, row, col)

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

    def _collect_facet_specs(self, spec: dict, row: int, col: int) -> list[dict]:
        """Expand a facet spec into one schema per facet cell."""
        import pandas as pd

        facet_def = spec["facet"]
        inner_spec = _inherit_data(spec, spec["spec"])

        # Resolve the full dataset
        df = resolve_data(inner_spec)
        if df.empty:
            schema = extract_chart_data(inner_spec)
            schema[MaidrKey.ID] = str(uuid.uuid4())
            return [{"schema": schema, "row": row, "col": col}]

        # Determine facet fields
        row_field = None
        col_field = None
        wrap_field = None

        if "row" in facet_def and isinstance(facet_def["row"], dict):
            row_field = facet_def["row"].get("field")
        if "column" in facet_def and isinstance(facet_def["column"], dict):
            col_field = facet_def["column"].get("field")
        if "field" in facet_def:
            wrap_field = facet_def["field"]

        results: list[dict] = []

        if wrap_field and wrap_field in df.columns:
            # Wrapped facet: single field, laid out in a grid
            columns = spec.get("columns", 2)
            unique_vals = list(df[wrap_field].unique())
            for i, val in enumerate(unique_vals):
                r = row + i // columns
                c = col + i % columns
                sub_df = df[df[wrap_field] == val]
                cell_spec = dict(inner_spec)
                cell_spec["data"] = {"values": sub_df.to_dict(orient="records")}
                cell_spec.pop("datasets", None)
                schema = extract_chart_data(cell_spec)
                schema[MaidrKey.ID] = str(uuid.uuid4())
                if not schema.get(MaidrKey.TITLE):
                    schema[MaidrKey.TITLE] = f"{wrap_field}: {val}"
                results.append({"schema": schema, "row": r, "col": c})

        elif row_field or col_field:
            # Row/column facet
            row_vals = (
                list(df[row_field].unique())
                if row_field and row_field in df.columns
                else [None]
            )
            col_vals = (
                list(df[col_field].unique())
                if col_field and col_field in df.columns
                else [None]
            )
            for ri, rv in enumerate(row_vals):
                for ci, cv in enumerate(col_vals):
                    mask = pd.Series(True, index=df.index)
                    if rv is not None:
                        mask &= df[row_field] == rv
                    if cv is not None:
                        mask &= df[col_field] == cv
                    sub_df = df[mask]
                    cell_spec = dict(inner_spec)
                    cell_spec["data"] = {"values": sub_df.to_dict(orient="records")}
                    cell_spec.pop("datasets", None)
                    schema = extract_chart_data(cell_spec)
                    schema[MaidrKey.ID] = str(uuid.uuid4())
                    # Build a descriptive title
                    title_parts = []
                    if rv is not None:
                        title_parts.append(f"{row_field}: {rv}")
                    if cv is not None:
                        title_parts.append(f"{col_field}: {cv}")
                    if not schema.get(MaidrKey.TITLE) and title_parts:
                        schema[MaidrKey.TITLE] = ", ".join(title_parts)
                    results.append({"schema": schema, "row": row + ri, "col": col + ci})
        else:
            # Fallback: treat as single unit
            schema = extract_chart_data(inner_spec)
            schema[MaidrKey.ID] = str(uuid.uuid4())
            results.append({"schema": schema, "row": row, "col": col})

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


def _extract_mark_class(class_str: str) -> str:
    """Extract the Vega mark type token (e.g. ``mark-rect``) from a class string."""
    for token in class_str.split():
        if token.startswith("mark-"):
            return token
    return ""
