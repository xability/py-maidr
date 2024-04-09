from __future__ import annotations

import io
import json
from uuid import uuid4

from htmltools import HTML, HTMLDocument, RenderedHTML, tags
from lxml import etree

from matplotlib.figure import Figure

from maidr.core.maidr_plot import MaidrPlot


class Maidr:
    def __init__(self, fig: Figure) -> None:
        self._fig = fig
        self._plots = list()

    @property
    def fig(self) -> Figure:
        return self._fig

    @property
    def data(self) -> list[MaidrPlot]:
        return self._plots

    def add_plot(self, plot: MaidrPlot) -> None:
        self._plots.append(plot)

    def render(
        self, *, lib_prefix: str | None = "lib", include_version: bool = True
    ) -> RenderedHTML:
        html = self._create_html()
        return html.render(lib_prefix=lib_prefix, include_version=include_version)

    def save_html(
        self, file: str, *, lib_dir: str | None = "lib", include_version: bool = True
    ) -> str:
        html = self._create_html()
        return html.save_html(file, libdir=lib_dir, include_version=include_version)

    def _create_html(self) -> HTMLDocument:
        svg = self._get_svg()
        maidr = f"\nlet maidr = {json.dumps(self._flatten_maidr(), indent=2)}\n"

        # inject svg and maidr into html
        return Maidr._inject_plot(svg, maidr)

    def _flatten_maidr(self) -> dict | list[dict]:
        maidr = [plot.schema for plot in self._plots]
        return maidr if len(maidr) != 1 else maidr[0]

    def _get_svg(self) -> HTML:
        svg_buffer = io.StringIO()
        self._fig.savefig(svg_buffer, format="svg")
        str_svg = svg_buffer.getvalue()

        etree.register_namespace("svg", "http://www.w3.org/2000/svg")
        tree_svg = etree.fromstring(str_svg.encode(), parser=None)
        root_svg = None
        # find the `svg` tag and set unique id if not present else use it
        for element in tree_svg.iter(tag="{http://www.w3.org/2000/svg}svg"):
            if "id" not in element.attrib:
                element.attrib["id"] = Maidr._unique_id()
            root_svg = element
            self._set_maidr_id(element.attrib["id"])
            break

        svg_buffer = io.StringIO()  # Reset the buffer
        svg_buffer.write(
            etree.tostring(root_svg, pretty_print=True, encoding="unicode")  # type: ignore # noqa
        )

        return HTML(svg_buffer.getvalue())

    def _set_maidr_id(self, maidr_id: str) -> None:
        for maidr in self._plots:
            maidr.set_id(maidr_id)

    @staticmethod
    def _unique_id() -> str:
        return str(uuid4())

    @staticmethod
    def _inject_plot(plot: HTML, maidr: str) -> HTMLDocument:
        return HTMLDocument(
            tags.html(
                tags.head(
                    tags.meta(charset="UTF-8"),
                    tags.title("MAIDR"),
                    tags.link(
                        rel="stylesheet",
                        href="https://cdn.jsdelivr.net/npm/maidr/dist/maidr_style.min.css",
                    ),
                    tags.script(
                        type="text/javascript",
                        src="https://cdn.jsdelivr.net/npm/maidr/dist/maidr.min.js",
                    ),
                ),
                tags.body(tags.div(plot)),
                tags.script(maidr),
            ),
            lang="en",
        )
