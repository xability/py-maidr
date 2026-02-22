from __future__ import annotations

import json
import os
import tempfile
import uuid
import webbrowser
from typing import Any, Literal

from htmltools import HTML, HTMLDocument, Tag, tags

from maidr.plotly.plotly_plot import PlotlyPlot
from maidr.plotly.plotly_plot_factory import PlotlyPlotFactory
from maidr.util.environment import Environment


class PlotlyMaidr:
    """
    Handles rendering Plotly figures as accessible MAIDR HTML.

    Preserves the full Plotly interactive experience (hover, zoom, pan,
    click events) while layering MAIDR accessibility features (sonification,
    braille, data table) on top via the MAIDR JS library.

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
        """Extract PlotlyPlot instances from all traces in the figure.

        Applies merging rules that mirror the matplotlib pipeline:

        * Multiple bar traces with ``barmode='group'`` or ``'stack'`` are
          merged into a single :class:`PlotlyGroupedBarPlot`.
        * Multiple scatter/lines traces are merged into a single
          :class:`PlotlyMultiLinePlot` (matching ``MultiLinePlot``).
        """
        fig_dict = self._fig.to_dict()
        layout = fig_dict.get("layout", {})
        traces = fig_dict.get("data", [])

        bar_traces = [t for t in traces if t.get("type") == "bar"]
        barmode = layout.get("barmode", "group")

        line_traces = [
            t
            for t in traces
            if t.get("type") in ("scatter", "scattergl")
            and "lines" in t.get("mode", "")
            and "markers" not in t.get("mode", "")
        ]

        # Track which traces are handled by merge rules
        merged: set[int] = set()

        # Grouped / stacked bars
        if len(bar_traces) > 1 and barmode in ("group", "stack"):
            from maidr.core.enum.plot_type import PlotType
            from maidr.plotly.grouped_bar import PlotlyGroupedBarPlot

            plot_type = (
                PlotType.DODGED if barmode == "group" else PlotType.STACKED
            )
            self._plots.append(
                PlotlyGroupedBarPlot(bar_traces, layout, plot_type)
            )
            merged.update(id(t) for t in bar_traces)

        # Multi-line: merge multiple lines-only traces into one layer
        if len(line_traces) > 1:
            from maidr.plotly.multiline import PlotlyMultiLinePlot

            self._plots.append(PlotlyMultiLinePlot(line_traces, layout))
            merged.update(id(t) for t in line_traces)

        # Process remaining traces normally
        for trace in traces:
            if id(trace) in merged:
                continue
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

    def _get_plotly_html(self) -> str:
        """Get Plotly's interactive HTML div.

        Returns the chart as an interactive HTML fragment that includes
        plotly.js from CDN.  This preserves all native Plotly features
        (hover, zoom, pan, click events, etc.).
        """
        return self._fig.to_html(
            full_html=False,
            include_plotlyjs="cdn",
        )

    def _build_init_script(self, schema: dict) -> str:
        """Build JS that bridges Plotly's SVG with MAIDR.

        After Plotly renders its chart into the DOM as an SVG, this script
        injects the MAIDR schema as an attribute on that SVG element, then
        loads the MAIDR JS library which reads the schema and provides
        sonification, braille, and keyboard navigation.
        """
        maidr_js = "https://cdn.jsdelivr.net/npm/maidr@latest/dist/maidr.js"
        return f"""
        (function() {{
            var maidrSchema = {json.dumps(schema, indent=2)};

            function initMaidr() {{
                var svg = document.querySelector('svg.main-svg');
                if (!svg) {{
                    requestAnimationFrame(initMaidr);
                    return;
                }}
                svg.setAttribute('id', maidrSchema.id);
                svg.setAttribute('maidr', JSON.stringify(maidrSchema));

                var existing = document.querySelector(
                    'script[src="{maidr_js}"]'
                );
                if (!existing) {{
                    var s = document.createElement('script');
                    s.src = '{maidr_js}';
                    s.onload = function() {{
                        if (window.main) window.main();
                    }};
                    document.head.appendChild(s);
                }} else if (window.main) {{
                    window.main();
                }}
            }}

            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', initMaidr);
            }} else {{
                requestAnimationFrame(initMaidr);
            }}
        }})();
        """

    def _create_html_tag(self, use_iframe: bool = True) -> Tag:
        """Create HTML with interactive Plotly chart and MAIDR accessibility.

        The output includes:

        1. MAIDR CSS for accessibility UI styling
        2. The interactive Plotly chart (plotly.js loaded from CDN)
        3. A bridge script that waits for Plotly to render, injects the
           MAIDR schema into the SVG, and loads MAIDR JS
        """
        schema = self._flatten_maidr()
        plotly_div = self._get_plotly_html()
        init_script = self._build_init_script(schema)

        maidr_css = "https://cdn.jsdelivr.net/npm/maidr@latest/dist/maidr_style.css"

        base_html = tags.div(
            tags.link(rel="stylesheet", href=maidr_css),
            tags.div(HTML(plotly_div)),
            tags.script(init_script, type="text/javascript"),
        )

        if use_iframe and (
            Environment.is_flask()
            or Environment.is_notebook()
            or Environment.is_shiny()
        ):
            base_html = self._wrap_in_iframe(base_html)

        return base_html

    def _wrap_in_iframe(self, html_tag: Tag) -> Tag:
        """Wrap the HTML tag in an auto-resizing iframe for notebooks."""
        unique_id = "iframe_" + str(uuid.uuid4())

        resizing_script = f"""
            function resizeIframe() {{
                let iframe = document.getElementById('{unique_id}');
                if (
                    iframe && iframe.contentWindow &&
                    iframe.contentWindow.document
                ) {{
                    iframe.style.height = 'auto';
                    let height =
                        iframe.contentWindow.document.body.scrollHeight + 50;
                    iframe.style.height = height + 'px';
                    iframe.style.width =
                        iframe.contentWindow.document.body.scrollWidth + 'px';
                }}
            }}
            let iframe = document.getElementById('{unique_id}');
            resizeIframe();
            iframe.onload = function() {{
                resizeIframe();
                iframe.contentWindow.addEventListener(
                    'resize', resizeIframe
                );
            }};
        """

        return tags.iframe(
            id=unique_id,
            srcdoc=str(html_tag.get_html_string()),
            width="100%",
            height="100%",
            scrolling="no",
            style=("background-color: #fff; position: relative; border: none"),
            frameBorder=0,
            onload=resizing_script,
        )

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
