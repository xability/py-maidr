from __future__ import annotations

import json

import io
import os
import tempfile
import uuid
import webbrowser
import subprocess
from pathlib import Path
from typing import Any, Literal, cast
from collections import defaultdict

import matplotlib.pyplot as plt
from htmltools import HTML, HTMLDocument, Tag, tags
from lxml import etree
from matplotlib.figure import Figure
from maidr.core.enum.plot_type import PlotType

from maidr.core.context_manager import HighlightContextManager
from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.plot import MaidrPlot
from maidr.util.dedup_utils import deduplicate_smooth_and_line
from maidr.util.dependencies import (
    MAIDR_CSS_CDN_URL,
    MAIDR_CSS_FILENAME,
    MAIDR_JS_CDN_URL,
    MAIDR_JS_FILENAME,
    maidr_bundled_files_dependency,
    maidr_bundled_relative_dir,
    maidr_html_dependency,
)
from maidr.util.environment import Environment
from maidr.util.iframe_utils import wrap_in_iframe_matplotlib


class Maidr:
    """
    A class to handle the rendering and interaction
    of matplotlib figures with additional metadata.

    Attributes
    ----------
    _fig : Figure
        The matplotlib figure associated with this instance.
    _plots : list[MaidrPlot]
        A list of MaidrPlot objects which hold additional plot-specific configurations.
    _cached_version : str | None
        Cached version of maidr from npm registry to avoid repeated API calls.

    Methods
    -------
    render(lib_prefix=None, include_version=True)
        Creates and returns a rendered HTML representation of the figure.
    save_html(file, lib_dir=None, include_version=True)
        Saves the rendered HTML representation to a file.
    show(renderer='auto')
        Displays the rendered HTML content in the specified rendering context.
    """

    def __init__(self, fig: Figure, plot_type: PlotType = PlotType.LINE) -> None:
        """Create a new Maidr for the given ``matplotlib.figure.Figure``."""
        self._fig = fig
        self._plots = []
        self.maidr_id = None
        self.selector_ids = []
        self.plot_type = plot_type

    @property
    def fig(self) -> Figure:
        """Return the ``matplotlib.figure.Figure`` associated with this object."""
        return self._fig

    @property
    def plots(self) -> list[MaidrPlot]:
        """Return the list of plots extracted from the ``fig``."""
        return self._plots

    def render(self, use_cdn: bool | Literal["auto"] = "auto") -> Tag:
        """Return the maidr plot inside an iframe.

        Parameters
        ----------
        use_cdn : bool or {"auto"}, default="auto"
            Controls which copy of ``maidr.js`` / ``maidr.css`` the
            rendered HTML references:

            * ``True``: load from the public jsDelivr CDN only (no
              offline fallback).
            * ``False``: reference the copy bundled inside the installed
              ``maidr`` package.  Useful for air-gapped environments.
            * ``"auto"`` (default): attempt the CDN first and fall back
              to the bundled copy client-side via a ``<script onerror>``
              handler.  The bundled files are copied next to the output
              so the fallback works without network access.
        """
        return self._create_html_tag(use_iframe=True, use_cdn=use_cdn)

    def save_html(
        self,
        file: str,
        *,
        lib_dir: str | None = "lib",
        include_version: bool = True,
        data_in_svg: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> str:
        """
        Save the HTML representation of the figure with MAIDR to a file.

        Parameters
        ----------
        file : str
            The file to save to.
        lib_dir : str, default="lib"
            The directory to save the dependencies to
            (relative to the file's directory).
        include_version : bool, default=True
            Whether to include the version number in the dependency folder name.
        data_in_svg : bool, default=True
            Controls where the MAIDR JSON payload is placed in the output HTML or SVG.
        use_cdn : bool or {"auto"}, default="auto"
            * ``True``: load ``maidr.js`` from the CDN only.
            * ``False``: copy the bundled ``maidr.js`` / ``maidr.css``
              into ``lib_dir`` next to the saved HTML and reference
              them with relative paths (no network access required).
            * ``"auto"`` (default): attempt the CDN first and fall back
              to the bundled copy client-side if the CDN request fails.
              The bundled files are still copied alongside the HTML so
              the fallback works offline.
        """
        html = self._create_html_doc(
            use_iframe=False, data_in_svg=data_in_svg, use_cdn=use_cdn
        )  # Always use direct HTML for saving

        # Write the HTML ourselves with explicit UTF-8 encoding to avoid
        # UnicodeEncodeError on Windows where the default encoding (e.g.
        # cp1252) cannot represent characters like U+2212 (minus sign).
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
        clear_fig: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> object:
        """
        Preview the HTML content using the specified renderer.

        Parameters
        ----------
        renderer : Literal["auto", "ipython", "browser"], default="auto"
            The renderer to use for the HTML preview.
        clear_fig : bool, default=True
            Whether to close the matplotlib figure after showing.
        use_cdn : bool or {"auto"}, default="auto"
            * ``True``: load ``maidr.js`` from the CDN only.
            * ``False``: render using the copy of ``maidr.js`` bundled
              with the installed package.  For the browser renderer
              the assets are copied next to the temporary HTML file.
            * ``"auto"`` (default): attempt the CDN first and fall back
              to the bundled copy client-side if the CDN request fails.
        """
        # Proactively inject the bundled ``maidr.js`` / ``maidr.css`` into
        # the *current* notebook cell right before the iframe is emitted.
        # The auto-call at ``import maidr`` time is not sufficient in
        # several real-world scenarios:
        #
        #   * The user cleared the notebook's output (the import cell's
        #     ``<script>`` is removed from the DOM even though the Python
        #     ``_NOTEBOOK_LOADED`` flag stays ``True``).
        #   * Cell-isolated frontends (Google Colab, Databricks) sandbox
        #     each cell's output so ``window.__maidrJsSource`` set by
        #     one cell is not visible to later cells.
        #   * The notebook was re-opened without re-running the import.
        #
        # ``force=True`` bypasses the idempotence guard so each plot
        # cell becomes self-contained (bundle ``<script>`` + iframe in
        # the same output).  This mirrors Bokeh's per-output emission
        # strategy and is only enabled when the user opted out of the
        # CDN — callers with ``use_cdn=True`` still get the single
        # ``<script src>`` reference.
        if use_cdn is not True and Environment.is_notebook():
            try:
                from maidr.api import init_notebook

                init_notebook(use_cdn=use_cdn, force=True)
            except Exception:
                # Never block show() on notebook init; the iframe
                # bootstrap will surface a helpful console warning if
                # the bundle is unreachable.
                pass

        html = self._create_html_tag(
            use_iframe=True, use_cdn=use_cdn
        )  # Always use iframe for display

        # Use the passed renderer parameter, fallback to auto-detection
        if renderer == "auto":
            _renderer = cast(Literal["ipython", "browser"], Environment.get_renderer())
        else:
            _renderer = renderer

        # Only try browser opening if explicitly requested as browser and not in notebook
        if _renderer == "browser" and not Environment.is_notebook():
            return self._open_plot_in_browser(use_cdn=use_cdn)

        if clear_fig:
            plt.close()
        return html.show(_renderer)

    def clear(self):
        self._plots = []

    def destroy(self) -> None:
        del self._plots
        del self._fig

    def _open_plot_in_browser(
        self, use_cdn: bool | Literal["auto"] = "auto"
    ) -> None:
        """Open the rendered HTML content using a temporary file.

        Parameters
        ----------
        use_cdn : bool or {"auto"}, default="auto"
            When ``False`` (or ``"auto"``), copy the bundled
            ``maidr.js`` / ``maidr.css`` assets next to the temporary
            HTML file so the browser can load them over ``file://``
            without any network access.
        """
        system_temp_dir = tempfile.gettempdir()
        static_temp_dir = os.path.join(system_temp_dir, "maidr")
        os.makedirs(static_temp_dir, exist_ok=True)

        temp_file_path = os.path.join(static_temp_dir, "maidr_plot.html")
        html_file_path = self.save_html(
            temp_file_path, use_cdn=use_cdn
        )  # This will use use_iframe=False
        if Environment.is_wsl():
            wsl_distro_name = Environment.get_wsl_distro_name()

            # Validate that WSL distro name is available
            if not wsl_distro_name:
                raise ValueError(
                    "WSL_DISTRO_NAME environment variable is not set or is empty. "
                    "Cannot construct WSL file URL. Please ensure you are running in a WSL environment."
                )

            # Ensure html_file_path is an absolute POSIX path for proper WSL URL construction
            html_file_path = Path(html_file_path).resolve().as_posix()

            url = f"file://wsl$/{wsl_distro_name}{html_file_path}"

            # Try to open the file in Windows using explorer.exe with robust path detection
            explorer_path = Environment.find_explorer_path()
            if explorer_path:
                try:
                    result = subprocess.run(
                        [explorer_path, url], capture_output=True, text=True, timeout=10
                    )

                    if result.returncode == 0:
                        return
                    else:
                        # Fall back to webbrowser.open() if explorer.exe fails
                        webbrowser.open(url)

                except subprocess.TimeoutExpired:
                    webbrowser.open(url)
                except Exception:
                    # Fall back to webbrowser.open() if explorer.exe fails
                    webbrowser.open(url)
            else:
                webbrowser.open(url)

        else:
            webbrowser.open(f"file://{html_file_path}")

    def _create_html_tag(
        self,
        use_iframe: bool = True,
        data_in_svg: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> Tag:
        """Create the MAIDR HTML using HTML tags.

        Parameters
        ----------
        use_iframe : bool, default=True
            Whether to render the plot inside an iframe (for notebooks and similar envs).
        data_in_svg : bool, default=True
            If True, the MAIDR JSON is embedded in the root <svg> under attribute 'maidr'.
            If False, a <script>var maidr = {...}</script> tag is injected instead.
        use_cdn : bool or {"auto"}, default="auto"
            Controls how ``maidr.js`` is referenced.  See :meth:`render`
            for the three possible modes.
        """
        tagged_elements: list[Any] = [
            element for plot in self._plots for element in plot.elements
        ]

        selector_ids = []
        for i, plot in enumerate(self._plots):
            for _ in plot.elements:
                selector_ids.append(self.selector_ids[i])

        # Build schema once so id stays consistent across SVG and global var
        schema = self._flatten_maidr()

        with HighlightContextManager.set_maidr_elements(tagged_elements, selector_ids):
            svg = self._get_svg(embed_data=data_in_svg, schema=schema)

        # Generate external payload if data is not embedded in SVG
        maidr = None
        if not data_in_svg:
            maidr = f"\nvar maidr = {json.dumps(schema, indent=2)}\n"

        # Inject plot's svg and MAIDR structure into html tag.
        return Maidr._inject_plot(svg, maidr, self.maidr_id, use_iframe, use_cdn)

    def _create_html_doc(
        self,
        use_iframe: bool = True,
        data_in_svg: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> HTMLDocument:
        """Create an HTML document from Tag objects.

        Parameters
        ----------
        use_iframe : bool, default=True
            Whether to render the plot inside an iframe (for notebooks and similar envs).
        data_in_svg : bool, default=True
            See _create_html_tag for details on payload placement strategy.
        use_cdn : bool or {"auto"}, default="auto"
            Controls how ``maidr.js`` is referenced.  See :meth:`render`.
        """
        return HTMLDocument(
            self._create_html_tag(use_iframe, data_in_svg, use_cdn=use_cdn),
            lang="en",
        )

    def _merge_plots_by_subplot_position(self) -> list[MaidrPlot]:
        """
        Merge plots by their subplot position, keeping only the first plot per position.

        For DODGED and STACKED plot types, multiple plots on the same subplot
        should be merged into a single plot since GroupedBarPlot extracts all
        containers from the axes itself.

        Returns
        -------
        list[MaidrPlot]
            List of plots with one plot per unique subplot position.

        Examples
        --------
        If we have plots at positions [(0,0), (0,0), (0,1), (1,0)],
        this will return plots at positions [(0,0), (0,1), (1,0)].
        """
        # Group plots by their subplot position (row, col) using defaultdict
        subplot_groups: dict[tuple[int, int], list[MaidrPlot]] = defaultdict(list)

        for plot in self._plots:
            # Get subplot position, defaulting to (0, 0) if not set
            position = (getattr(plot, "row_index", 0), getattr(plot, "col_index", 0))
            subplot_groups[position].append(plot)

        # Keep only the first plot for each subplot position
        # The GroupedBarPlot will extract all containers from that axes
        merged_plots: list[MaidrPlot] = []
        for position_plots in subplot_groups.values():
            merged_plots.append(
                position_plots[0]
            )  # Each list is guaranteed to have at least one plot

        return merged_plots

    def _flatten_maidr(self) -> dict | list[dict]:
        """Return a single plot schema or a list of schemas from the Maidr instance."""
        # Handle DODGED/STACKED plots: only keep one plot per subplot position
        # because GroupedBarPlot extracts all containers from the axes itself
        if self.plot_type in (PlotType.DODGED, PlotType.STACKED):
            self._plots = self._merge_plots_by_subplot_position()

        # Deduplicate: if any SMOOTH plots exist, remove LINE plots
        self._plots = deduplicate_smooth_and_line(self._plots)

        unique_gids = set()
        deduped_plots = []
        for plot in self._plots:
            if getattr(plot, "type", None) == PlotType.SMOOTH:
                gid = getattr(plot, "_smooth_gid", None)
                if gid and gid in unique_gids:
                    continue
                if gid:
                    unique_gids.add(gid)
                deduped_plots.append(plot)
            else:
                deduped_plots.append(plot)
        self._plots = deduped_plots

        plot_schemas = []

        for i, plot in enumerate(self._plots):
            schema = plot.schema

            if MaidrKey.SELECTOR in schema and plot.type not in (
                PlotType.BOX,
                PlotType.VIOLIN_BOX,
            ):
                if isinstance(schema[MaidrKey.SELECTOR], str):
                    schema[MaidrKey.SELECTOR] = schema[MaidrKey.SELECTOR].replace(
                        "maidr='true'", f"maidr='{self.selector_ids[i]}'"
                    )
                if isinstance(schema[MaidrKey.SELECTOR], list):
                    for j in range(len(schema[MaidrKey.SELECTOR])):
                        schema[MaidrKey.SELECTOR][j] = schema[MaidrKey.SELECTOR][
                            j
                        ].replace("maidr='true'", f"maidr='{self.selector_ids[i]}'")

            plot_schemas.append(
                {
                    "schema": schema,
                    "row": getattr(plot, "row_index", 0),
                    "col": getattr(plot, "col_index", 0),
                }
            )

        max_row = max([plot.get("row", 0) for plot in plot_schemas], default=0)
        max_col = max([plot.get("col", 0) for plot in plot_schemas], default=0)

        subplot_grid: list[list[dict[str, str | list[Any]]]] = [
            [{} for _ in range(max_col + 1)] for _ in range(max_row + 1)
        ]

        position_groups = {}
        for plot in plot_schemas:
            pos = (plot.get("row", 0), plot.get("col", 0))
            if pos not in position_groups:
                position_groups[pos] = []
            position_groups[pos].append(plot["schema"])

        for (row, col), layers in position_groups.items():
            if subplot_grid[row][col]:
                subplot_grid[row][col]["layers"].append(layers)
            else:
                subplot_grid[row][col] = {"id": Maidr._unique_id(), "layers": layers}

        for i in range(len(subplot_grid)):
            subplot_grid[i] = [
                cell if cell is not None else {"id": Maidr._unique_id(), "layers": []}
                for cell in subplot_grid[i]
            ]

        return {
            "id": Maidr._unique_id(),
            "subplots": subplot_grid,
        }

    def _get_svg(self, embed_data: bool = True, schema: dict | None = None) -> HTML:
        """Extract the chart SVG from ``matplotlib.figure.Figure``.

        Parameters
        ----------
        embed_data : bool, default=True
            If True, embed the MAIDR JSON schema as an attribute named 'maidr' on
            the root <svg> element. If False, do not embed JSON in the SVG.
        schema : dict | None, default=None
            If provided, this schema will be used (ensuring a consistent id across
            the page). If None, a new schema will be generated.
        """
        svg_buffer = io.StringIO()
        self._fig.savefig(svg_buffer, format="svg")
        str_svg = svg_buffer.getvalue()

        etree.register_namespace("svg", "http://www.w3.org/2000/svg")
        tree_svg = etree.fromstring(str_svg.encode(), parser=None)
        root_svg = None
        # Find the `svg` tag and optionally embed MAIDR data.
        for element in tree_svg.iter(tag="{http://www.w3.org/2000/svg}svg"):
            current_schema = schema if schema is not None else self._flatten_maidr()
            # Ensure SVG id matches schema id in both modes
            if isinstance(current_schema, dict) and "id" in current_schema:
                element.attrib["id"] = str(current_schema["id"])  # ensure match
            if embed_data:
                element.attrib["maidr"] = json.dumps(current_schema, indent=2)
            root_svg = element
            break

        svg_buffer = io.StringIO()  # Reset the buffer
        svg_buffer.write(
            etree.tostring(
                root_svg,
                pretty_print=True,
                encoding="unicode",  # type: ignore
            )
        )

        return HTML(svg_buffer.getvalue())

    def _set_maidr_id(self, maidr_id: str) -> None:
        """Set a unique identifier to each ``MaidrPlot``."""
        self.maidr_id = maidr_id
        for maidr in self._plots:
            maidr.set_id(maidr_id)

    @staticmethod
    def _unique_id() -> str:
        """Generate a unique identifier string using UUID4."""
        return str(uuid.uuid4())

    @staticmethod
    def _inject_plot(
        plot: HTML,
        maidr: str | None,
        maidr_id,
        use_iframe: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> Tag:
        """Embed the plot and associated MAIDR scripts into the HTML structure.

        Parameters
        ----------
        plot : htmltools.HTML
            The rendered SVG markup for the chart.
        maidr : str | None
            Optional ``var maidr = {...}`` script body (used when the
            schema is not embedded in the SVG ``maidr`` attribute).
        maidr_id : Any
            Unused placeholder retained for backwards compatibility.
        use_iframe : bool, default=True
            Whether to wrap the output in an iframe for notebook display.
        use_cdn : bool or {"auto"}, default="auto"
            * ``True``: emit only CDN ``<script>`` / ``<link>`` tags
              (no offline fallback).
            * ``False``: emit an :class:`htmltools.HTMLDependency`
              pointing at the bundled ``maidr.js`` / ``maidr.css``
              assets, which ``htmltools`` copies into ``lib_dir``.
            * ``"auto"`` (default): emit a CDN loader with a
              client-side ``onerror`` handler that falls back to the
              bundled copy.  A no-tag dependency ensures the bundled
              files are copied to ``lib_dir`` so the fallback works
              without network access.
        """
        # Decide whether the iframe-in-notebook "load-once" fast path applies.
        # ``Tag.get_html_string()`` (used by ``wrap_in_iframe_matplotlib``)
        # silently drops ``HTMLDependency`` children, so for iframe renders
        # we must not rely on htmltools to inject the bundled script.
        # Instead we emit a small bootstrap that evaluates the JS source
        # which :func:`maidr.api.init_notebook` has stashed on
        # ``window.__maidrJsSource`` in the parent document.  This matches
        # the Plotly/Bokeh "library loaded once per notebook" pattern and
        # keeps the .ipynb file small.
        iframe_in_notebook = use_iframe and (
            Environment.is_notebook() or Environment.is_shiny()
        )

        children: list[Any]
        if use_cdn is False:
            if iframe_in_notebook:
                # Pull the bundled source from the parent document instead
                # of emitting an ``HTMLDependency`` (which would be lost
                # when the iframe wrapper serialises the tag via
                # ``Tag.get_html_string()``).
                parent_source_script = """
                    (function() {
                        function run() { if (window.main) window.main(); }
                        function go() {
                            try {
                                var jsSrc = window.parent && window.parent.__maidrJsSource;
                                var cssSrc = window.parent && window.parent.__maidrCssSource;
                                if (cssSrc) {
                                    var style = document.createElement('style');
                                    style.textContent = cssSrc;
                                    document.head.appendChild(style);
                                }
                                if (jsSrc) {
                                    var s = document.createElement('script');
                                    s.text = jsSrc;
                                    document.head.appendChild(s);
                                    run();
                                    return;
                                }
                            } catch (_) { /* cross-origin or missing parent */ }
                            // Fallback: init_notebook() was not called, log a hint.
                            if (window.console) {
                                console.warn(
                                    'maidr: use_cdn=False requires maidr.init_notebook() ' +
                                    'to be called once per notebook session, or the bundle ' +
                                    'to be available on window.parent.__maidrJsSource.'
                                );
                            }
                        }
                        if (document.readyState === 'loading') {
                            document.addEventListener('DOMContentLoaded', go);
                        } else {
                            go();
                        }
                    })();
                """
                children = []
                if maidr is not None:
                    children.append(tags.script(maidr, type="text/javascript"))
                children.append(
                    tags.script(parent_source_script, type="text/javascript")
                )
                children.append(tags.div(plot))
            else:
                dep = maidr_html_dependency()
                # ``htmltools`` inserts the bundled ``maidr.js`` via a normal
                # ``<script src="...">`` tag; we still need the same
                # ``window.main()`` bootstrap that the CDN loader performs.
                bootstrap_script = """
                    (function() {
                        function run() { if (window.main) window.main(); }
                        if (document.readyState === 'loading') {
                            document.addEventListener('DOMContentLoaded', run);
                        } else {
                            run();
                        }
                    })();
                """
                children = [dep]
                if maidr is not None:
                    children.append(tags.script(maidr, type="text/javascript"))
                children.append(
                    tags.script(bootstrap_script, type="text/javascript")
                )
                children.append(tags.div(plot))
        elif use_cdn == "auto":
            if iframe_in_notebook:
                # Inside a notebook iframe, relative ``lib/maidr-.../maidr.js``
                # paths cannot be resolved (srcdoc iframes have no base URL).
                # Fall back to the parent-source string (populated by
                # :func:`maidr.api.init_notebook`) if the CDN fetch fails.
                auto_script = f"""
                    (function() {{
                        function bootstrap() {{
                            if (document.readyState === 'loading') {{
                                document.addEventListener('DOMContentLoaded', function() {{ if (window.main) window.main(); }});
                            }} else {{
                                if (window.main) window.main();
                            }}
                        }}
                        function fallbackFromParent() {{
                            try {{
                                var jsSrc = window.parent && window.parent.__maidrJsSource;
                                var cssSrc = window.parent && window.parent.__maidrCssSource;
                                if (cssSrc) {{
                                    var style = document.createElement('style');
                                    style.textContent = cssSrc;
                                    document.head.appendChild(style);
                                }}
                                if (jsSrc) {{
                                    var s = document.createElement('script');
                                    s.text = jsSrc;
                                    document.head.appendChild(s);
                                    bootstrap();
                                }}
                            }} catch (_) {{ /* parent unreachable */ }}
                        }}
                        var cssLink = document.createElement('link');
                        cssLink.rel = 'stylesheet';
                        cssLink.href = '{MAIDR_CSS_CDN_URL}';
                        document.head.appendChild(cssLink);
                        var s = document.createElement('script');
                        s.src = '{MAIDR_JS_CDN_URL}';
                        s.onload = bootstrap;
                        s.onerror = fallbackFromParent;
                        document.head.appendChild(s);
                    }})();
                """
                children = []
                if maidr is not None:
                    children.append(tags.script(maidr, type="text/javascript"))
                children.append(tags.script(auto_script, type="text/javascript"))
                children.append(tags.div(plot))
            else:
                # Non-iframe (e.g. ``save_html``): copy the bundle alongside
                # the HTML and emit a CDN loader with an ``onerror``
                # fallback to the relative bundled path.  The browser
                # decides which source to use based on network reachability.
                files_dep = maidr_bundled_files_dependency()
                rel_dir = maidr_bundled_relative_dir()
                bundled_js_rel = f"{rel_dir}/{MAIDR_JS_FILENAME}"
                bundled_css_rel = f"{rel_dir}/{MAIDR_CSS_FILENAME}"
                fallback_script = f"""
                    (function() {{
                        function bootstrap() {{
                            if (document.readyState === 'loading') {{
                                document.addEventListener('DOMContentLoaded', function() {{ if (window.main) window.main(); }});
                            }} else {{
                                if (window.main) window.main();
                            }}
                        }}
                        var cssLink = document.createElement('link');
                        cssLink.rel = 'stylesheet';
                        cssLink.href = '{MAIDR_CSS_CDN_URL}';
                        cssLink.onerror = function() {{
                            var fb = document.createElement('link');
                            fb.rel = 'stylesheet';
                            fb.href = '{bundled_css_rel}';
                            document.head.appendChild(fb);
                        }};
                        document.head.appendChild(cssLink);
                        var existing = document.querySelector('script[src="{MAIDR_JS_CDN_URL}"]');
                        if (existing) {{ bootstrap(); return; }}
                        var s = document.createElement('script');
                        s.src = '{MAIDR_JS_CDN_URL}';
                        s.onload = bootstrap;
                        s.onerror = function() {{
                            var fb = document.createElement('script');
                            fb.src = '{bundled_js_rel}';
                            fb.onload = bootstrap;
                            document.head.appendChild(fb);
                        }};
                        document.head.appendChild(s);
                    }})();
                """
                children = [files_dep]
                if maidr is not None:
                    children.append(tags.script(maidr, type="text/javascript"))
                children.append(
                    tags.script(fallback_script, type="text/javascript")
                )
                children.append(tags.div(plot))
        else:
            # Preserve the historical CDN-loading behaviour byte-for-byte
            # so existing notebooks keep working unchanged.
            script = f"""
                (function() {{
                    var existing = document.querySelector('script[src="{MAIDR_JS_CDN_URL}"]');
                    if (!existing) {{
                        var s = document.createElement('script');
                        s.src = '{MAIDR_JS_CDN_URL}';
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

            children = [
                tags.link(rel="stylesheet", href=MAIDR_CSS_CDN_URL),
            ]
            if maidr is not None:
                children.append(tags.script(maidr, type="text/javascript"))
            children.append(tags.script(script, type="text/javascript"))
            children.append(tags.div(plot))

        base_html = tags.div(*children)

        # Render the plot inside an iframe if in a Jupyter notebook, Google Colab
        # or VSCode notebook. No need for iframe if this is a Quarto document.
        if use_iframe and (
            Environment.is_flask()
            or Environment.is_notebook()
            or Environment.is_shiny()
        ):
            base_html = wrap_in_iframe_matplotlib(base_html)

        return base_html
