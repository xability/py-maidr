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

import matplotlib.pyplot as plt
from htmltools import HTML, HTMLDocument, Tag, tags
from lxml import etree
from matplotlib.figure import Figure
from maidr.core.enum.plot_type import PlotType

from maidr.core.context_manager import HighlightContextManager
from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.plot import MaidrPlot
from maidr.util.environment import Environment
from maidr.util.dedup_utils import deduplicate_smooth_and_line


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

    def render(self) -> Tag:
        """Return the maidr plot inside an iframe."""
        return self._create_html_tag(use_iframe=True)

    def save_html(
        self, file: str, *, lib_dir: str | None = "lib", include_version: bool = True
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
        """
        html = self._create_html_doc(
            use_iframe=False
        )  # Always use direct HTML for saving
        return html.save_html(file, libdir=lib_dir, include_version=include_version)

    def show(
        self,
        renderer: Literal["auto", "ipython", "browser"] = "auto",
        clear_fig: bool = True,
    ) -> object:
        """
        Preview the HTML content using the specified renderer.

        Parameters
        ----------
        renderer : Literal["auto", "ipython", "browser"], default="auto"
            The renderer to use for the HTML preview.
        """
        html = self._create_html_tag(use_iframe=True)  # Always use iframe for display

        # Use the passed renderer parameter, fallback to auto-detection
        if renderer == "auto":
            _renderer = cast(Literal["ipython", "browser"], Environment.get_renderer())
        else:
            _renderer = renderer

        # Only try browser opening if explicitly requested as browser and not in notebook
        if _renderer == "browser" and not Environment.is_notebook():
            return self._open_plot_in_browser()

        if clear_fig:
            plt.close()
        return html.show(_renderer)

    def clear(self):
        self._plots = []

    def destroy(self) -> None:
        del self._plots
        del self._fig

    def _open_plot_in_browser(self) -> None:
        """
        Open the rendered HTML content using a temporary file
        """
        system_temp_dir = tempfile.gettempdir()
        static_temp_dir = os.path.join(system_temp_dir, "maidr")
        os.makedirs(static_temp_dir, exist_ok=True)

        temp_file_path = os.path.join(static_temp_dir, "maidr_plot.html")
        html_file_path = self.save_html(
            temp_file_path
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
                        [explorer_path, url],
                        capture_output=True,
                        text=True,
                        timeout=10
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

    def _create_html_tag(self, use_iframe: bool = True) -> Tag:
        """Create the MAIDR HTML using HTML tags."""
        tagged_elements: list[Any] = [
            element for plot in self._plots for element in plot.elements
        ]

        selector_ids = []
        for i, plot in enumerate(self._plots):
            for _ in plot.elements:
                selector_ids.append(self.selector_ids[i])

        with HighlightContextManager.set_maidr_elements(tagged_elements, selector_ids):
            svg = self._get_svg()
        maidr = f"\nlet maidr = {json.dumps(self._flatten_maidr(), indent=2)}\n"

        # Inject plot's svg and MAIDR structure into html tag.
        return Maidr._inject_plot(svg, maidr, self.maidr_id, use_iframe)

    def _create_html_doc(self, use_iframe: bool = True) -> HTMLDocument:
        """Create an HTML document from Tag objects."""
        return HTMLDocument(self._create_html_tag(use_iframe), lang="en")

    def _flatten_maidr(self) -> dict | list[dict]:
        """Return a single plot schema or a list of schemas from the Maidr instance."""
        if self.plot_type in (PlotType.DODGED, PlotType.STACKED):
            self._plots = [self._plots[0]]
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

            if MaidrKey.SELECTOR in schema and plot.type != PlotType.BOX:
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

        return {"id": Maidr._unique_id(), "subplots": subplot_grid}

    def _get_svg(self) -> HTML:
        """Extract the chart SVG from ``matplotlib.figure.Figure``."""
        svg_buffer = io.StringIO()
        self._fig.savefig(svg_buffer, format="svg")
        str_svg = svg_buffer.getvalue()

        etree.register_namespace("svg", "http://www.w3.org/2000/svg")
        tree_svg = etree.fromstring(str_svg.encode(), parser=None)
        root_svg = None
        # Find the `svg` tag and set unique id if not present else use it.
        for element in tree_svg.iter(tag="{http://www.w3.org/2000/svg}svg"):
            if "maidr-data" not in element.attrib:
                element.attrib["maidr-data"] = json.dumps(
                    self._flatten_maidr(), indent=2
                )
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
    def _inject_plot(plot: HTML, maidr: str, maidr_id, use_iframe: bool = True) -> Tag:
        """Embed the plot and associated MAIDR scripts into the HTML structure."""
        # Get the latest version from npm registry
        MAIDR_TS_CDN_URL = "https://cdn.jsdelivr.net/npm/maidr@latest/dist/maidr.js"

        script = f"""
            if (!document.querySelector('script[src="{MAIDR_TS_CDN_URL}"]'))
            {{
                var script = document.createElement('script');
                script.type = 'module';
                script.src = '{MAIDR_TS_CDN_URL}';
                script.addEventListener('load', function() {{
                    window.main();
                }});
                document.head.appendChild(script);
            }} else {{
                document.addEventListener('DOMContentLoaded', function (e) {{
                    window.main();
                }});
            }}
        """

        base_html = tags.div(
            tags.link(
                rel="stylesheet",
                href="https://cdn.jsdelivr.net/npm/maidr@latest/dist/maidr_style.css",
            ),
            tags.script(script, type="text/javascript"),
            tags.div(plot),
        )

        # is_quarto = os.getenv("IS_QUARTO") == "True"

        # Render the plot inside an iframe if in a Jupyter notebook, Google Colab
        # or VSCode notebook. No need for iframe if this is a Quarto document.
        # For TypeScript we will use iframe by default for now
        if use_iframe and (Environment.is_flask() or Environment.is_notebook() or Environment.is_shiny()):
            unique_id = "iframe_" + Maidr._unique_id()

            def generate_iframe_script(unique_id: str) -> str:
                resizing_script = f"""
                    function resizeIframe() {{
                        let iframe = document.getElementById('{unique_id}');
                        if (
                            iframe && iframe.contentWindow &&
                            iframe.contentWindow.document
                        ) {{
                            let iframeDocument = iframe.contentWindow.document;
                            let brailleContainer =
                                iframeDocument.getElementById('braille-input');
                            iframe.style.height = 'auto';
                            let height = iframeDocument.body.scrollHeight;
                            if (brailleContainer &&
                                brailleContainer === iframeDocument.activeElement
                            ) {{
                                height += 100;
                            }}else{{
                                height += 50
                            }}
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
                    iframe.contentWindow.document.addEventListener('focusin', () => {{
                        resizeIframe();
                    }});
                    iframe.contentWindow.document.addEventListener('focusout', () => {{
                        resizeIframe();
                    }});
                """
                return resizing_script

            resizing_script = generate_iframe_script(unique_id)

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
