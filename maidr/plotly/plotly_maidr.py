from __future__ import annotations

import json
import os
import tempfile
import uuid
import webbrowser
from typing import Any, Literal

from htmltools import HTML, HTMLDocument, Tag

from maidr.plotly.plotly_plot import PlotlyPlot
from maidr.plotly.plotly_plot_factory import PlotlyPlotFactory
from maidr.util.environment import Environment


class PlotlyMaidr:
    """
    Handles rendering Plotly figures as accessible MAIDR HTML.

    Parameters
    ----------
    fig : plotly.graph_objects.Figure
        The Plotly figure to make accessible.
    """

    def __init__(self, fig: Any) -> None:
        self._fig = fig
        self._plots: list[PlotlyPlot] = []
        self.maidr_id = str(uuid.uuid4())
        self._extract_plots()

    def _extract_plots(self) -> None:
        """Extract PlotlyPlot instances from all traces in the figure."""
        fig_dict = self._fig.to_dict()
        layout = fig_dict.get("layout", {})
        traces = fig_dict.get("data", [])

        for trace in traces:
            plot = PlotlyPlotFactory.create(trace, layout)
            if plot is not None:
                self._plots.append(plot)

    def render(self) -> Tag:
        """Return the maidr plot inside an iframe."""
        return self._create_html_tag(use_iframe=True)

    def show(
        self,
        renderer: Literal["auto", "ipython", "browser"] = "auto",
    ) -> object:
        """Display the accessible Plotly plot."""
        html = self._create_html_tag(use_iframe=True)

        if renderer == "auto":
            _renderer = Environment.get_renderer()
        else:
            _renderer = renderer

        if _renderer == "browser" and not Environment.is_notebook():
            return self._open_plot_in_browser()

        return html.show(_renderer)

    def save_html(
        self,
        file: str,
        *,
        lib_dir: str | None = "lib",
        include_version: bool = True,
    ) -> str:
        """Save the accessible HTML representation to a file."""
        html = self._create_html_doc(use_iframe=False)
        return html.save_html(file, libdir=lib_dir, include_version=include_version)

    def destroy(self) -> None:
        """Clean up resources."""
        del self._plots
        del self._fig

    def _flatten_maidr(self) -> dict:
        """Build the MAIDR schema from all extracted plots."""
        layers = [plot.schema for plot in self._plots]

        return {
            "id": self.maidr_id,
            "subplots": [
                [
                    {
                        "id": str(uuid.uuid4()),
                        "layers": layers,
                    }
                ]
            ],
        }

    def _get_svg(self) -> HTML:
        """Generate SVG from the Plotly figure.

        Uses kaleido for high-fidelity SVG rendering when available.
        Falls back to a placeholder SVG if kaleido fails (e.g. Chrome
        not installed). The MAIDR accessibility features work either way
        since they are driven by the JSON schema, not the SVG graphic.
        """
        schema = self._flatten_maidr()
        svg_str = self._render_svg_with_kaleido()

        if svg_str is not None:
            return self._inject_schema_into_svg(svg_str, schema)

        return self._build_fallback_svg(schema)

    def _render_svg_with_kaleido(self) -> str | None:
        """Try to render SVG via kaleido. Returns None on failure."""
        try:
            svg_bytes = self._fig.to_image(format="svg")
            if isinstance(svg_bytes, bytes):
                return svg_bytes.decode("utf-8")
            return svg_bytes
        except Exception:
            return None

    def _inject_schema_into_svg(self, svg_str: str, schema: dict) -> HTML:
        """Parse a kaleido SVG and inject the MAIDR schema."""
        from lxml import etree

        tree = etree.fromstring(svg_str.encode(), parser=None)

        ns = {"svg": "http://www.w3.org/2000/svg"}
        svg_elem = tree if tree.tag.endswith("svg") else tree.find(".//svg:svg", ns)
        if svg_elem is None:
            svg_elem = tree

        svg_elem.attrib["id"] = str(schema["id"])
        svg_elem.attrib["maidr"] = json.dumps(schema, indent=2)

        result = etree.tostring(svg_elem, pretty_print=True, encoding="unicode")
        return HTML(result)

    def _build_fallback_svg(self, schema: dict) -> HTML:
        """Build a minimal SVG with the MAIDR schema embedded.

        This is used when kaleido/Chrome is unavailable. The MAIDR JS
        library reads the schema from the ``maidr`` attribute, so
        sonification, braille, and text description still work.
        """
        title = ""
        for plot in self._plots:
            title = plot._get_title()
            if title:
                break

        escaped_schema = json.dumps(schema, indent=2).replace("&", "&amp;").replace(
            "<", "&lt;"
        ).replace(">", "&gt;").replace('"', "&quot;")

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'id="{schema["id"]}" '
            f'width="800" height="450" '
            f'maidr="{escaped_schema}" '
            f'role="img" aria-label="{title}">'
            f"<rect width='800' height='450' fill='#f8f9fa' />"
            f"<text x='400' y='225' text-anchor='middle' "
            f"font-size='16' fill='#333'>{title}</text>"
            f"</svg>"
        )
        return HTML(svg)

    def _create_html_tag(
        self, use_iframe: bool = True
    ) -> Tag:
        """Create the MAIDR HTML tag with embedded SVG and scripts."""
        svg = self._get_svg()

        # Reuse the static _inject_plot from the core Maidr class
        from maidr.core.maidr import Maidr

        return Maidr._inject_plot(svg, None, self.maidr_id, use_iframe)

    def _create_html_doc(self, use_iframe: bool = True) -> HTMLDocument:
        """Create a full HTML document."""
        return HTMLDocument(self._create_html_tag(use_iframe), lang="en")

    def _open_plot_in_browser(self) -> None:
        """Open the rendered HTML in a browser via a temp file."""
        system_temp_dir = tempfile.gettempdir()
        static_temp_dir = os.path.join(system_temp_dir, "maidr")
        os.makedirs(static_temp_dir, exist_ok=True)

        temp_file_path = os.path.join(static_temp_dir, "maidr_plotly_plot.html")
        html_file_path = self.save_html(temp_file_path)
        webbrowser.open(f"file://{html_file_path}")
