from __future__ import annotations

import re
import uuid
from typing import Any, Sequence

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import Collection
from matplotlib.path import Path

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.plot.lineplot import _X, _Y, _Z, _has_position, _reading
from maidr.exception import ExtractionError

#: One command letter or one number of the path data matplotlib writes.
_PATH_TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

#: The attribute a ``<use>`` names its template by. matplotlib writes the
#: XLink spelling.
_HREF = "{http://www.w3.org/1999/xlink}href"


class AreaPlot(MaidrPlot):
    """
    A chart drawing one or more filled bands against a baseline.

    Reads ``Axes.stackplot`` and the single-bound form of ``Axes.fill_between``.

    Emitted as an area layer rather than a line one because a stacked area
    draws **two** numbers at each point that a line would conflate: the band's
    height is the series' own value, and its top edge is the running total. A
    line layer announces one number per point with nothing to say which of the
    two it is; the area trace announces the value and reports the total beside
    it.

    The values come from the **caller's arguments** rather than from the drawn
    polygons, which is the one place this differs from the rest of this package
    -- ``ErrorBarPlot`` and ``PointPlot`` both read geometry precisely because
    the arguments they were given are not the quantity the schema carries.
    Here it is the other way round: ``stackplot`` is handed each series' own
    values and does the accumulation itself, so the arguments are exactly what
    the consumer needs, while the drawn polygon is a closed outline whose
    vertices run forward along the baseline and back along the top with the
    endpoints repeated. Recovering per-series values from that means undoing
    both the accumulation and the closure, to arrive back at what the caller
    passed in.

    Parameters
    ----------
    ax : Axes
        The axes the bands were drawn on.
    **kwargs
        ``x`` is the shared position array, ``series`` the per-series values in
        drawing order, ``labels`` their names when the caller supplied any, and
        ``collections`` the drawn artists. The patch resolves all four.
        ``samples_on_second_bound`` says which bound of each band's
        ``fill_between`` polygon its samples lie on -- see
        :meth:`finish_svg`.

    See Also
    --------
    MaidrPlot : The base class for MAIDR plot data objects.
    """

    def __init__(self, ax: Axes, plot_type: PlotType, **kwargs) -> None:
        super().__init__(ax, plot_type)

        self._x = kwargs.pop("x", None)
        self._series = list(kwargs.pop("series", []))
        self._labels = list(kwargs.pop("labels", []))
        self._collections = list(kwargs.pop("collections", []))
        # `fill_betweenx` draws the same band with the axes exchanged: the
        # positions run down the page and the magnitudes out along x. The
        # numbers still go into the fields the trace reads them from -- see
        # `render` for why the titles move instead of the data.
        self._transposed = bool(kwargs.pop("transposed", False))
        # `fill_between(x, y1, y2)` draws its band out along `y1` and back
        # along `y2`. A `fill_between(x, y1)` area has its samples on `y1`;
        # `stackplot` draws band i as `fill_between(x, stack[i-1], stack[i])`,
        # so its samples -- the band's top, the running total -- are on the
        # second bound. Only `finish_svg` reads this.
        self._samples_on_second_bound = bool(
            kwargs.pop("samples_on_second_bound", False)
        )

    def render(self) -> dict:
        """
        Build the layer, exchanging the two axis titles for a sideways band.

        `fill_betweenx(y, x1)` fills between the vertical positions `y` and
        the horizontal curve `x1`, so its positions belong to the y axis and
        its magnitudes to the x axis -- the mirror of every other chart this
        class reads. Emitted unchanged, the two spellings produced byte-
        identical payloads for charts that are transposes of each other, and
        every number was announced under the other axis' title (#566).

        The **titles** move rather than the data, which is deliberate twice
        over:

        - the core sonifies an area trace's `y` and steps along its `x`, so
          putting the positions in `y` would pitch `[1, 2, 3, 4]` -- a rising
          ramp on every sideways band ever drawn, whatever the data says;
        - `orientation` is the field that says a chart is drawn sideways, and
          `src/util/orientation.ts` marks `AREA` as not oriented on purpose,
          so emitting one would be a promise the core does not keep.

        The same exchange, for the same reason, is what the core's Vega-Lite
        adapter does to a horizontal waterfall.

        What it does not fix is navigation: left and right still walk the
        trace's `x`, which for a sideways band is the vertical axis. That is
        what `orientation` would carry, and it cannot be said for an area
        trace today.

        Returns
        -------
        dict
            The layer, with `axes.x` and `axes.y` exchanged when the band was
            drawn sideways.
        """
        maidr_schema = super().render()

        if not self._transposed:
            return maidr_schema

        # After `super().render()` rather than in `_extract_axes_data`,
        # because the format config is merged into each `AxisConfig` there: a
        # currency formatter set on the x axis describes the horizontal
        # numbers, which are the ones this moves.
        axes = maidr_schema.get(MaidrKey.AXES)
        if isinstance(axes, dict) and MaidrKey.X in axes and MaidrKey.Y in axes:
            axes[MaidrKey.X], axes[MaidrKey.Y] = axes[MaidrKey.Y], axes[MaidrKey.X]

        return maidr_schema

    def _extract_plot_data(self) -> list[list[dict]]:
        if self._x is None or not self._series:
            raise ExtractionError(self.type, self.ax)

        positions = np.atleast_1d(np.asarray(self._x, dtype=object))

        # Cleared rather than appended to: a layer is rendered more than once,
        # and the tagged elements have to stay one per series, in series order.
        self._elements.clear()

        # Plain numbers, which is nearly every area chart, are read in bulk:
        # the same points, keyed by the plain strings for the reason
        # `lineplot._X` gives. The positions are shared by every series, so
        # they are converted once here. Anything else takes the per-point
        # reading below, unchanged.
        xs, placed = self._numeric_positions(positions)

        data: list[list[dict]] = []
        for index, values in enumerate(self._series):
            magnitudes = np.atleast_1d(np.asarray(values))
            if len(magnitudes) != len(positions):
                raise ExtractionError(self.type, self.ax)

            label = self._labels[index] if index < len(self._labels) else None

            readings = (
                self._numeric_readings(magnitudes, placed) if xs is not None else None
            )
            if readings is not None:
                if label:
                    name = str(label)
                    points = [{_X: x, _Y: y, _Z: name} for x, y in zip(xs, readings)]
                else:
                    points = [{_X: x, _Y: y} for x, y in zip(xs, readings)]
                data.append(points)
                self._tag(index)
                continue

            points = []
            for position, magnitude in zip(positions, magnitudes):
                # The line layer's two rules, for the reason it gives: a
                # sample with no *position* is nowhere a reader could be
                # sent and is dropped -- from every series, since the
                # positions are shared, so the columns the consumer sums
                # stay aligned -- while one with a position and no *value*
                # is kept and emitted as `null`, which the core's area trace
                # reads as a gap that stays out of the running total. Either
                # written out as a bare `NaN` stops the chart initializing
                # (#427).
                x = self._scalar(position)
                if not _has_position(x):
                    continue
                point = {MaidrKey.X: x, MaidrKey.Y: _reading(self._scalar(magnitude))}
                if label:
                    point[MaidrKey.Z] = str(label)
                points.append(point)

            data.append(points)
            self._tag(index)

        if len(self._elements) != len(data):
            # The consumer resolves the selector to one element per series and
            # discards the result outright when the count disagrees, so a
            # partial list would emit a selector that silently highlights
            # nothing. Saying so is better than promising it.
            self._elements.clear()
            self._support_highlighting = False

        return data

    def _tag(self, index: int) -> None:
        """
        Tag the band drawn for one series, when the call handed it over.

        Parameters
        ----------
        index : int
            The series' place in drawing order.
        """
        if index < len(self._collections):
            collection = self._collections[index]
            # Assigned here rather than relied upon: a gid is otherwise
            # only stamped at draw time, and the schema is built first.
            # `MultiLinePlot` does the same for the same reason.
            if collection.get_gid() is None:
                collection.set_gid(f"maidr-{uuid.uuid4()}")
            self._elements.append(collection)

    @staticmethod
    def _numeric_positions(
        positions: np.ndarray,
    ) -> tuple[list | None, np.ndarray | None]:
        """
        The positions as :meth:`_scalar` converts them, read in bulk.

        Parameters
        ----------
        positions : ndarray
            The shared positions, as the object array extraction holds them.

        Returns
        -------
        tuple
            ``(xs, placed)``: the positions :func:`_has_position` keeps, as
            floats, and the mask that keeps them -- or ``(None, None)`` when
            a position is anything but a plain ``float`` or ``int``, which
            leaves them all to the per-point reading.
        """
        items = positions.tolist()
        # Exactly these two types -- not `bool`, not a NumPy scalar, not a
        # string that `float()` would parse -- so the conversion below is the
        # one `_scalar` makes, and everything else keeps the per-point path.
        if not set(map(type, items)) <= {float, int}:
            return None, None
        # `_scalar` of a float or an int is `float()` of it, and
        # `_has_position` of a float is `isfinite`.
        values = [float(item) for item in items]
        placed = np.isfinite(np.asarray(values, dtype=float))
        if placed.all():
            return values, placed
        return [value for value, kept in zip(values, placed.tolist()) if kept], placed

    @staticmethod
    def _numeric_readings(magnitudes: np.ndarray, placed: np.ndarray) -> list | None:
        """
        One series' values at the kept positions, read in bulk.

        Parameters
        ----------
        magnitudes : ndarray
            The series' values, one per position.
        placed : ndarray
            The kept positions, from :meth:`_numeric_positions`.

        Returns
        -------
        list or None
            What ``_reading(_scalar(value))`` gives each kept value -- the
            float, or ``None`` for a non-finite one -- or ``None`` when the
            values are not plain numbers.
        """
        if magnitudes.ndim != 1 or magnitudes.dtype.kind not in "fiu":
            return None
        # `float()` of a NumPy scalar is the same C conversion `astype` makes.
        kept = magnitudes[placed].astype(float)
        readings = kept.tolist()
        measured = np.isfinite(kept)
        if not measured.all():
            for index in np.flatnonzero(~measured).tolist():
                readings[index] = None
        return readings

    def _get_selector(self) -> list[str]:
        """
        Return one selector per drawn band, in series order.

        Parameters
        ----------
        None

        Only reached when every series was tagged: extraction clears the flag
        otherwise, so this never has to describe a partial list.

        The band's own ``<path>``, a child of its group. The descendant form
        this was, ``g[id=...] path``, also matched a template matplotlib
        writes into the group's ``<defs>`` -- for a band with an edge colour
        the only ``<path>`` there, which draws nothing; see
        :meth:`finish_svg`, which leaves every band drawn as that child.

        Returns
        -------
        list of str
            One selector per band.
        """
        return [f"g[id='{element.get_gid()}'] > path" for element in self._elements]

    def finish_svg(self, tree: Any) -> None:
        """
        Write each band as one path that starts along its samples.

        maidr.js reads an area series from the vertices of the ``<path>`` its
        selector names: the samples first, from the first position on, and
        then the way back, which it drops. matplotlib writes a band neither
        way.

        A band with an edge colour -- a seaborn theme's white edge, an Excel
        chart's, any ``edgecolor=`` -- is drawn through matplotlib's
        single-path shortcut, ``draw_markers``: the polygon goes into the
        group's ``<defs>``, offset by the height of the figure, and a
        ``<use>`` draws it. The only ``<path>`` in the group was that
        template, so the selector named it, maidr.js put its markers beside
        it inside ``<defs>``, and the reader got no highlight at all: the
        marker never drew, at 0,0 (py-gallery-files#1).

        A band drawn as a plain ``<path>`` was read from the wrong vertices.
        ``fill_between`` starts its polygon at a corner on its second bound,
        walks the first bound out and the second back. A ``stackplot`` band's
        samples, its top, are on that second bound, so the highlight walked
        its lower edge instead; a ``fill_between(x, y)`` area's are on the
        first, one vertex in, so every highlight sat one sample behind the
        announced one, the first on the baseline.

        So each band whose polygon is that construction, one vertex per
        position on each bound, is rewritten as one plain ``<path>``: the
        same vertices and the same style, starting at the first sample and
        running along the samples first. The shape drawn does not change --
        a closed polygon starting elsewhere, or run the other way round, fills
        and strokes the same -- and a band that is anything else is left as
        matplotlib wrote it.

        Parameters
        ----------
        tree : lxml.etree._Element
            The rendered SVG, modified in place.
        """
        for band in self._elements:
            order = self._sample_order(band)
            if order is not None:
                _rewrite_band(tree, str(band.get_gid()), order)

    def _sample_order(self, band: Any) -> list[int] | None:
        """
        The order to visit a band's vertices in to walk its samples first.

        Worked out on the band's own path, whose vertices matplotlib writes
        one for one, the closing one as ``z``. ``fill_between`` builds it as
        ``[c0, A_0 .. A_n-1, c1, B_n-1 .. B_0]``: ``A`` the first bound, ``B``
        the second, and the corners ``c0 = B_0`` and ``c1 = B_n-1``. Read
        only when every one of those holds and both bounds sit at this
        layer's positions, one vertex each.

        Parameters
        ----------
        band : Any
            One of the layer's drawn artists.

        Returns
        -------
        list of int or None
            The vertex indices in the order to write them, or ``None`` when
            the band is not a polygon of that shape.
        """
        if not isinstance(band, Collection):
            return None
        paths = band.get_paths()
        if len(paths) != 1 or paths[0].codes is None:
            return None
        codes = paths[0].codes
        if (
            codes[0] != Path.MOVETO
            or codes[-1] != Path.CLOSEPOLY
            or np.any(codes[1:-1] != Path.LINETO)
        ):
            return None
        # The closing vertex is written as `z`, not as a point.
        points = np.asarray(paths[0].vertices, dtype=float)[:-1]
        count = len(points)
        n, odd = divmod(count - 2, 2)
        if odd or n < 2:
            return None

        convert = self.ax.convert_yunits if self._transposed else self.ax.convert_xunits
        try:
            positions = np.asarray(convert(self._x), dtype=float)
        except (TypeError, ValueError):
            return None
        axis = 1 if self._transposed else 0
        out = points[1 : n + 1, axis]
        back = points[count - 1 : n + 1 : -1, axis]
        if not (
            positions.shape == (n,)
            and np.array_equal(points[0], points[count - 1])
            and np.array_equal(points[n + 1], points[n + 2])
            and np.array_equal(out, positions)
            and np.array_equal(back, positions)
        ):
            return None

        if self._samples_on_second_bound:
            # B_0 .. B_n-1, c1, A_n-1 .. A_0, c0: the whole polygon backwards.
            return list(range(count - 1, -1, -1))
        # A_0 .. A_n-1, c1, B_n-1 .. B_0, c0: the corner moved to the end.
        return [*range(1, count), 0]

    @staticmethod
    def _scalar(value: Any) -> Any:
        """
        Convert one coordinate to a JSON-serializable scalar.

        Parameters
        ----------
        value : Any
            A coordinate read off the caller's arguments.

        Returns
        -------
        Any
            A float, or a string for a coordinate that is not numeric.
        """
        if isinstance(value, (str, np.str_)):
            return str(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def resolve_type(series: Sequence) -> PlotType:
        """
        Decide which area layer a call produced.

        A single band has nothing stacked on it, so announcing a running total
        equal to its own value at every point would be noise -- it is a plain
        area. Several bands stack, and the two numbers a stack draws are what
        the dedicated type keeps apart.

        The count is the whole rule. ``baseline`` looks like it should matter
        and does not: ``sym`` and ``wiggle`` move where the stack sits on the
        value axis without changing what any band measures, so a streamgraph
        is a stacked area drawn around a floating center and reads as one.

        Parameters
        ----------
        series : sequence
            The per-series value arrays.

        Returns
        -------
        PlotType
            The layer type to emit.
        """
        return PlotType.STACKED_AREA if len(series) > 1 else PlotType.AREA


def _rewrite_band(tree: Any, gid: str, order: list[int]) -> None:
    """
    Write one band as a single ``<path>``, its vertices in ``order``.

    matplotlib writes the band's group in one of two forms. A plain ``<path>``
    child gets its ``d`` rewritten. A ``<use>`` of a template is replaced by
    the ``<path>`` it draws -- the template's vertices moved by the use's
    offset, the use's style, the clip of the ``<g>`` it sat in -- in the
    place of that ``<g>``, so the band's group reads as matplotlib's plain
    form does; the template goes once nothing else uses it. Anything else is
    left as it was.

    Parameters
    ----------
    tree : lxml.etree._Element
        The rendered SVG, modified in place.
    gid : str
        The band's gid, which matplotlib writes as its group's ``id``.
    order : list of int
        The band's vertex indices, in the order to write them.
    """
    groups = tree.xpath("//*[local-name()='g'][@id=$gid]", gid=gid)
    if len(groups) != 1:
        # A gid two artists share (#753), or a band that drew nothing.
        return
    group = groups[0]
    children = [child for child in group if isinstance(child.tag, str)]

    paths = [child for child in children if _local_name(child) == "path"]
    if paths:
        vertices = _polygon(paths[0].get("d", "")) if len(paths) == 1 else None
        if vertices is not None and len(vertices) == len(order):
            paths[0].set("d", _polygon_data([vertices[i] for i in order]))
        return

    wrappers = [child for child in children if _local_name(child) == "g"]
    if len(wrappers) != 1:
        return
    wrapper = wrappers[0]
    inside = [child for child in wrapper if isinstance(child.tag, str)]
    if len(inside) != 1 or _local_name(inside[0]) != "use":
        return
    use = inside[0]
    reference = use.get(_HREF) or use.get("href") or ""
    templates = (
        tree.xpath("//*[local-name()='path'][@id=$id]", id=reference[1:])
        if reference.startswith("#")
        else []
    )
    if len(templates) != 1:
        return
    vertices = _polygon(templates[0].get("d", ""))
    try:
        dx, dy = float(use.get("x", 0)), float(use.get("y", 0))
    except ValueError:
        return
    if vertices is None or len(vertices) != len(order):
        return

    path = group.makeelement(templates[0].tag, {})
    moved = [(vertices[i][0] + dx, vertices[i][1] + dy) for i in order]
    path.set("d", _polygon_data(moved))
    if wrapper.get("clip-path") is not None:
        path.set("clip-path", wrapper.get("clip-path"))
    if use.get("style") is not None:
        path.set("style", use.get("style"))
    path.tail = wrapper.tail
    wrapper.addprevious(path)
    group.remove(wrapper)

    # matplotlib writes one template for every collection drawn with the same
    # shape and style, so another band may still use this one.
    used = tree.xpath(
        "//*[local-name()='use'][@*[local-name()='href']=$ref]", ref=reference
    )
    if not used:
        template = templates[0]
        holder = template.getparent()
        holder.remove(template)
        if _local_name(holder) == "defs" and len(holder) == 0:
            holder.getparent().remove(holder)


def _local_name(element: Any) -> str:
    """
    An SVG element's tag without its namespace.

    Parameters
    ----------
    element : lxml.etree._Element
        The element.

    Returns
    -------
    str
        Its local name, such as ``"path"``.
    """
    return str(element.tag).rsplit("}", 1)[-1]


def _polygon(data: str) -> list[tuple[float, float]] | None:
    """
    The vertices of path data that draws one closed polygon of straight lines.

    The form matplotlib writes for a polygon's path: ``M x y``, then
    ``L x y`` for each further vertex, then ``z``.

    Parameters
    ----------
    data : str
        A ``d`` attribute.

    Returns
    -------
    list of tuple or None
        The vertices in order, or ``None`` for path data of any other form.
    """
    tokens = _PATH_TOKEN.findall(data)
    if len(tokens) < 4 or tokens[0] != "M" or tokens[-1] not in ("z", "Z"):
        return None
    vertices = []
    for start in range(0, len(tokens) - 1, 3):
        command, *coordinates = tokens[start : start + 3]
        if command != ("M" if start == 0 else "L") or len(coordinates) != 2:
            return None
        try:
            vertices.append((float(coordinates[0]), float(coordinates[1])))
        except ValueError:
            return None
    return vertices


def _polygon_data(vertices: list[tuple[float, float]]) -> str:
    """
    Path data drawing a closed polygon through the given vertices.

    Parameters
    ----------
    vertices : list of tuple
        The vertices, in drawing order.

    Returns
    -------
    str
        ``M x y L x y ... z``, each number as matplotlib writes it.
    """
    commands = [
        f"{'M' if index == 0 else 'L'} {_number(x)} {_number(y)}"
        for index, (x, y) in enumerate(vertices)
    ]
    return " ".join([*commands, "z"])


def _number(value: float) -> str:
    """
    One coordinate, written as matplotlib's SVG backend writes it.

    Parameters
    ----------
    value : float
        The coordinate.

    Returns
    -------
    str
        Six decimals at most, with trailing zeros dropped.
    """
    text = f"{value:f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text
