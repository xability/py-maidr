from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list, colorbar_title

#: What the two halves of a region's reading are, when the author named
#: neither. A choropleth has no cartesian axes to read titles off, and these
#: are what the fields hold: the region it is, and the number it is shaded by.
_AXIS_FALLBACKS = ("Region", "Value")


class PlotlyChoroplethPlot(PlotlyPlot):
    """Extract data from a Plotly ``choropleth`` trace.

    A map whose regions are shaded by a value. The core reads it as
    `CHOROPLETH`, whose point is a region's name and the number it carries.

    **The centroids are not here to be read.** `ChoroplethPoint` takes an
    optional ``lon``/``lat`` pair in degrees, which is what lets a reader
    walk the map spatially rather than down a list. A ``go.Choropleth``
    carries neither: it names its regions -- ``"USA"``, ``"FRA"``, a US state
    -- and plotly resolves those names against geometry it fetches in the
    browser. So the pair genuinely is not in the figure, and the grammar
    already says what that means: "the map is read as a region list in
    declared order, which is a poorer reading but the one the data supports".

    ``neighbors`` is absent for the same reason and a stronger one -- the
    grammar notes adjacency "is not derivable from rendered SVG paths, and
    not from centroids either".
    """

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.CHOROPLETH, **kwargs)

    def _get_selector(self) -> list[str]:
        """No selector, and this one is a limit rather than a decision.

        The other three plotly layers that ship without a highlight do so
        because of something about the chart: a barpolar draws no per-series
        path (#635), a parcoords renders to WebGL (#637), and a parcats is
        laid out in an order that cannot be computed offline (#639).

        This is not that. A choropleth almost certainly *is* addressable --
        plotly draws one ``path`` per region -- but the map could not be
        measured where this was written: plotly requests its geometry from
        ``https://cdn.plot.ly/un/world_110m.json`` at render time, and with
        no network the ``.geolayer`` stays empty (measured:
        ``geo._topojson`` false, zero ``path`` elements, one entry in
        ``calcdata``).

        Emitting a selector that has never resolved would be guessing, and a
        highlight that lands on the wrong region is worse than none. So the
        layer ships without one and keeps its audio, braille and text, and
        the selector is left to whoever can load the map. See #640.
        """
        return []

    def _extract_axes_data(self) -> dict:
        """Name the region and the value it is shaded by.

        A choropleth draws no cartesian axes, so ``layout.xaxis`` holds
        neither name -- reading it would take another trace's titles. The
        colour bar's title is the one thing the author may have written about
        the *value*, and it is exactly what it means, so it is used when it
        is there.
        """
        region, value = _AXIS_FALLBACKS
        return {
            MaidrKey.X: self._axis_config(label=region),
            MaidrKey.Y: self._axis_config(label=colorbar_title(self._trace) or value),
        }

    def _extract_plot_data(self) -> list[dict]:
        """One point per region the trace names.

        Read in the trace's own order, which is the order the grammar says a
        centroid-less map is navigated in. A region with no value is dropped:
        plotly leaves it unshaded, so announcing it would put a region on the
        map that the reader cannot be told anything about.
        """
        locations = as_list(self._trace.get("locations"))
        values = as_list(self._trace.get("z"))

        return [
            {
                MaidrKey.X: str(self._to_native(location)),
                MaidrKey.Y: self._to_native(value),
            }
            for location, value in zip(locations, values)
            if value is not None
        ]


#: The three names plotly gives one chart. ``choropleth`` shades regions on a
#: geographic projection; ``choroplethmap`` and its deprecated
#: ``choroplethmapbox`` spelling shade the same regions over a tiled base map.
#: They carry the same ``locations`` and ``z`` and are read identically -- the
#: base map is drawing, not data (#683).
_CHOROPLETH_TYPES = frozenset(
    {"choropleth", "choroplethmap", "choroplethmapbox"}
)


def is_choropleth_trace(trace: dict) -> bool:
    """Report whether a trace is a choropleth map."""
    return trace.get("type") in _CHOROPLETH_TYPES
