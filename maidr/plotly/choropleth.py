from __future__ import annotations

import math
from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.geo import geo_block
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

    Parameters
    ----------
    trace : dict
        One trace of the figure.
    layout : dict
        The figure's layout block.
    trace_position : int, default 0
        This trace's position among the choropleths drawn into its geo
        subplot's ``.choroplethlayer``, counted from zero. Only
        :class:`~maidr.plotly.plotly_maidr.PlotlyMaidr` knows it; the
        factory leaves it at its default.
    animated : bool, default False
        Whether the figure carries animation frames. A figure that does
        names no element; see :meth:`_get_selector`.
    **kwargs : str
        Axis names forwarded to the parent class.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        *,
        trace_position: int = 0,
        animated: bool = False,
        **kwargs: str,
    ) -> None:
        # A negative position builds ``nth-of-type(0)`` or lower, which
        # matches nothing and reports nothing -- the highlight simply never
        # appears. The same guard `PlotlyPiePlot` keeps over its own.
        if trace_position < 0:
            raise ValueError(f"trace position must be >= 0, got {trace_position}")

        super().__init__(trace, layout, PlotType.CHOROPLETH, **kwargs)
        self._trace_position = trace_position
        self._animated = animated
        self._block = geo_block(trace)

    def _get_selector(self) -> list[str]:
        """Address each shaded region by the path plotly draws for it.

        Measured in Chromium with the map loaded -- a ``go.Choropleth`` of
        eight countries declared out of alphabetical order gave eight
        ``path.choroplethlocation`` elements whose bound ``__data__.loc``
        read back in **declared** order. Plotly sorts nothing here, unlike
        the parcats ribbons of #639, so the element a region is drawn as is
        computable offline from the trace's own arrays. That is what #640
        was waiting on.

        ## One selector per region, keyed on the declared index

        ``ChoroplethTrace.mapToSvgElements`` resolves every selector, counts
        the elements, and withdraws the layer's highlight entirely when the
        total is not the point count. Measured, plotly draws one path per
        **declared** ``(location, z)`` pair -- including the pairs it can
        draw nothing for. A region with no value keeps its slot with no
        ``d`` attribute, and so does one whose name plotly cannot resolve at
        all (measured: ``"ZZZ"`` keeps ``loc``, ``z`` and its fill, and has
        no geometry).

        So a single selector matching every path would resolve more elements
        than `_extract_plot_data` announces on any map with a hole -- and a
        hole is ordinary, a value the source had nothing for is still a row
        -- which costs the layer its highlight altogether. Each surviving
        region names its own path instead, at the index it was *declared*
        at rather than the index it was announced at. A dropped region does
        not shift the ones after it.

        A region plotly could not resolve still gets a selector, and it
        resolves to that zero-area placeholder: a highlight that shows
        nothing, never one that outlines the wrong country.

        ## Scoped to this trace, on this map

        ``g.trace.choropleth:nth-of-type(n)`` counts among the choropleths
        drawn into **this geo subplot's** ``.choroplethlayer``, which is not
        the trace's position in the figure: a ``scattergeo`` on the same map
        draws into the sibling ``.scatterlayer`` and takes no slot here
        (measured -- a choropleth declared after one is still
        ``nth-of-type(1)``).

        The subplot is named by its exact class attribute rather than by a
        class token, which is the one place a geo subplot differs from the
        polar one #635 scoped. Plotly writes ``class="geo " + id``, so the
        *first* subplot's attribute is the doubled string ``"geo geo"`` and
        its token list is the single token ``geo`` -- which every other geo
        subplot carries too. Measured on a two-map figure,
        ``.geolayer > g.geo.geo`` matched **both** maps and on a three-map
        figure all **three**; the exact-attribute form matched exactly one
        on each, and on ``geo2`` and ``geo10`` alike.

        ## Not while the map is moving

        A figure built with ``animation_frame=`` names nothing. Its frames
        are in ``figure.frames``, which is not read here -- the payload is
        the base trace, plotly's *first* frame -- and plotly.js advances the
        drawing to the **last** frame within about half a second of load,
        with no interaction. Measured on a two-frame `px.choropleth` whose
        frames name the same four countries in opposite orders: the payload
        announces ``USA, CAN, MEX, BRA`` while the four paths are bound to
        ``BRA, MEX, CAN, USA``. Four selectors resolve four elements, so the
        count agrees and the highlight stays live -- pointing at the wrong
        country every step of the walk, which is the outcome this whole
        method is written to avoid.

        The stale *reading* is older than this and not a choropleth's alone;
        nothing under ``maidr/plotly/`` reads ``frames`` for any trace. What
        is declined here is only the confident highlight laid over it.

        Returns
        -------
        list of str
            One selector per announced region, in the order they are
            announced. Empty when the layer names nothing.
        """
        if not draws_svg_regions(self._trace) or self._animated:
            return []

        group = (
            f".geolayer > g[class='geo {self._block}'] > g.backplot "
            f"> g.choroplethlayer "
            f"> g.trace.choropleth:nth-of-type({self._trace_position + 1})"
        )
        return [
            f"{group} > path.choroplethlocation:nth-of-type({index + 1})"
            for index, _, _ in self._shaded_regions()
        ]

    def _extract_axes_data(self) -> dict:
        """Name the region and the value it is shaded by.

        A choropleth draws no cartesian axes, so ``layout.xaxis`` holds
        neither name -- reading it would take another trace's titles. The
        color bar's title is the one thing the author may have written about
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
        return [
            {
                MaidrKey.X: str(self._to_native(location)),
                MaidrKey.Y: self._to_native(value),
            }
            for _, location, value in self._shaded_regions()
        ]

    def _shaded_regions(self) -> list[tuple[int, Any, Any]]:
        """The regions that are read, each with the index it was declared at.

        The index is what the selector is built on and the pair is what the
        payload is built on, so they are taken together: reading them apart
        is how a dropped region comes to shift the highlight of every region
        after it.

        Returns
        -------
        list of tuple
            ``(declared index, location, value)`` per region carrying a
            value, in the trace's own order.
        """
        locations = as_list(self._trace.get("locations"))
        values = as_list(self._trace.get("z"))

        return [
            (index, location, value)
            for index, (location, value) in enumerate(zip(locations, values))
            if _carries_a_value(value)
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


def draws_svg_regions(trace: dict) -> bool:
    """Report whether a choropleth draws a region a selector can name.

    The three spellings read identically and do not draw identically. Only
    the geographic projection puts its regions in the SVG; the tiled pair
    hands them to a GL base map. Measured in Chromium on a fully painted
    ``go.Choroplethmap`` with ``style="white-bg"``, so no tile server was
    needed: four ``<canvas>`` elements, an empty ``<g class="geolayer">``,
    and **zero** ``path`` elements anywhere on the page carrying a class
    other than the modebar's. The regions are genuinely there --
    ``queryRenderedFeatures`` returned both of them with their fills -- but
    not as anything CSS can address. ``go.Choroplethmapbox`` measured the
    same, under ``.mapboxgl-canvas`` instead.

    So the tiled pair keeps the #145 outcome the whole family had until now:
    audio, braille and text, and no highlight. That is the ``scattergl``
    conclusion of #668 rather than the "not measured yet" of #640.

    Parameters
    ----------
    trace : dict
        One trace of the figure.

    Returns
    -------
    bool
        True for the geographic projection, false for the tiled pair.
    """
    return trace.get("type") == "choropleth"


def _carries_a_value(value: Any) -> bool:
    """Report whether a region's ``z`` entry is a number to announce.

    ``None`` is the obvious case and ``NaN`` is the ordinary one: plotly's
    validators coerce a missing entry to ``NaN`` rather than keeping it, so
    a dataframe column with a gap -- ``pd.Series([1.0, None, 3.0])`` -- never
    reaches a ``is not None`` test at all. Plotly treats the two the same
    (both serialize to ``null`` and draw a region with no geometry), and so
    does this: a `NaN` announced as a value is a region the reader cannot be
    told anything about, and it is also the token that stops the payload
    parsing as JSON at all, which is what #427 named for a coordinate.

    Parameters
    ----------
    value : Any
        One raw ``z`` entry.

    Returns
    -------
    bool
        True when the region is shaded by a number.
    """
    if value is None:
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def enters_the_region_layer(trace: dict) -> bool:
    """Report whether plotly gives this trace a group in ``.choroplethlayer``.

    A choropleth's selector counts its position among the groups plotly
    appends there, so a trace that is *drawn* but appends no group must not
    take a slot -- every later choropleth on that map would be numbered one
    past its own element and resolve nothing, which withdraws its highlight
    outright.

    Measured in Chromium: plotly writes a ``g.trace.choropleth`` exactly when
    the trace has at least one declared ``(location, z)`` pair, and nothing
    at all when it has none. A per-group loop where one group matched no rows
    is the ordinary way to get one. The boundary is the *declared* pair and
    not the announced point: ``locations=["USA"], z=[None]`` announces
    nothing yet still draws a group holding one geometry-less path, so it
    does take a slot.

    Parameters
    ----------
    trace : dict
        One trace of the figure.

    Returns
    -------
    bool
        True when plotly draws a group for this trace.
    """
    if not draws_svg_regions(trace):
        return False
    locations = as_list(trace.get("locations"))
    values = as_list(trace.get("z"))
    return min(len(locations), len(values)) > 0
