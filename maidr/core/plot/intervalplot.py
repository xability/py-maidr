"""Read a band or a range of bars as the interval it draws."""

from __future__ import annotations

import uuid
from typing import Any, List, Sequence

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.core.plot.scatterplot import _rgba
from maidr.exception import ExtractionError
from maidr.util.legend_names import names_for
from maidr.util.mixin import DictMergerMixin

#: The keyword the drawn artists are handed over under.
DRAWN_INTERVALS = "intervals"


class IntervalPlot(MaidrPlot, DictMergerMixin):
    """
    An interval per position, drawn either as a band or as a bar each.

    ``so.Band`` and ``so.Range`` are the same reading from two drawings, which
    is why one class serves both. Measured on ``seaborn 0.13.2`` over three
    positions::

        so.Band()   one Polygon         verts lower forward, upper backward
        so.Range()  one LineCollection  one segment per position

    Both carry **bounds and no estimate**, and that is not a gap to be filled
    in: neither mark draws a centre of its own, and
    :class:`~maidr.core.enum.PlotType.ERRORBAR`'s point shape declares its
    estimate optional for exactly this -- "absent on a band that draws only
    bounds". A chart wanting the estimate too adds ``so.Dot(), so.Agg()``
    beside it, which registers as its own layer and is read as one.

    Orientation is read from the drawing rather than from the caller's
    spelling. The two bounds at one position share the coordinate the
    position is on, so whichever of the pair matches is the position axis --
    true of a polygon's paired vertices and of a segment's two endpoints
    alike, and true whether the caller wrote ``orient="y"`` or not.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.ERRORBAR)

        self._intervals: list = list(kwargs.pop(DRAWN_INTERVALS, None) or [])

        # One per interval, filled by `_bounds` because the name belongs to
        # the artist an interval was read off; pairing them afterwards would
        # mean reconstructing which artist that was.
        self._names: list = []

        # Resolved from the drawing during extraction, which `render` runs
        # before it reads this.
        self._orientation = "vert"

    def render(self) -> dict:
        """
        Build the layer schema, adding the orientation the intervals run in.

        Returns
        -------
        dict
            The MAIDR layer schema.
        """
        # `super().render()` runs `_extract_plot_data`, which is what resolves
        # `self._orientation` -- so the read below has to come after it.
        base_schema = super().render()
        return self.merge_dict(base_schema, {MaidrKey.ORIENTATION: self._orientation})

    def _extract_axes_data(self) -> dict:
        """
        Extend the base per-axis mapping with the legend title as ``z``.

        A colour split names each series by the level it belongs to, so the
        dimension itself needs a name for those levels to be announced
        against. Omitted when there is no legend, which is every chart drawn
        without a split.
        """
        axes_data = super()._extract_axes_data()

        label = self._legend_title()
        if label:
            axes_data[MaidrKey.Z] = self._axis_config(label=label)

        return axes_data

    def _extract_plot_data(self) -> list:
        bounds = self._bounds()
        if not bounds:
            raise ExtractionError(self.type, self.ax)

        self._orientation = "vert" if self._vertical(bounds) else "horz"
        # The position runs along the axis the interval does NOT span, and the
        # magnitude along the one it does. The schema names the magnitude
        # `y`/`yMin`/`yMax` in BOTH orientations and lets `orientation` say
        # which is on screen where -- the convention `ErrorBarPlot` documents,
        # and one `ErrorBarTrace` depends on: `ErrorBarPoint` declares no
        # `xMin`/`xMax` to put a bound in, so a screen-aligned payload would
        # leave a horizontal chart with no interval at all.
        component = 1 if self._orientation == "vert" else 0
        other = 1 - component

        points = []
        for index, (position, low, high) in enumerate(bounds):
            # Ordered rather than taken as they came. Both drawings happen
            # to give the lower bound first -- a band's fold runs the lower
            # edge forward, and a range's segment starts at its foot -- so
            # neither mark reaches the swap today. The fields mean the
            # smaller and the larger, though, and a reader handed a `yMin`
            # above its `yMax` would be told the interval runs backwards.
            point = {
                MaidrKey.X: _plain(position[other]),
                MaidrKey.Y_MIN: _plain(min(low[component], high[component])),
                MaidrKey.Y_MAX: _plain(max(low[component], high[component])),
            }
            name = self._names[index] if index < len(self._names) else None
            if name:
                point[MaidrKey.Z] = name
            points.append(point)

        return self._grouped(points)

    def _grouped(self, points: list[dict]) -> list:
        """
        One series per level, or the flat list when nothing named them.

        The grouped shape is what ``ErrorBarPoint[][]`` was added for (#942):
        it is what lets a reader move between two levels' intervals at one
        position, which is the comparison a grouped interval chart exists to
        support. A chart with no split has one group and needs no name for it,
        so it stays flat rather than becoming a list of one.

        Parameters
        ----------
        points : list of dict
            Every interval, in drawing order.

        Returns
        -------
        list
            ``ErrorBarPoint[]`` or ``ErrorBarPoint[][]``.
        """
        if not any(point.get(MaidrKey.Z) for point in points):
            return points

        series: dict[Any, list[dict]] = {}
        for point in points:
            series.setdefault(point.get(MaidrKey.Z), []).append(point)
        return list(series.values())

    def _get_selector(self) -> List[str]:
        """
        One selector per interval, addressing its own path inside the group.

        The inherited default is ``g[maidr='true'] > path``, which resolves to
        nothing: `maidr.patch.highlight` tags a drawn artist by giving it a
        ``maidr-`` **gid**, not a ``maidr`` attribute, so a class that leaves
        the default emits a selector matching no element in the document. That
        is worse than emitting none -- the layer says its intervals can be
        outlined and none of them can.

        A range's collection draws one path per segment as direct children of
        one group, so an interval is addressed by its position within that
        group. This is only reached where every interval is one of that
        collection's paths, in drawing order: :meth:`_bounds` clears the
        elements and turns highlighting off for a band, which has no path per
        interval, and for a split range, whose paths run in drawing order
        while the payload is grouped by level.

        Returns
        -------
        list of str
            One selector per interval, in the order the payload announces them.
        """
        collection = self._elements[0]
        gid = collection.get_gid()
        if not gid or not str(gid).startswith("maidr-"):
            gid = f"maidr-{uuid.uuid4()}"
            collection.set_gid(gid)

        return [
            f"g[id='{gid}'] > path:nth-of-type({position + 1})"
            for position in range(len(collection.get_segments()))
        ]

    def _bounds(self) -> list[tuple]:
        """
        Every interval as ``(position, lower, upper)`` points, in draw order.

        Also fills ``self._names``, one per interval.

        Returns
        -------
        list of tuple
            One entry per drawn interval.
        """
        self._names = []
        found: list[tuple] = []

        polygons = [art for art in self._intervals if isinstance(art, Polygon)]
        collections = [art for art in self._intervals if isinstance(art, LineCollection)]

        if polygons:
            named = names_for(self.ax, [_face_of(poly) for poly in polygons])
            for poly, name in zip(polygons, named):
                pairs = _folded(np.asarray(poly.get_path().vertices, dtype=float))
                found.extend(pairs)
                self._names.extend([name] * len(pairs))
            # A band spans every position with one path, so there is no
            # element per interval for a selector to resolve to. Announcing
            # one would promise highlightable paths the document does not
            # contain -- the same reason `ErrorBarPlot` clears the flag for a
            # call that drew no bars.
            self._support_highlighting = False

        for collection in collections:
            segments = [np.asarray(seg, dtype=float) for seg in collection.get_segments()]
            named = names_for(self.ax, _segment_colours(collection, len(segments)))
            for segment, name in zip(segments, named):
                if len(segment) < 2:
                    continue
                found.append((segment[0], segment[0], segment[-1]))
                self._names.append(name)
            self._elements.append(collection)

        # A split range's paths are one collection's, in drawing order, while
        # the payload is grouped by level -- so a positional selector would
        # pair the second level's first interval with the first level's. The
        # grouped selector shape is a question of its own, and outlining the
        # wrong interval is worse than outlining none (#814).
        if collections and any(self._names):
            self._elements.clear()
            self._support_highlighting = False

        return found

    @staticmethod
    def _vertical(bounds: Sequence[tuple]) -> bool:
        """
        Whether the intervals run up the page.

        The two bounds at one position share the coordinate that position is
        on. Read off the first interval that has a spread to read: a
        degenerate one shares *both*, so it says nothing, and taking it would
        answer from a chart's flattest point.

        Parameters
        ----------
        bounds : sequence of tuple
            Every interval as ``(position, lower, upper)``.

        Returns
        -------
        bool
            True for an interval spanning ``y``.
        """
        for _, low, high in bounds:
            if low[0] != high[0]:
                return False
            if low[1] != high[1]:
                return True
        # Every interval is a point. Nothing distinguishes the axes, and
        # vertical is what `ErrorBarPlot` also answers when its container
        # carries no error at all.
        return True


def _folded(vertices: np.ndarray) -> list[tuple]:
    """
    A band polygon's vertices as one ``(position, lower, upper)`` per position.

    Measured, the path is the lower edge forward then the upper edge
    backward, closed by repeating the first vertex::

        [[0,0.71], [1,1.78], [2,2.26], [2,2.75], [1,2.15], [0,1.19], [0,0.71]]
         └──── lower, n ────┘ └──── upper, n, reversed ───┘ └─ close ─┘

    so position ``i``'s bounds are ``verts[i]`` and ``verts[2n - 1 - i]``.

    Parameters
    ----------
    vertices : numpy.ndarray
        The polygon's path vertices.

    Returns
    -------
    list of tuple
        One entry per position, or empty when the path does not fold.
    """
    points = vertices
    if len(points) > 1 and np.allclose(points[0], points[-1]):
        points = points[:-1]

    count = len(points) // 2
    if count == 0 or len(points) != count * 2:
        return []

    return [(points[i], points[i], points[len(points) - 1 - i]) for i in range(count)]


def _face_of(poly: Polygon):
    """
    One band's fill colour, as the rounded RGBA the legend is matched on.

    Parameters
    ----------
    poly : matplotlib.patches.Polygon
        The band.

    Returns
    -------
    tuple of float or None
        The rounded RGBA, or ``None`` when the patch names no single colour.
    """
    face = np.asarray(poly.get_facecolor(), dtype=float).ravel()
    return _rgba(face[:4]) if len(face) >= 4 else None


def _segment_colours(collection: LineCollection, count: int) -> list:
    """
    One rounded RGBA per drawn segment.

    Cycled rather than indexed, for the reason ``SegmentLinePlot`` cycles its
    own: ``get_colors()`` returns exactly what was set, which for a chart
    drawn without a split is one colour over every segment.

    Parameters
    ----------
    collection : matplotlib.collections.LineCollection
        The drawn segments.
    count : int
        How many segments there are.

    Returns
    -------
    list
        One rounded RGBA per segment, or ``None`` where there is no colour.
    """
    colours = np.asarray(collection.get_colors(), dtype=float)
    if colours.ndim == 1:
        colours = colours.reshape(1, -1)
    if len(colours) == 0:
        return [None] * count
    return [_rgba(colours[index % len(colours)][:4]) for index in range(count)]


def _plain(value) -> Any:
    """
    A numpy scalar as the plain Python number ``json.dumps`` can write.

    Parameters
    ----------
    value : Any
        One coordinate.

    Returns
    -------
    Any
        The plain value.
    """
    return value.item() if hasattr(value, "item") else value
