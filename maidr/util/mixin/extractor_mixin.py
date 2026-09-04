import math

import numpy as np
from typing import Any, Dict, List, Optional, Tuple, Union

from matplotlib.axes import Axes
from matplotlib.category import UnitData
from matplotlib.cm import ScalarMappable
from matplotlib.collections import PolyQuadMesh, QuadMesh
from matplotlib.image import AxesImage
from matplotlib.lines import Line2D

from maidr.core.enum import MaidrKey


class ContainerExtractorMixin:
    @staticmethod
    def extract_container(
        ax: Axes,
        container_type: type,
        include_all: bool = False,
    ) -> Any:
        """
        Retrieve containers of a specified type from an Axes object.

        Returns ``None`` when the axes holds none of that type, which is what
        every caller is written for -- ``HistPlot._extract_bar_container_data``
        opens with ``if plot is None``. The single-container branch used to
        reach that answer through a bare ``next()`` and raise
        ``StopIteration`` instead, so the ``None`` handling below it could
        never run and a `sns.histplot(x=..., y=...)` -- a 2D histogram, drawn
        as a mesh rather than as bars -- killed the whole render with an
        exception that named nothing (#388).

        A bare ``StopIteration`` is never a useful failure, and inside a
        generator PEP 479 turns it into a ``RuntimeError`` with the cause
        obscured. The two branches now agree: nothing found is ``[]`` or
        ``None``, not an exception.
        """
        if ax is None or ax.containers is None:
            return None

        matches = [
            container
            for container in ax.containers
            if isinstance(container, container_type)
        ]

        # If include_all is True, return a list of all containers of the specified type.
        if include_all:
            return matches

        # Otherwise, return the first container of the specified type.
        return matches[0] if matches else None


def _within_tolerance_of(position: float, bound: float) -> bool:
    """
    Whether a tick sits on a data bound to within a rounding error.

    Parameters
    ----------
    position : float
        The tick's position in data coordinates.
    bound : float
        The data limit it is measured against.

    Returns
    -------
    bool
        True when the two differ by no more than float noise: one part in a
        billion of the larger magnitude of the two, as ``math.isclose``
        measures it, or 1e-12 outright beside zero.
    """
    return math.isclose(position, bound, rel_tol=1e-9, abs_tol=1e-12)


class LevelExtractorMixin:
    @staticmethod
    def extract_level_positions(
        ax: Axes, key: MaidrKey = MaidrKey.X
    ) -> Optional[List[float]]:
        """
        Where on the axis the labels ``extract_level`` returns are drawn.

        A caller that has its own idea of what the axis positions mean -- a
        heatmap, which knows where its own cells sit -- can only check the
        ticks against it by knowing where they are. Filtered
        through the same code ``extract_level`` filters through --
        ``_ticks_in_view`` -- so the two answers are index-aligned by
        construction rather than by both being edited together (#526).

        One divergence is deliberate and is not mirrored here:
        ``extract_level`` falls back to a *sibling* axes' labels when its own
        filter comes back empty, and a sibling's positions would be numbers
        off a different axes to pair against this one's cells. A caller that
        needs the two to line up therefore checks the lengths, which is what
        ``HeatPlot._cell_names`` does.

        Parameters
        ----------
        ax : Axes
            The axes to read.
        key : MaidrKey
            Which axis, ``X`` or ``Y``.

        Returns
        -------
        list of float or None
            One position per label, or ``None`` for a key that has none.
        """
        if ax is None or key not in (MaidrKey.X, MaidrKey.Y):
            return None

        return [
            float(position) for position, _ in LevelExtractorMixin._ticks_in_view(ax, key)
        ]

    @staticmethod
    def _ticks_in_view(ax: Axes, key: MaidrKey) -> List[tuple]:
        """
        The ticks of one axis that fall inside the data, with their labels.

        The one place the filter lives, so ``extract_level`` and
        ``extract_level_positions`` cannot disagree about which ticks they
        describe. They used to hold a copy each, and the claim that they
        stay index-aligned "however that rule changes" was true only for as
        long as both copies were edited together -- a claim about the habits
        of a future editor rather than about the code.

        Padded view limits are deliberately not used: a tick drawn outside
        the data is furniture, not a position anything was plotted at.

        Parameters
        ----------
        ax : Axes
            The axes to read.
        key : MaidrKey
            Which axis, ``X`` or ``Y``.

        Returns
        -------
        list of tuple
            ``(position, label)`` per kept tick, in axis order.
        """
        if MaidrKey.X == key:
            ticks = ax.get_xticks()
            labels = [label.get_text() for label in ax.get_xticklabels()]
            span = ax.dataLim.width if hasattr(ax, "dataLim") else 0
            low = ax.dataLim.x0 if span else 0
        else:
            ticks = ax.get_yticks()
            labels = [label.get_text() for label in ax.get_yticklabels()]
            span = ax.dataLim.height if hasattr(ax, "dataLim") else 0
            low = ax.dataLim.y0 if span else 0

        # To within a rounding error of either bound. A bar whose edge is
        # meant to sit on a tick can land a float past it: seaborn dodges
        # two hue levels to +-0.2 and draws each 0.4 wide, so the second
        # level's first bar starts at `0.2 - 0.2`, which arrives as 5.6e-17
        # -- and when that bar is the only one at the first category, the
        # tick at 0 sat outside its own data by that much and the category
        # was dropped (#752). A tick a rounding error outside the data is
        # not furniture.
        #
        # Anchored on the bound, not on the span: a slack cut from the span
        # is decades wide on a log axis running 1e-3 to 1e12, and admitted
        # ticks at 1e-6 and 1e-4 that no data reaches. `isclose` against
        # the bound itself keeps 5.6e-17 beside 0 and nothing beside 1e-3
        # but 1e-3.
        high = low + span
        kept = [
            index
            for index, position in enumerate(ticks)
            if span == 0
            or (position >= low or _within_tolerance_of(position, low))
            and (position <= high or _within_tolerance_of(position, high))
        ]
        return [
            (ticks[index], labels[index]) for index in kept if index < len(labels)
        ]

    @staticmethod
    def extract_level(ax: Axes, key: MaidrKey = MaidrKey.X) -> Optional[List[str]]:
        """Retrieve label texts from Axes based on the specified Maidr key."""
        if ax is None:
            return None

        level = None
        if key in (MaidrKey.X, MaidrKey.Y):
            # Through the same filter `extract_level_positions` uses, so the
            # two answers are index-aligned by construction rather than by
            # both being edited together.
            level = [label for _, label in LevelExtractorMixin._ticks_in_view(ax, key)]
        elif MaidrKey.Z == key:
            level = [container.get_label() for container in ax.containers]

        if len(level) == 0:  # type: ignore
            level = LevelExtractorMixin.extract_shared_xtick_labels(ax)

        return level

    @staticmethod
    def extract_shared_xtick_labels(ax):
        siblings = ax.get_shared_x_axes().get_siblings(ax)
        for shared_ax in siblings:
            labels = [label.get_text() for label in shared_ax.get_xticklabels()]
            if any(labels):
                return labels
        return []


class LineExtractorMixin:
    @staticmethod
    def extract_line(ax: Axes) -> Optional[Line2D]:
        """Retrieve the last line object from Axes, if available."""
        if ax is None or ax.get_lines() is None:
            return None

        # Since the upstream MaidrJS library currently supports only the last plot line,
        # `maidr` package supports the same.
        return ax.get_lines()[-1]

    @staticmethod
    def extract_lines(ax: Axes) -> Optional[List[Line2D]]:
        """Retrieve all line objects from Axes, if available."""
        if ax is None or ax.get_lines() is None:
            return None

        # Since the upstream MaidrJS library currently supports only the last plot line,
        # `maidr` package supports the same.
        return ax.get_lines()

    @staticmethod
    def _category_tick_labels(ax: Axes, axis: str) -> Dict[float, str]:
        """
        Map an axis's tick coordinates to the names written beside them.

        Built from the *unfiltered* tick positions and labels, and keyed by
        tick coordinate rather than array index, so it survives boundary ticks
        being filtered elsewhere (``LevelExtractorMixin.extract_level``) and
        tick layouts that are neither contiguous nor zero-based.

        Empty unless the axis really is a string-category axis: matplotlib
        leaves a ``UnitData`` on the axis it mapped strings onto. It is the
        *kind* of units that decides, not their presence -- a date axis
        carries units too, because matplotlib's date converter records the
        data's ``tzinfo`` there, so a tz-aware index leaves a ``timezone``
        where a naive one leaves ``None``. That axis is numeric for this
        purpose: reading it as categories snapped every hourly point onto a
        daily tick (#709). A numeric axis has tick labels too -- "0", "25",
        "1.00" -- and they are formatted renderings of the numbers rather than
        names for them, so substituting one costs the value both its type and
        its precision.

        Parameters
        ----------
        ax : Axes
            The matplotlib axes object
        axis : str
            ``"x"`` or ``"y"``

        Returns
        -------
        Dict[float, str]
            Tick coordinate to label, or an empty mapping on a numeric axis
        """
        holder = ax.xaxis if axis == "x" else ax.yaxis
        if not isinstance(holder.units, UnitData):
            return {}

        positions = ax.get_xticks() if axis == "x" else ax.get_yticks()
        labels = ax.get_xticklabels() if axis == "x" else ax.get_yticklabels()
        return {
            float(pos): label.get_text()
            for pos, label in zip(positions, labels)
            if label.get_text()
        }

    @staticmethod
    def _named_coordinate(
        coordinate: float, tick_labels: Dict[float, str]
    ) -> Union[str, float]:
        """
        Name one coordinate after the tick it was drawn on, when there is one.

        A string-category axis puts its groups on consecutive integers, so a
        point drawn *off* one is a group a ``dodge`` shifted aside to make room
        for its neighbour -- still that group, and still named by the tick it
        was moved from. Rounding recovers the name; without it a dodged series
        announces "-0.025" where the chart says "Thur".

        ``tick_labels`` is empty on a numeric axis, so the same rounding cannot
        rename a measurement after whichever tick it happens to fall nearest.

        Parameters
        ----------
        coordinate : float
            The drawn coordinate
        tick_labels : Dict[float, str]
            The axis's tick names, from :meth:`_category_tick_labels`

        Returns
        -------
        Union[str, float]
            The tick's name, or the coordinate when the axis has none
        """
        if not tick_labels:
            return float(coordinate)

        exact = tick_labels.get(float(coordinate))
        if exact is not None:
            return exact

        nearest = tick_labels.get(float(round(coordinate)))
        return nearest if nearest is not None else float(coordinate)

    @staticmethod
    def extract_line_data_with_categorical_labels(
        ax: Axes, line: Line2D
    ) -> Optional[List[Tuple[Union[str, float], Union[str, float]]]]:
        """
        Extract line data, naming whichever axis carries the categories.

        Categories sit on x in a vertical chart and on y in a horizontal one,
        and the axis that carries them is the one to recover names from. This
        followed x alone, so a horizontal categorical chart announced its
        groups as the positions they were drawn at -- and a dodged one as the
        offsets it was shifted to (#353).

        Parameters
        ----------
        ax : Axes
            The matplotlib axes object
        line : Line2D
            The line object to extract data from

        Returns
        -------
        Optional[List[Tuple[Union[str, float], Union[str, float]]]]
            List of (x, y) tuples, each coordinate being the name written
            beside it on a category axis and the drawn number otherwise
        """
        if ax is None or line is None:
            return None

        xydata = line.get_xydata()
        if xydata is None:
            return None

        # Convert to numpy array for easier handling
        xy_array = np.asarray(xydata)
        if xy_array.size == 0:
            return None

        x_ticks = LineExtractorMixin._category_tick_labels(ax, "x")
        y_ticks = LineExtractorMixin._category_tick_labels(ax, "y")

        return [
            (
                LineExtractorMixin._named_coordinate(x, x_ticks),
                LineExtractorMixin._named_coordinate(y, y_ticks),
            )
            for x, y in xy_array
        ]


class CollectionExtractorMixin:
    @staticmethod
    def extract_collection(ax: Axes, collection_type: type) -> Any:
        """
        Retrieve the first collection of a specified type from an Axes object.

        Returns ``None`` when the axes holds none of that type, which is what
        its caller is written for: ``ScatterPlot._extract_plot_data`` opens
        with ``if data is None: raise ExtractionError(...)`` and
        ``_extract_point_data`` opens with ``if plot is None``. That handling
        could never run, because the lookup was a bare ``next()`` with no
        default and raised first. What a reader got instead was a
        ``StopIteration`` -- fatal to the whole figure, naming neither the
        plot type nor the artist, and nothing anyone can act on. Measured on
        matplotlib 3.9.4, an axes holding only a line raised it (#529).

        The third of three. ``extract_container`` was the same shape and
        gives the fuller reasoning above, including why a bare
        ``StopIteration`` is never a useful failure; ``extract_scalar_mappable``
        was the second. All three are in this file, and each was found only
        when a chart happened to route into it, which is the argument for the
        last one not waiting for its chart.

        Parameters
        ----------
        ax : Axes
            The axes to read.
        collection_type : type
            The collection class wanted.

        Returns
        -------
        Any
            The first collection of that type, or ``None`` when there is none.
        """
        if ax is None or ax.collections is None:
            return None

        # We assume only one collection of each type is present to avoid plot clutter,
        # even though multiples are technically possible.
        return next(
            (
                collection
                for collection in ax.collections
                if isinstance(collection, collection_type)
            ),
            None,
        )


class ScalarMappableExtractorMixin:
    @staticmethod
    def extract_scalar_mappable(ax: Axes) -> Optional[ScalarMappable]:
        """
        Retrieve the artist a heatmap keeps its grid of values in.

        A heatmap's values live in a mesh or an image. Preferring one matters
        because ``ScalarMappable`` is a much wider net than it looks: a
        scatter's ``PathCollection`` is one too -- that is how a colour-mapped
        scatter works -- so "the first ``ScalarMappable`` on the axes" finds
        the *scatter* whenever one was drawn first, and the heatmap beside it
        is then read from an artist that has no grid at all::

            sns.scatterplot(...); ax.pcolormesh(...)
            ExtractionError: ... from <class 'matplotlib.collections.PathCollection'>

        Falls back to the first mappable of any kind, so a mesh subclass this
        does not name is still found rather than newly refused.

        Returns ``None`` on an axes holding none, which is the ``Optional``
        this has always been annotated with and what ``HeatPlot`` is written
        for -- it opens with ``if data is None``. Reaching that answer through
        a bare ``next()`` raised ``StopIteration`` instead, fatal to the whole
        figure and naming nothing, which is the shape of failure #388 removed
        from ``extract_container`` for the same reason.

        Parameters
        ----------
        ax : Axes
            The axes to search.

        Returns
        -------
        ScalarMappable or None
            The mesh or image if there is one, else the first mappable of any
            kind, else None.
        """
        if ax is None or ax.get_children() is None:
            return None

        mappables = [
            child for child in ax.get_children() if isinstance(child, ScalarMappable)
        ]
        grids = [
            mappable
            for mappable in mappables
            if isinstance(mappable, (QuadMesh, PolyQuadMesh, AxesImage))
        ]
        if grids:
            return grids[0]
        return mappables[0] if mappables else None
