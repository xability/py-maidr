from __future__ import annotations

import math
from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list, colorbar_title, subplot_block

#: What a map marker's own coordinates are called. A map draws no cartesian
#: axes, so there is no author-written title to read: `layout.xaxis` holds
#: another trace's, and the fallback `"X"`/`"Y"` would name a pair of degrees
#: after coordinates the chart does not have.
MAP_LONGITUDE_AXIS = "Longitude"
MAP_LATITUDE_AXIS = "Latitude"

#: What a density map's magnitude is called when the author titled no colour
#: bar. `Density` rather than `Value`, because that is what the trace weights
#: its kernel by and what the colour states.
MAP_DENSITY_AXIS = "Density"

#: The scatter-shaped map traces: a marker per position, and a name for it.
_PLACED_MARKS = frozenset({"scattergeo", "scattermap", "scattermapbox"})

#: The same shape carrying a magnitude per position.
_WEIGHTED_MARKS = frozenset({"densitymap", "densitymapbox"})

#: Which layout block field each family of map trace names its subplot under,
#: and what it belongs to when it names none. Measured on plotly 6.7.0: a
#: ``scattergeo`` writes ``geo``, while every ``*map`` and ``*mapbox`` trace
#: writes ``subplot`` -- and the two defaults differ, because a maplibre
#: figure's block is ``layout.map`` and a mapbox one's is ``layout.mapbox``.
_BLOCK_FIELDS: dict[str, tuple[str, str]] = {
    "geo": ("geo", "geo"),
    "mapbox": ("subplot", "mapbox"),
    "map": ("subplot", "map"),
}


def geo_block(trace: dict) -> str:
    """
    The layout block naming the map subplot a trace is drawn on.

    A map trace is placed by neither an axis pair nor a ``domain`` of its
    own, but by a rectangle plotly writes under a named block, which the
    trace addresses by name. Which field carries that name depends on the
    family: measured on plotly 6.7.0, ``go.Scattergeo(geo="geo2")`` writes
    ``geo``, while ``go.Scattermap(subplot="map2")`` writes ``subplot``.

    Parameters
    ----------
    trace : dict
        One trace of the figure.

    Returns
    -------
    str
        The block name, defaulted per family when the trace names none.
    """
    kind = str(trace.get("type", ""))
    if kind.endswith("mapbox"):
        field, default = _BLOCK_FIELDS["mapbox"]
    elif kind.endswith("map"):
        field, default = _BLOCK_FIELDS["map"]
    else:
        field, default = _BLOCK_FIELDS["geo"]
    return subplot_block(trace, field, default)


def is_geo_scatter_trace(trace: dict) -> bool:
    """
    Report whether a trace is a map's markers rather than its regions.

    Parameters
    ----------
    trace : dict
        One trace of the figure.

    Returns
    -------
    bool
        True for the scatter-shaped and density map traces.
    """
    kind = trace.get("type")
    return kind in _PLACED_MARKS or kind in _WEIGHTED_MARKS


def _degrees(value: Any) -> float | None:
    """
    One coordinate as a finite number of degrees, or ``None``.

    Parameters
    ----------
    value : Any
        A raw ``lat`` or ``lon`` entry.

    Returns
    -------
    float or None
        The coordinate, or ``None`` when it is missing or not finite.
    """
    if value is None or isinstance(value, str):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class PlotlyGeoScatterPlot(PlotlyPlot):
    """Extract data from a plotly map trace that draws markers.

    Five trace types draw the same chart: ``scattergeo`` on a geographic
    projection, ``scattermap``/``scattermapbox`` on a tiled base map, and
    ``densitymap``/``densitymapbox``, which add a magnitude per position.
    All five carry ``lat`` and ``lon`` in degrees, and none of them was read
    at all -- a figure whose only trace was one of them fell back to a
    picture (#683).

    **A scatter of degrees rather than a choropleth.** A marker has a
    position and, usually, a name, and that is the whole of its data.
    ``ChoroplethPoint.y`` is the value a region is shaded by and is
    required; a placed marker has none, and the only ways to give it one are
    to invent a constant or to promote its index, both of which announce a
    measurement the chart never made. Read as a scatter, every number
    announced is one the figure states, and the place name travels on
    ``ScatterPoint.label`` -- the field whose purpose is "this point is
    Oslo" rather than "this slot is called Oslo". The same reading the
    Highcharts adapter gives ``mappoint`` (xability/maidr#1187).

    A density trace's ``z`` is a real magnitude, so it travels on
    ``ScatterPoint.z``, which the core sounds through its intensity mapping.
    """

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.SCATTER, **kwargs)

    def _get_selector(self) -> str:
        """No selector, for the reason ``PlotlyChoroplethPlot`` gives.

        Plotly requests a geographic projection's land geometry, and a
        tiled map's tiles, from the network at render time, so what a map
        trace's markers are drawn as could not be measured here. Emitting a
        selector that has never resolved would be guessing, and a highlight
        that lands on the wrong marker is worse than none. The layer keeps
        its audio, braille and text; see #640.

        Returns
        -------
        str
            The empty string.
        """
        return ""

    def _extract_axes_data(self) -> dict:
        """Name the two coordinates, and the magnitude where there is one.

        A map draws no cartesian axes, so ``layout.xaxis`` holds neither
        name -- reading it would take another trace's titles. A density
        trace's colour bar title is the one thing the author may have
        written about its magnitude, so it is used when it is there.

        Returns
        -------
        dict
            The canonical per-axis payload.
        """
        axes = {
            MaidrKey.X: self._axis_config(label=MAP_LONGITUDE_AXIS),
            MaidrKey.Y: self._axis_config(label=MAP_LATITUDE_AXIS),
        }
        if self._trace.get("type") in _WEIGHTED_MARKS:
            axes[MaidrKey.Z] = self._axis_config(
                label=colorbar_title(self._trace) or MAP_DENSITY_AXIS
            )
        return axes

    def _extract_plot_data(self) -> list[dict]:
        """One point per marker the trace places.

        A marker whose position is not a finite pair of degrees is dropped
        rather than announced: plotly draws nothing for it, so announcing it
        would put a place on the map the reader cannot be told anything
        about -- and a non-finite coordinate is the ``NaN`` that stops the
        payload parsing at all (#427).

        Returns
        -------
        list of dict
            The samples, in the trace's own order.
        """
        lats = as_list(self._trace.get("lat"))
        lons = as_list(self._trace.get("lon"))
        names = as_list(self._trace.get("text"))
        weights = as_list(self._trace.get("z"))

        samples: list[dict] = []
        for position in range(min(len(lats), len(lons))):
            latitude = _degrees(lats[position])
            longitude = _degrees(lons[position])
            if latitude is None or longitude is None:
                continue

            sample = {MaidrKey.X: longitude, MaidrKey.Y: latitude}

            name = names[position] if position < len(names) else None
            if isinstance(name, str) and name.strip():
                sample[MaidrKey.LABEL] = name

            if position < len(weights):
                weight = _degrees(weights[position])
                if weight is not None:
                    sample[MaidrKey.Z] = weight

            samples.append(sample)

        return samples
