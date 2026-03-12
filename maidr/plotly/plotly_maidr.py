from __future__ import annotations

import json
import os
import tempfile
import uuid
import webbrowser
from collections import defaultdict
from typing import Any, Literal

from htmltools import HTML, HTMLDocument, Tag, tags

from maidr.plotly.plotly_plot import PlotlyPlot
from maidr.plotly.plotly_plot_factory import PlotlyPlotFactory
from maidr.util.environment import Environment
from maidr.util.iframe_utils import wrap_in_iframe_plotly


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

    @staticmethod
    def _trace_axis_ref(trace: dict) -> tuple[str, str]:
        """Return layout axis keys for a trace.

        Plotly traces reference their subplot axes via ``xaxis`` and
        ``yaxis`` fields containing values like ``"x"``, ``"x2"``,
        ``"y3"``, etc.  This converts them to layout keys such as
        ``"xaxis"``, ``"xaxis2"``, ``"yaxis3"``.
        """
        xref = trace.get("xaxis", "x")
        yref = trace.get("yaxis", "y")

        # "x" -> "xaxis", "x2" -> "xaxis2"
        x_key = "xaxis" + xref[1:] if xref else "xaxis"
        y_key = "yaxis" + yref[1:] if yref else "yaxis"

        return x_key, y_key

    @staticmethod
    def _subplot_grid_position(
        layout: dict, xaxis_name: str, yaxis_name: str
    ) -> tuple[int, int]:
        """Determine subplot grid position from axis domain values.

        Plotly's ``make_subplots`` assigns each axis a ``domain`` property
        that specifies its fractional position within the figure.  This
        method collects all unique domain start values to compute row/col
        indices.
        """
        # Collect all x-axis domain starts and y-axis domain starts
        x_starts: set[float] = set()
        y_starts: set[float] = set()

        for key, val in layout.items():
            if key.startswith("xaxis") and isinstance(val, dict):
                domain = val.get("domain", [0, 1])
                x_starts.add(round(domain[0], 6))
            if key.startswith("yaxis") and isinstance(val, dict):
                domain = val.get("domain", [0, 1])
                y_starts.add(round(domain[0], 6))

        # Sort: x left-to-right gives columns, y top-to-bottom gives rows
        # y domains: higher start = higher on page = lower row index
        sorted_x = sorted(x_starts)
        sorted_y = sorted(y_starts, reverse=True)

        # Get this axis's domain start
        xaxis = layout.get(xaxis_name, {})
        yaxis = layout.get(yaxis_name, {})
        x_start = round(xaxis.get("domain", [0, 1])[0], 6)
        y_start = round(yaxis.get("domain", [0, 1])[0], 6)

        col = sorted_x.index(x_start) if x_start in sorted_x else 0
        row = sorted_y.index(y_start) if y_start in sorted_y else 0

        return row, col

    def _extract_plots(self) -> None:
        """Extract PlotlyPlot instances from all traces in the figure.

        Groups traces by their subplot position (axis pair), then applies
        merging rules within each group:

        * Multiple bar traces with ``barmode='group'`` or ``'stack'`` are
          merged into a single :class:`PlotlyGroupedBarPlot`.
        * Multiple scatter/lines traces are merged into a single
          :class:`PlotlyMultiLinePlot` (matching ``MultiLinePlot``).
        * Multiple box traces are merged into a single
          :class:`PlotlyMultiBoxPlot` (matching ``BoxPlot``).
        """
        fig_dict = self._fig.to_dict()
        layout = fig_dict.get("layout", {})
        traces = fig_dict.get("data", [])
        barmode = layout.get("barmode", "group")

        # Group traces by their subplot axis pair
        axis_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for trace in traces:
            axis_pair = self._trace_axis_ref(trace)
            axis_groups[axis_pair].append(trace)

        # Process each subplot group independently
        for (xaxis_name, yaxis_name), group_traces in axis_groups.items():
            axis_kwargs = {
                "xaxis_name": xaxis_name,
                "yaxis_name": yaxis_name,
            }
            row, col = self._subplot_grid_position(
                layout, xaxis_name, yaxis_name
            )

            bar_traces = [
                t for t in group_traces if t.get("type") == "bar"
            ]
            line_traces = [
                t
                for t in group_traces
                if t.get("type") in ("scatter", "scattergl")
                and "lines" in t.get("mode", "")
                and "markers" not in t.get("mode", "")
            ]
            box_traces = [
                t for t in group_traces if t.get("type") == "box"
            ]

            merged: set[int] = set()

            # Grouped / stacked bars
            if len(bar_traces) > 1 and barmode in ("group", "stack"):
                from maidr.core.enum.plot_type import PlotType
                from maidr.plotly.grouped_bar import PlotlyGroupedBarPlot

                plot_type = (
                    PlotType.DODGED
                    if barmode == "group"
                    else PlotType.STACKED
                )
                plot = PlotlyGroupedBarPlot(
                    bar_traces, layout, plot_type, **axis_kwargs
                )
                plot.row_index = row
                plot.col_index = col
                self._plots.append(plot)
                merged.update(id(t) for t in bar_traces)

            # Multi-line
            if len(line_traces) > 1:
                from maidr.plotly.multiline import PlotlyMultiLinePlot

                plot = PlotlyMultiLinePlot(
                    line_traces, layout, **axis_kwargs
                )
                plot.row_index = row
                plot.col_index = col
                self._plots.append(plot)
                merged.update(id(t) for t in line_traces)

            # Multi-box
            if len(box_traces) > 1:
                from maidr.plotly.multibox import PlotlyMultiBoxPlot

                plot = PlotlyMultiBoxPlot(
                    box_traces, layout, **axis_kwargs
                )
                plot.row_index = row
                plot.col_index = col
                self._plots.append(plot)
                merged.update(id(t) for t in box_traces)

            # Remaining traces
            for trace in group_traces:
                if id(trace) in merged:
                    continue
                plot = PlotlyPlotFactory.create(
                    trace, layout, **axis_kwargs
                )
                if plot is not None:
                    plot.row_index = row
                    plot.col_index = col
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
        """Build the MAIDR schema from all extracted plots.

        Groups plots by their ``(row_index, col_index)`` position to
        construct a subplot grid matching the Plotly figure layout.
        """
        # Collect schemas with their grid positions
        plot_entries = []
        for plot in self._plots:
            plot_entries.append(
                {
                    "schema": plot.schema,
                    "row": plot.row_index,
                    "col": plot.col_index,
                }
            )

        max_row = max((e["row"] for e in plot_entries), default=0)
        max_col = max((e["col"] for e in plot_entries), default=0)
        is_multi_subplot = max_row > 0 or max_col > 0

        # Build the grid
        subplot_grid: list[list[dict]] = [
            [{} for _ in range(max_col + 1)] for _ in range(max_row + 1)
        ]

        # Group by position
        position_groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for entry in plot_entries:
            pos = (entry["row"], entry["col"])
            position_groups[pos].append(entry["schema"])

        for (row, col), layers in position_groups.items():
            cell: dict = {
                "id": str(uuid.uuid4()),
                "layers": layers,
            }
            if is_multi_subplot:
                selector_id = f"axes_{uuid.uuid4()}"
                cell["selector"] = f'g[id="{selector_id}"]'
            subplot_grid[row][col] = cell

        # Fill empty cells
        for r in range(len(subplot_grid)):
            for c in range(len(subplot_grid[r])):
                if not subplot_grid[r][c]:
                    subplot_grid[r][c] = {
                        "id": str(uuid.uuid4()),
                        "layers": [],
                    }

        return {
            "id": self.maidr_id,
            "subplots": subplot_grid,
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
        injects the MAIDR schema into the SVG element and loads the MAIDR
        JS library.  Plotly-specific SVG normalization (subplot wrapping,
        layout fixes, accessibility patches) is handled by the Plotly
        adapter inside maidr.js itself.
        """
        maidr_js = "https://cdn.jsdelivr.net/npm/maidr@latest/dist/maidr.js"
        return f"""
        (function() {{
            var maidrSchema = {json.dumps(schema, indent=2)};

            var _maidrDone = false;
            function initMaidr() {{
                if (_maidrDone) return;
                var svg = document.querySelector('svg.main-svg');
                if (!svg) {{
                    requestAnimationFrame(initMaidr);
                    return;
                }}
                _maidrDone = true;

                svg.setAttribute('id', maidrSchema.id);
                svg.setAttribute('maidr', JSON.stringify(maidrSchema));

                var existing = document.querySelector(
                    'script[src="{maidr_js}"]'
                );
                if (!existing) {{
                    var s = document.createElement('script');
                    s.src = '{maidr_js}';
                    document.head.appendChild(s);
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
            base_html = wrap_in_iframe_plotly(base_html)

        return base_html

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
