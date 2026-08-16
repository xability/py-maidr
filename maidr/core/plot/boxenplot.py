from __future__ import annotations

import math
import warnings
from typing import Sequence

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


def _ladder_probabilities(depth: int) -> list[float]:
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

        # The collections this layer's own call drew, handed over by the
        # patch. Absent means none rather than "sweep the axes": a fallback
        # sweep is what pairs each ladder with whatever collection follows it,
        # and that is the defect two commits of this change went to remove. It
        # is unreachable through the patch, which always supplies these, so
        # keeping it would only arm a trap for a future caller that constructs
        # this class directly -- and arm it silently, since a swept chart
        # reads as a complete one. With no collections there are no ladders,
        # and `_extract_plot_data` raises.
        drawn = kwargs.get(DRAWN_LADDERS, None)
        self._own_collections = drawn if isinstance(drawn, list) else []

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

    def _ladders(self) -> list[tuple[PatchCollection, PathCollection | None]]:
        """
        Pair each drawn ladder with the flier cloud that belongs to it.

        Matched by where the fliers sit rather than by where they appear in
        the list, because the order is not stable across seaborn versions.
        0.13 adds the ladder then its fliers; 0.12 adds them the other way
        round::

            0.13   Patch Path Patch Path
            0.12   Path Patch Path Patch

        So "the collection after this one" pairs a ladder with its *own*
        fliers on one version and with the *next group's* on the other -- a
        chart whose outliers are attributed to the wrong distribution while
        every number in it is real.

        A ladder's fliers are drawn on its own category slot, so containment
        settles it on both. This is the rule ``_median_of`` already uses, for
        the same reason.

        Returns
        -------
        list of (PatchCollection, PathCollection or None)
            One entry per boxen, in draw order. ``None`` when nothing was
            drawn beyond the deepest rung.
        """
        collections: Sequence[Collection] = self._own_collections
        ladders = [c for c in collections if isinstance(c, PatchCollection)]
        clouds = [c for c in collections if isinstance(c, PathCollection)]

        pairs = []
        for ladder in ladders:
            bounds = self._box_bounds(ladder)
            if not bounds:
                pairs.append((ladder, None))
                continue

            x0 = min(bound[0] for bound in bounds)
            x1 = max(bound[1] for bound in bounds)
            y0 = min(bound[2] for bound in bounds)
            y1 = max(bound[3] for bound in bounds)

            pairs.append((ladder, self._cloud_within(clouds, x0, x1, y0, y1)))

        return pairs

    @staticmethod
    def _cloud_within(
        clouds: list[PathCollection],
        x0: float,
        x1: float,
        y0: float,
        y1: float,
    ) -> PathCollection | None:
        """
        The flier cloud drawn on one ladder's category slot.

        Asked of the category axis alone -- a flier is by definition outside
        the ladder's *value* range, so requiring containment there would
        reject every real one. Which axis carries the categories is not known
        yet at this point, so both are tried and whichever the cloud fits
        decides it.

        Parameters
        ----------
        clouds : list of PathCollection
            Every flier collection this call drew.
        x0, x1, y0, y1 : float
            The ladder's extent.

        Returns
        -------
        PathCollection or None
            The first cloud sitting within the ladder's slot, or None.
        """
        for cloud in clouds:
            offsets = cloud.get_offsets()
            if offsets is None or not len(offsets):
                continue
            xs = [float(offset[0]) for offset in offsets]
            ys = [float(offset[1]) for offset in offsets]
            if all(x0 <= x <= x1 for x in xs) or all(y0 <= y <= y1 for y in ys):
                return cloud

        return None

    @staticmethod
    def _box_bounds(ladder: PatchCollection) -> list[tuple[float, float, float, float]]:
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

    def _median_of(self, ladder: PatchCollection) -> Line2D | None:
        """
        The median segment drawn across ``ladder``.

        Matched by containment rather than by position in ``ax.get_lines()``.
        Order would work for a chart seaborn drew by itself, but a reference
        line or any other line the user added lands in the same list, and a
        positional match would then pair a ladder with something that is not
        its median and read a value off it.

        Containment alone is not enough either. A short segment a user drew in
        data space can sit entirely inside a ladder's footprint: measured on
        ``ax.plot([-0.1, 0.1], [0.5, 0.5])`` under a two-category boxen, the
        first category's median was announced as 0.5 where the data says
        0.0484. What separates the two is *span*. seaborn draws a median
        across the whole ladder, so its endpoints are the ladder's own extent
        on the category axis -- measured, -0.4 to 0.4 against a widest box of
        exactly that width, where the user's segment spanned -0.1 to 0.1.

        So a median is a segment that spans the ladder end to end on one axis
        and holds a single value inside it on the other. That is orientation
        agnostic, which is what lets this run before orientation is known.

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
        # A matching tolerance rather than slack: the endpoints seaborn drew
        # are the ladder's own extent, so they agree to floating point and
        # this only absorbs the last bits.
        pad_x = (x1 - x0) * 1e-6
        pad_y = (y1 - y0) * 1e-6

        for line in self.ax.get_lines():
            # `axhline`/`axvline` blend the *axes* transform on one axis, so
            # their stored coordinates run 0 to 1 and describe the extent of
            # the axes rather than any value. Those numbers land in data space
            # by coincidence, and a threshold given an explicit span does land
            # inside a ladder: measured on `axhline(0.0, xmin=.15, xmax=.35)`
            # over two categories, containment matched and the first
            # category's median was announced as 0.0 where the data says
            # 0.0484. Asking the transform is the same test `MultiLinePlot`
            # uses to keep a reference line out of a line layer (#434).
            if line.get_transform() is not self.ax.transData:
                continue
            xy = line.get_xydata()
            if xy is None or len(xy) != 2:  # type: ignore[arg-type]
                continue
            xs = [float(point[0]) for point in xy]
            ys = [float(point[1]) for point in xy]
            if not all(math.isfinite(value) for value in xs + ys):
                continue
            spans_x = abs(min(xs) - x0) <= pad_x and abs(max(xs) - x1) <= pad_x
            spans_y = abs(min(ys) - y0) <= pad_y and abs(max(ys) - y1) <= pad_y
            level_y = abs(ys[0] - ys[1]) <= pad_y and y0 - pad_y <= ys[0] <= y1 + pad_y
            level_x = abs(xs[0] - xs[1]) <= pad_x and x0 - pad_x <= xs[0] <= x1 + pad_x

            if (spans_x and level_y) or (spans_y and level_x):
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

    def _hue_levels(self) -> list[str]:
        """
        The hue levels, in the order the legend lists them.

        Load-bearing, and worth saying so: a ladder's level is decided by its
        rank in the dodge lattice, and that rank is looked up in this list. The
        two agree because seaborn lays the dodge out in legend order --
        verified against ``hue_order``, which reorders both together::

            hue_order=["r","q","p"]  legend ['r','q','p']  z 'a, r' 'a, q' 'a, p'
            hue_order=["q","p","r"]  legend ['q','p','r']  z 'a, q' 'a, p' 'a, r'

        If a future seaborn ever ordered the legend independently of the
        dodge, every level would be silently mislabelled rather than raising,
        which is why ``test_a_reordered_hue_keeps_each_ladder_with_its_level``
        exists rather than the assumption being left implicit.
        """
        legend = self.ax.get_legend()
        return [text.get_text() for text in legend.get_texts()] if legend else []

    def _tick_labels(self, vertical: bool) -> list[tuple[float, str]]:
        """Category tick positions paired with their rendered labels."""
        axis = self.ax.xaxis if vertical else self.ax.yaxis
        return [
            (float(position), text.get_text())
            for position, text in zip(axis.get_ticklocs(), axis.get_ticklabels())
        ]

    def _dodge_offsets(self, centres: list[float], vertical: bool) -> list[float]:
        """
        The distinct offsets from a tick at which ladders are drawn.

        A hue split dodges ``n`` ladders into each category's slot, and every
        slot uses the same offsets. Collecting them across the whole chart and
        sorting gives the dodge lattice directly, so a ladder's level is its
        offset's rank -- no pitch, slot width or gap arithmetic involved.

        That is what makes it hold under ``gap=``. Deriving the pitch from the
        widest drawn box assumes a box fills its slot, and ``gap=`` is exactly
        the parameter that stops it: measured on four hue levels, ``gap=0.3``
        left two ladders with no level name and ``gap=0.6`` gave two of them
        the *wrong* one -- ``a, p`` where the chart drew ``a, q``.

        Reading the lattice from every ladder rather than per category also
        survives a category that is missing a level, so long as some other
        category draws it: the offsets are a property of the dodge, not of the
        data in one slot.

        Parameters
        ----------
        centres : list of float
            Every ladder's midpoint on the category axis.
        vertical : bool
            Whether the category axis is x.

        Returns
        -------
        list of float
            Distinct offsets, ascending. Empty when there are no ticks to
            measure from.
        """
        ticks = self._tick_labels(vertical)
        if not ticks:
            return []

        offsets: list[float] = []
        for centre in centres:
            position = min(ticks, key=lambda tick: abs(tick[0] - centre))[0]
            offset = centre - position
            # Clustered rather than compared exactly: the same lattice
            # position arrives with different last bits from category to
            # category.
            if not any(abs(offset - seen) < 1e-6 for seen in offsets):
                offsets.append(offset)

        return sorted(offsets)

    def _category_of(
        self,
        centre: float,
        offsets: list[float],
        ticks: list[tuple[float, str]],
        levels: list[str],
    ) -> str:
        """
        Name the distribution a ladder at ``centre`` summarises.

        Without a hue split a ladder sits on its tick and the tick's label is
        the answer. With one, the ladder sits at one of the dodge lattice's
        offsets from its tick, and which one it is says which level it belongs
        to -- see :meth:`_dodge_offsets` for why the lattice is measured
        rather than computed.

        Parameters
        ----------
        centre : float
            The ladder's midpoint on the category axis.
        offsets : list of float
            The dodge lattice, from :meth:`_dodge_offsets`.
        ticks : list of (float, str)
            Category tick positions and labels, read once for the whole layer.
        levels : list of str
            Hue levels in legend order, read once for the whole layer.

        Returns
        -------
        str
            The category, or ``"category, level"`` when a hue split is drawn.
        """
        if not ticks:
            return ""

        # Nearest tick, which is safe by construction rather than by luck.
        # seaborn dodges `n` levels into a slot `width` wide, so the outermost
        # ladder's centre sits `width * (n - 1) / (2n)` from its tick -- always
        # under `width / 2`, and `width` is a fraction of the categorical unit
        # whose spacing is 1. Measured, against a half-spacing of 0.5::
        #
        #     n=2 width=0.8  ->  0.2000
        #     n=6 width=1.0  ->  0.4167
        #     n=8 width=1.0  ->  0.4375
        #
        # The bound tightens toward 0.5 as levels are added and only reaches
        # it in the limit, at a width that would already have adjacent
        # categories touching.
        position, label = min(ticks, key=lambda tick: abs(tick[0] - centre))

        if len(levels) < 2 or len(offsets) < 2:
            return label

        offset = centre - position
        index = min(range(len(offsets)), key=lambda rank: abs(offsets[rank] - offset))
        if index < len(levels):
            return f"{label}, {levels[index]}"

        return label

    @staticmethod
    def _levels(boxes: list[tuple[float, float]]) -> list[dict]:
        """
        Turn a ladder's boxes into rungs, deepest first.

        A ``k``-rung ladder is drawn as ``2k - 1`` boxes abutting edge to
        edge: one straddling the median and ``k - 1`` extending outward each
        way. So the lower quantiles are the lower edges of the bottom ``k``
        boxes, the upper quantiles the upper edges of the top ``k``, and rung
        ``i`` counted from the deepest pairs the ``i``-th of the first with
        the ``i``-th from the end of the second.

        That is seaborn 0.13's construction. 0.12 draws the same ladder as
        ``k`` boxes *nested* inside one another, each spanning a whole rung,
        and this rule would read four of those as two rungs with ``lo`` and
        ``hi`` taken from different ones. It is not handled, because
        ``import maidr`` does not survive seaborn 0.12 at all -- the box plot
        patch reaches for ``_CategoricalPlotter.plot_boxes``, which 0.13
        introduced (#441). 0.13 is the effective floor, and adding a branch
        for a layout nothing can reach would be speculative rather than
        defensive. The layout difference is recorded on that issue so it is
        not rediscovered by whoever fixes the floor.

        Each box is consumed once, rather than a set of shared edges being
        collected. Adjacent boxes meet at a quantile but hold *separately
        computed* floats, and when they differ in the last bits both survive
        the set. Measured that way: five rungs instead of four, ``lo``
        repeated across two of them, and the widest rung a copy of its
        neighbour -- plausible throughout, which is what made it worth
        removing the float comparison rather than adding a tolerance to it.

        Parameters
        ----------
        boxes : list of (float, float)
            Every box as ``(low, high)`` along the value axis, ascending.

        Returns
        -------
        list of dict
            ``{p, lo, hi}`` per rung, outermost first, which is the order the
            core walks them in.
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
    def _cloud_within(
        clouds: list[PathCollection],
        x0: float,
        x1: float,
        y0: float,
        y1: float,
    ) -> PathCollection | None:
        """
        The flier cloud drawn on one ladder's category slot.

        Asked of the category axis alone -- a flier is by definition outside
        the ladder's *value* range, so requiring containment there would
        reject every real one. Which axis carries the categories is not known
        yet at this point, so both are tried and whichever the cloud fits
        decides it.

        Parameters
        ----------
        clouds : list of PathCollection
            Every flier collection this call drew.
        x0, x1, y0, y1 : float
            The ladder's extent.

        Returns
        -------
        PathCollection or None
            The first cloud sitting within the ladder's slot, or None.
        """
        for cloud in clouds:
            offsets = cloud.get_offsets()
            if offsets is None or not len(offsets):
                continue
            xs = [float(offset[0]) for offset in offsets]
            ys = [float(offset[1]) for offset in offsets]
            if all(x0 <= x <= x1 for x in xs) or all(y0 <= y <= y1 for y in ys):
                return cloud

        return None

    @staticmethod
    def _box_bounds(ladder: PatchCollection) -> list[tuple[float, float, float, float]]:
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

    def _median_of(self, ladder: PatchCollection) -> Line2D | None:
        """
        The median segment drawn across ``ladder``.

        Matched by containment rather than by position in ``ax.get_lines()``.
        Order would work for a chart seaborn drew by itself, but a reference
        line or any other line the user added lands in the same list, and a
        positional match would then pair a ladder with something that is not
        its median and read a value off it.

        Containment alone is not enough either. A short segment a user drew in
        data space can sit entirely inside a ladder's footprint: measured on
        ``ax.plot([-0.1, 0.1], [0.5, 0.5])`` under a two-category boxen, the
        first category's median was announced as 0.5 where the data says
        0.0484. What separates the two is *span*. seaborn draws a median
        across the whole ladder, so its endpoints are the ladder's own extent
        on the category axis -- measured, -0.4 to 0.4 against a widest box of
        exactly that width, where the user's segment spanned -0.1 to 0.1.

        So a median is a segment that spans the ladder end to end on one axis
        and holds a single value inside it on the other. That is orientation
        agnostic, which is what lets this run before orientation is known.

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
        # A matching tolerance rather than slack: the endpoints seaborn drew
        # are the ladder's own extent, so they agree to floating point and
        # this only absorbs the last bits.
        pad_x = (x1 - x0) * 1e-6
        pad_y = (y1 - y0) * 1e-6

        for line in self.ax.get_lines():
            # `axhline`/`axvline` blend the *axes* transform on one axis, so
            # their stored coordinates run 0 to 1 and describe the extent of
            # the axes rather than any value. Those numbers land in data space
            # by coincidence, and a threshold given an explicit span does land
            # inside a ladder: measured on `axhline(0.0, xmin=.15, xmax=.35)`
            # over two categories, containment matched and the first
            # category's median was announced as 0.0 where the data says
            # 0.0484. Asking the transform is the same test `MultiLinePlot`
            # uses to keep a reference line out of a line layer (#434).
            if line.get_transform() is not self.ax.transData:
                continue
            xy = line.get_xydata()
            if xy is None or len(xy) != 2:  # type: ignore[arg-type]
                continue
            xs = [float(point[0]) for point in xy]
            ys = [float(point[1]) for point in xy]
            if not all(math.isfinite(value) for value in xs + ys):
                continue
            spans_x = abs(min(xs) - x0) <= pad_x and abs(max(xs) - x1) <= pad_x
            spans_y = abs(min(ys) - y0) <= pad_y and abs(max(ys) - y1) <= pad_y
            level_y = abs(ys[0] - ys[1]) <= pad_y and y0 - pad_y <= ys[0] <= y1 + pad_y
            level_x = abs(xs[0] - xs[1]) <= pad_x and x0 - pad_x <= xs[0] <= x1 + pad_x

            if (spans_x and level_y) or (spans_y and level_x):
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

    def _hue_levels(self) -> list[str]:
        """
        The hue levels, in the order the legend lists them.

        Load-bearing, and worth saying so: a ladder's level is decided by its
        rank in the dodge lattice, and that rank is looked up in this list. The
        two agree because seaborn lays the dodge out in legend order --
        verified against ``hue_order``, which reorders both together::

            hue_order=["r","q","p"]  legend ['r','q','p']  z 'a, r' 'a, q' 'a, p'
            hue_order=["q","p","r"]  legend ['q','p','r']  z 'a, q' 'a, p' 'a, r'

        If a future seaborn ever ordered the legend independently of the
        dodge, every level would be silently mislabelled rather than raising,
        which is why ``test_a_reordered_hue_keeps_each_ladder_with_its_level``
        exists rather than the assumption being left implicit.
        """
        legend = self.ax.get_legend()
        return [text.get_text() for text in legend.get_texts()] if legend else []

    def _tick_labels(self, vertical: bool) -> list[tuple[float, str]]:
        """Category tick positions paired with their rendered labels."""
        axis = self.ax.xaxis if vertical else self.ax.yaxis
        return [
            (float(position), text.get_text())
            for position, text in zip(axis.get_ticklocs(), axis.get_ticklabels())
        ]

    def _dodge_offsets(self, centres: list[float], vertical: bool) -> list[float]:
        """
        The distinct offsets from a tick at which ladders are drawn.

        A hue split dodges ``n`` ladders into each category's slot, and every
        slot uses the same offsets. Collecting them across the whole chart and
        sorting gives the dodge lattice directly, so a ladder's level is its
        offset's rank -- no pitch, slot width or gap arithmetic involved.

        That is what makes it hold under ``gap=``. Deriving the pitch from the
        widest drawn box assumes a box fills its slot, and ``gap=`` is exactly
        the parameter that stops it: measured on four hue levels, ``gap=0.3``
        left two ladders with no level name and ``gap=0.6`` gave two of them
        the *wrong* one -- ``a, p`` where the chart drew ``a, q``.

        Reading the lattice from every ladder rather than per category also
        survives a category that is missing a level, so long as some other
        category draws it: the offsets are a property of the dodge, not of the
        data in one slot.

        Parameters
        ----------
        centres : list of float
            Every ladder's midpoint on the category axis.
        vertical : bool
            Whether the category axis is x.

        Returns
        -------
        list of float
            Distinct offsets, ascending. Empty when there are no ticks to
            measure from.
        """
        ticks = self._tick_labels(vertical)
        if not ticks:
            return []

        offsets: list[float] = []
        for centre in centres:
            position = min(ticks, key=lambda tick: abs(tick[0] - centre))[0]
            offset = centre - position
            # Clustered rather than compared exactly: the same lattice
            # position arrives with different last bits from category to
            # category.
            if not any(abs(offset - seen) < 1e-6 for seen in offsets):
                offsets.append(offset)

        return sorted(offsets)

    def _category_of(
        self,
        centre: float,
        offsets: list[float],
        ticks: list[tuple[float, str]],
        levels: list[str],
    ) -> str:
        """
        Name the distribution a ladder at ``centre`` summarises.

        Without a hue split a ladder sits on its tick and the tick's label is
        the answer. With one, the ladder sits at one of the dodge lattice's
        offsets from its tick, and which one it is says which level it belongs
        to -- see :meth:`_dodge_offsets` for why the lattice is measured
        rather than computed.

        Parameters
        ----------
        centre : float
            The ladder's midpoint on the category axis.
        offsets : list of float
            The dodge lattice, from :meth:`_dodge_offsets`.
        ticks : list of (float, str)
            Category tick positions and labels, read once for the whole layer.
        levels : list of str
            Hue levels in legend order, read once for the whole layer.

        Returns
        -------
        str
            The category, or ``"category, level"`` when a hue split is drawn.
        """
        if not ticks:
            return ""

        # Nearest tick, which is safe by construction rather than by luck.
        # seaborn dodges `n` levels into a slot `width` wide, so the outermost
        # ladder's centre sits `width * (n - 1) / (2n)` from its tick -- always
        # under `width / 2`, and `width` is a fraction of the categorical unit
        # whose spacing is 1. Measured, against a half-spacing of 0.5::
        #
        #     n=2 width=0.8  ->  0.2000
        #     n=6 width=1.0  ->  0.4167
        #     n=8 width=1.0  ->  0.4375
        #
        # The bound tightens toward 0.5 as levels are added and only reaches
        # it in the limit, at a width that would already have adjacent
        # categories touching.
        position, label = min(ticks, key=lambda tick: abs(tick[0] - centre))

        if len(levels) < 2 or len(offsets) < 2:
            return label

        offset = centre - position
        index = min(range(len(offsets)), key=lambda rank: abs(offsets[rank] - offset))
        if index < len(levels):
            return f"{label}, {levels[index]}"

        return label

    @staticmethod
    def _levels(boxes: list[tuple[float, float]]) -> list[dict]:
        """
        Turn a ladder's boxes into rungs, deepest first.

        seaborn draws the same ladder two different ways, and which one it is
        can be read off the boxes rather than off a version number.

        **Tiled** (0.13 and later): ``2k - 1`` boxes abutting edge to edge, one
        straddling the median and ``k - 1`` extending outward each way. Their
        value intervals are disjoint, meeting at the quantiles.

        **Nested** (0.12): ``k`` boxes, each spanning a whole rung ``[lo, hi]``,
        drawn on top of one another. Their intervals contain each other, and
        the narrowest box on the category axis is the one covering the widest
        range of values. Measured on 0.12.2::

            box0: x -0.050..+0.050  y -1.9277..1.6800   <- p = 0.03125
            box3: x -0.400..+0.400  y -0.6258..0.6863   <- p = 0.25

        Reading the nested layout with the tiled rule is not a crash but a
        plausible ladder that is wrong: four nested boxes give
        ``(4 + 1) // 2 = 2`` rungs instead of four, with ``lo`` and ``hi``
        taken from different rungs and both mislabelled.

        Each box is consumed once either way, rather than a set of shared
        edges being collected. Adjacent tiled boxes meet at a quantile but
        hold *separately computed* floats, and when they differ in the last
        bits both survive a set. Measured that way: five rungs instead of
        four, ``lo`` repeated across two of them, and the widest rung a copy
        of its neighbour -- plausible throughout.

        Parameters
        ----------
        boxes : list of (float, float)
            Every box as ``(low, high)`` along the value axis, ascending.

        Returns
        -------
        list of dict
            ``{p, lo, hi}`` per rung, outermost first, which is the order the
            core walks them in.
        """
        if not boxes:
            return []

        if BoxenPlot._is_nested(boxes):
            # Widest value range first is already deepest first.
            ladder = sorted(boxes, key=lambda box: box[0] - box[1])
            return [
                {
                    MaidrKey.P.value: probability,
                    MaidrKey.LO.value: box[0],
                    MaidrKey.HI.value: box[1],
                }
                for box, probability in zip(ladder, _ladder_probabilities(len(ladder)))
            ]

        depth = (len(boxes) + 1) // 2
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
    def _is_nested(boxes: list[tuple[float, float]]) -> bool:
        """
        Whether the boxes contain one another rather than abutting.

        A tiled ladder's intervals touch at the quantiles and never overlap; a
        nested one's each sit strictly inside the next. One box is ambiguous
        and reads as tiled, which is right: ``2k - 1`` with ``k = 1`` is also
        one box, and both layouts then say the same thing.

        Parameters
        ----------
        boxes : list of (float, float)
            Every box as ``(low, high)`` along the value axis, ascending.

        Returns
        -------
        bool
            True when any box strictly contains another.
        """
        widest = max(boxes, key=lambda box: box[1] - box[0])
        span = widest[1] - widest[0]
        if span <= 0:
            return False

        # A tolerance rather than a strict comparison: tiled boxes meet at a
        # shared quantile whose two copies can differ in the last bits, and
        # that must not read as an overlap.
        slack = span * 1e-6
        return any(
            box is not widest
            and box[0] > widest[0] + slack
            and box[1] < widest[1] - slack
            for box in boxes
        )

    @staticmethod
    def _outliers(
        fliers: PathCollection | None, vertical: bool, low: float, high: float
    ) -> tuple[list[float], list[float]]:
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

    def _extract_plot_data(self) -> list[dict]:
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
        # Read every ladder's geometry first, then name them. Naming needs the
        # dodge lattice, and the lattice is only visible once every ladder's
        # centre is known -- a ladder cannot say which hue level it is from
        # its own position alone.
        read = []
        ladders = self._ladders()

        for ladder, fliers in ladders:
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

            centre = (
                min(span[0] for span in spans) + max(span[1] for span in spans)
            ) / 2
            lower, upper = self._outliers(
                fliers,
                vertical,
                levels[0][MaidrKey.LO.value],
                levels[0][MaidrKey.HI.value],
            )
            read.append((centre, vertical, median, levels, lower, upper))

        # Read once for the layer rather than once per ladder: the ticks and
        # the legend belong to the axes, not to any one ladder, and asking
        # them per ladder was the only reason this needed the axes at all
        # inside the naming loop.
        upright = read[0][1] if read else True
        offsets = self._dodge_offsets([entry[0] for entry in read], upright)
        ticks = self._tick_labels(upright)
        hue_levels = self._hue_levels()

        points = []
        for centre, _vertical, median, levels, lower, upper in read:
            point = {
                MaidrKey.Z.value: self._category_of(centre, offsets, ticks, hue_levels),
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

        # A ladder that was drawn but could not be read is dropped above, and
        # a chart quietly missing a distribution is the failure this class was
        # written to remove -- a reader is given a complete-sounding reading
        # of fewer groups than the chart has. Nothing here can repair it, so
        # it is said out loud instead.
        drawn = len(ladders)
        if len(points) < drawn:
            warnings.warn(
                f"maidr: read {len(points)} of {drawn} boxen distributions on "
                f"these axes; {drawn - len(points)} had no median segment or "
                "no boxes and are absent from the chart.",
                UserWarning,
                stacklevel=2,
            )

        return points
