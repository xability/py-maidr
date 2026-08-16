from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from matplotlib.axes import Axes
from matplotlib.collections import Collection, PatchCollection, PathCollection
from matplotlib.lines import Line2D

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.exception import ExtractionError

#: Tail probability of the widest rung, which every letter-value ladder starts
#: from: the box spanning the middle half of the data. Successive rungs halve
#: it, so rung ``i`` counted inward from the deepest has ``p = 0.5 ** (k + 1 - i)``.
#: This is seaborn's own construction -- ``LetterValues.__call__`` builds its
#: percentiles as ``0.5 ** arange(k + 1, 1, -1)`` -- rather than a convention
#: chosen here.
_WIDEST_RUNG_P = 0.25

#: The keyword the patch hands this layer its own collections under. Named
#: once and imported at both ends rather than spelled twice, for the reason
#: ``ScatterPlot.DRAWN_POINTS`` gives: a mismatch falls back to sweeping the
#: axes, so a typo would restore the behaviour rather than raise.
DRAWN_LADDERS = "_maidr_ladders"


def _ladder_probabilities(depth: int) -> List[float]:
    """
    The tail probabilities of a ``depth``-rung letter-value ladder, deepest first.

    Mirrors ``seaborn._statistics.LetterValues.__call__``, which computes its
    lower percentiles as ``0.5 ** arange(k + 1, 1, -1)``: the widest rung is
    always the quartile pair and each step outward halves the tail.

    Parameters
    ----------
    depth : int
        Number of rungs, ``k`` in the letter-value literature.

    Returns
    -------
    list of float
        ``depth`` probabilities, ordered outermost (smallest) first so they
        line up with the box edges read from the outside in.

    Notes
    -----
    ``k_depth="full"`` is the one setting that does not follow this: seaborn
    overwrites the outermost percentile pair with 0 and 100, so the deepest
    rung is the sample minimum and maximum rather than the quantile named
    here. The nominal probability is kept for it anyway, because the
    alternative is worse in both directions -- the core drops a rung whose
    ``p`` is outside ``(0, 0.5)``, which would take the extremes out of the
    reading altogether and leave ``Min value`` and ``Max value`` reporting the
    *second* deepest quantile as the range. At the depths ``"full"`` reaches
    the two differ by well under one observation.
    """
    return [_WIDEST_RUNG_P * 0.5**step for step in range(depth - 1, -1, -1)]


class BoxenPlot(MaidrPlot):
    """
    A letter-value plot: ``seaborn.boxenplot``.

    A boxen plot is a box plot whose tails keep resolving. Where a box plot
    stops at one quartile box and calls everything past the whiskers an
    outlier, a boxen draws a *ladder*: the quartile pair, then the eighths,
    then the sixteenths, as deep as the sample supports. The whole point is
    that a large sample gets more rungs, so the shape of the tail stays
    legible instead of collapsing into a whisker and a cloud of dots.

    Before this class, MAIDR had no type that could hold that, and what
    ``sns.boxenplot`` produced was not a partial reading but a wrong one.
    Measured on a three-category chart of 200 observations each::

        line  : 3 series of 2 points, every series a value repeated twice
        point : 3 layers, x = 0.0 / 1.0 / 2.0

    The line layer was the three median segments, each read as a two-sample
    series -- so the chart announced itself as a line chart and said each
    median twice. The point layers were the outliers alone, positioned at the
    numeric category slots rather than at ``a``/``b``/``c``. Every rung of
    every ladder, which is the entire chart, was absent, and nothing in the
    output suggested anything was missing.

    Extraction reads what was drawn rather than recomputing it. seaborn renders
    each ladder as a :class:`~matplotlib.collections.PatchCollection` of
    ``2k - 1`` boxes whose edges along the value axis are exactly the letter
    values it computed, so the quantiles are read off those edges; the median
    comes from the segment drawn across the ladder, and the fliers from the
    :class:`~matplotlib.collections.PathCollection` beside it. Only the tail
    probability that names each rung is inferred, and that from seaborn's own
    formula rather than from the geometry -- see :func:`_ladder_probabilities`.

    Parameters
    ----------
    ax : Axes
        The axes seaborn drew the boxen plot on.
    **kwargs : dict
        Accepted and ignored, so the factory can pass a uniform payload.

    Notes
    -----
    Orientation is taken from the median segment rather than from a keyword:
    the axis the segment *runs along* is the category axis, and the one it
    holds constant is the value axis. That is true of both orientations by
    construction and needs nothing threaded through from the call site.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.BOXEN)

        # No selector, because the grammar has no shape for one. A box plot
        # highlights through ``BoxSelector``, which names an element per
        # summary value -- ``min``, ``iq``, ``q2``, ``max`` and the two
        # outlier lists. A boxen's ladder has no fixed depth, so there is no
        # fixed set of names to fill in, and the core declares no boxen
        # counterpart. Emitting a selector list against a shape the frontend
        # does not read would attach an outline to nothing.
        self._support_highlighting = False

        # Filled in during extraction, from the median segment of the first
        # ladder read. Vertical is the right default: it is what the core
        # falls back to (``layer.orientation ?? Orientation.VERTICAL``) and
        # what seaborn draws unless told otherwise.
        self._orientation = "vert"

        drawn = kwargs.get(DRAWN_LADDERS, None)
        self._own_collections = drawn if isinstance(drawn, list) else None

    def render(self) -> dict:
        """
        Emit the layer, carrying which way round it is drawn.

        The core reads ``layer.orientation`` and falls back to vertical when
        it is absent, so a horizontal boxen without it is not merely
        unlabelled -- it is labelled *backwards*. ``BoxenTrace.text`` picks
        the announcement's two axis labels off this flag::

            label: isHorizontal ? this.yAxis : this.xAxis,   // the category
            label: isHorizontal ? this.xAxis : this.yAxis,   // the quantile

        so ``sns.boxenplot(y="g", x="v")`` announced the category under the
        *value* axis's name and the quantile under the *category* axis's:
        "v is a", "g is 1.23". The values were right and the two things
        naming them were swapped, which is the reading that sounds complete.

        Returns
        -------
        dict
            The base schema with ``orientation`` merged in.
        """
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = self._orientation
        return schema

    def _extract_axes_data(self) -> dict:
        """
        Extend the base per-axis mapping with the legend title as ``z``.

        A hue split names each ladder by the level it belongs to, so the
        dimension itself needs a name for those levels to be announced against.
        Omitted when there is no legend.
        """
        axes_data = super()._extract_axes_data()

        legend = self.ax.get_legend()
        if legend is not None:
            title = legend.get_title()
            if title is not None:
                label = title.get_text().strip()
                if label:
                    axes_data[MaidrKey.Z] = self._axis_config(label=label)

        return axes_data

    def _ladders(self) -> List[Tuple[PatchCollection, Optional[PathCollection]]]:
        """
        Pair each drawn ladder with the flier cloud beside it.

        seaborn adds the two together and in that order, once per boxen, so the
        pairing is positional. A ladder with no fliers still gets an empty
        collection; the ``None`` fallback only guards a trailing ladder.

        Returns
        -------
        list of (PatchCollection, PathCollection or None)
            One entry per boxen, in draw order.
        """
        collections: Sequence[Collection] = (
            self._own_collections
            if self._own_collections is not None
            else self.ax.collections
        )
        pairs = []

        for index, collection in enumerate(collections):
            if not isinstance(collection, PatchCollection):
                continue
            nxt = collections[index + 1] if index + 1 < len(collections) else None
            pairs.append((collection, nxt if isinstance(nxt, PathCollection) else None))

        return pairs

    @staticmethod
    def _box_bounds(ladder: PatchCollection) -> List[Tuple[float, float, float, float]]:
        """Every box of a ladder as ``(x0, x1, y0, y1)`` in data coordinates."""
        bounds = []
        for path in ladder.get_paths():
            extents = path.get_extents()
            bounds.append(
                (
                    float(extents.x0),
                    float(extents.x1),
                    float(extents.y0),
                    float(extents.y1),
                )
            )
        return bounds

    def _median_of(self, ladder: PatchCollection) -> Optional[Line2D]:
        """
        The median segment drawn across ``ladder``.

        Matched by containment rather than by position in ``ax.get_lines()``.
        Order would work for a chart seaborn drew by itself, but a reference
        line or any other line the user added lands in the same list, and a
        positional match would then pair a ladder with something that is not
        its median and read a value off it. Containment cannot: a line is this
        ladder's median only if it lies inside this ladder's own footprint.

        Parameters
        ----------
        ladder : PatchCollection
            One boxen's nested boxes.

        Returns
        -------
        Line2D or None
            The segment, or None when the ladder has no median drawn.
        """
        bounds = self._box_bounds(ladder)
        if not bounds:
            return None

        x0 = min(bound[0] for bound in bounds)
        x1 = max(bound[1] for bound in bounds)
        y0 = min(bound[2] for bound in bounds)
        y1 = max(bound[3] for bound in bounds)
        # Widened by a whisker so a median sitting exactly on a box edge, or
        # nudged by floating point, is still inside its own ladder.
        pad_x = (x1 - x0) * 1e-6
        pad_y = (y1 - y0) * 1e-6

        for line in self.ax.get_lines():
            xy = line.get_xydata()
            if xy is None or len(xy) != 2:  # type: ignore[arg-type]
                continue
            xs = [float(point[0]) for point in xy]
            ys = [float(point[1]) for point in xy]
            if not all(math.isfinite(value) for value in xs + ys):
                continue
            if all(x0 - pad_x <= x <= x1 + pad_x for x in xs) and all(
                y0 - pad_y <= y <= y1 + pad_y for y in ys
            ):
                return line

        return None

    @staticmethod
    def _is_vertical(median: Line2D) -> bool:
        """
        Whether the boxen runs up the page, from the median segment alone.

        The segment spans the ladder across the *category* axis and holds the
        value constant, so a horizontal segment means a vertical boxen. Asking
        the geometry rather than a keyword covers ``orient=``, ``x=``/``y=``
        and the inference seaborn does from column dtypes with one rule.
        """
        xy = median.get_xydata()
        return float(xy[0][0]) != float(xy[1][0])  # type: ignore[index]

    def _tick_labels(self, vertical: bool) -> List[Tuple[float, str]]:
        """Category tick positions paired with their rendered labels."""
        axis = self.ax.xaxis if vertical else self.ax.yaxis
        return [
            (float(position), text.get_text())
            for position, text in zip(axis.get_ticklocs(), axis.get_ticklabels())
        ]

    def _category_of(self, centre: float, width: float, vertical: bool) -> str:
        """
        Name the distribution a ladder at ``centre`` summarises.

        Without a hue split a ladder sits on its tick and the tick's label is
        the answer. With one, seaborn dodges ``n`` ladders into the slot, each
        ``width`` wide, so level ``j`` is centred ``width * (j + 0.5)`` from the
        slot's left edge. Inverting that gives the level, which is why the
        arithmetic is here rather than a left-to-right walk: a category that is
        missing a level would shift every later ladder along and rename them
        all.

        Parameters
        ----------
        centre : float
            The ladder's midpoint on the category axis.
        width : float
            The widest box's extent along the category axis, which is the
            per-level slot width.
        vertical : bool
            Whether the category axis is x.

        Returns
        -------
        str
            The category, or ``"category, level"`` when a hue split is drawn.
        """
        ticks = self._tick_labels(vertical)
        if not ticks:
            return ""

        position, label = min(ticks, key=lambda tick: abs(tick[0] - centre))

        legend = self.ax.get_legend()
        levels = [text.get_text() for text in legend.get_texts()] if legend else []
        if len(levels) < 2 or width <= 0:
            return label

        index = round((centre - position + width * len(levels) / 2) / width - 0.5)
        if 0 <= index < len(levels):
            return f"{label}, {levels[index]}"

        return label

    @staticmethod
    def _levels(boxes: List[Tuple[float, float]]) -> List[dict]:
        """
        Turn a ladder's boxes into rungs, deepest first.

        Each box is consumed once rather than a set of shared edges being
        collected, and that is the whole of the method. Adjacent boxes meet at
        a quantile, so deduplicating edges looks equivalent -- but the two
        boxes meeting there hold *separately computed* floats, and when they
        differ in the last bits both survive. Measured on a 200-sample group
        that way: five rungs instead of four, ``lo`` repeated across two of
        them, and the widest rung a copy of its neighbour. The reading stayed
        plausible throughout, which is what made it worth removing the float
        comparison rather than adding a tolerance to it.

        A ``k``-rung ladder is drawn as ``2k - 1`` boxes: one straddling the
        median and ``k - 1`` extending outward on each side. So the lower
        quantiles are the lower edges of the bottom ``k`` boxes, the upper
        quantiles the upper edges of the top ``k``, and rung ``i`` counted from
        the deepest pairs the ``i``-th of the first with the ``i``-th from the
        end of the second.

        Parameters
        ----------
        boxes : list of (float, float)
            Every box as ``(low, high)`` along the value axis, ascending.

        Returns
        -------
        list of dict
            ``{p, lo, hi}`` per rung, ordered outermost first, which is the
            order the core walks them in.
        """
        depth = (len(boxes) + 1) // 2
        if depth < 1:
            return []

        los = [box[0] for box in boxes[:depth]]
        his = [box[1] for box in boxes[len(boxes) - depth :]]

        return [
            {
                MaidrKey.P.value: probability,
                MaidrKey.LO.value: los[rung],
                MaidrKey.HI.value: his[depth - 1 - rung],
            }
            for rung, probability in enumerate(_ladder_probabilities(depth))
        ]

    @staticmethod
    def _outliers(
        fliers: Optional[PathCollection], vertical: bool, low: float, high: float
    ) -> Tuple[List[float], List[float]]:
        """Split a flier cloud into the values below and above the deepest rung."""
        if fliers is None:
            return [], []

        offsets = fliers.get_offsets()
        values = [
            float(offset[1] if vertical else offset[0])
            for offset in offsets
            if math.isfinite(float(offset[1] if vertical else offset[0]))
        ]

        return (
            sorted(value for value in values if value < low),
            sorted(value for value in values if value > high),
        )

    def _extract_plot_data(self) -> List[dict]:
        """
        One :class:`BoxenPoint` per drawn ladder.

        Returns
        -------
        list of dict
            ``z``, ``median``, ``levels`` and, when present, the outliers on
            each side.

        Raises
        ------
        ExtractionError
            When nothing on the axes reads as a letter-value ladder.
        """
        points = []

        for ladder, fliers in self._ladders():
            bounds = self._box_bounds(ladder)
            median_line = self._median_of(ladder)
            if not bounds or median_line is None:
                continue

            vertical = self._is_vertical(median_line)
            self._orientation = "vert" if vertical else "horz"
            xy = median_line.get_xydata()
            median = float(xy[0][1] if vertical else xy[0][0])  # type: ignore[index]

            # Along the value axis the boxes tile edge to edge; along the
            # category axis they are nested about a shared centre.
            if vertical:
                boxes = sorted((bound[2], bound[3]) for bound in bounds)
                spans = [(bound[0], bound[1]) for bound in bounds]
            else:
                boxes = sorted((bound[0], bound[1]) for bound in bounds)
                spans = [(bound[2], bound[3]) for bound in bounds]

            levels = self._levels(boxes)
            if not levels:
                continue

            widest = max(span[1] - span[0] for span in spans)
            centre = (
                min(span[0] for span in spans) + max(span[1] for span in spans)
            ) / 2
            lower, upper = self._outliers(
                fliers,
                vertical,
                levels[0][MaidrKey.LO.value],
                levels[0][MaidrKey.HI.value],
            )

            point = {
                MaidrKey.Z.value: self._category_of(centre, widest, vertical),
                MaidrKey.MEDIAN.value: median,
                MaidrKey.LEVELS.value: levels,
            }
            if lower:
                point[MaidrKey.LOWER_OUTLIER.value] = lower
            if upper:
                point[MaidrKey.UPPER_OUTLIER.value] = upper

            points.append(point)

        if not points:
            raise ExtractionError(self.type, self.ax)

        return points
