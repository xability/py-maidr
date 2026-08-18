from __future__ import annotations

from typing import Sequence

import numpy as np
from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.lines import Line2D

from maidr.core.enum import MaidrKey
from maidr.core.plot.errorbar import ErrorBarPlot, _is_drawn
from maidr.exception import ExtractionError


class PointPlot(ErrorBarPlot):
    """
    A seaborn point plot: a group estimate drawn with the interval around it.

    ``sns.pointplot`` renders the same quantity ``Axes.errorbar`` does, and the
    reader needs the same thing from it -- whether two group means differ is
    answered by whether their intervals overlap -- so it emits the same layer
    type and this class extends :class:`ErrorBarPlot` rather than restating
    it. What differs is only where the numbers are read from: seaborn draws no
    ``ErrorbarContainer`` at all, but one ``Line2D`` per group, so none of the
    container machinery in the base class applies.

    Each interval line is a polyline the caller's ``capsize`` decides the shape
    of: two points when it is zero, and eight -- lower cap, spine, upper cap,
    NaN-separated -- when it is not. Both forms are read the same way, by
    taking the extremes along the value axis, because a cap is drawn *at* the
    bound it marks.

    Before this existed, a point plot was not merely missing its intervals: the
    interval polylines reached the reader as data. A four-category chart
    announced five series, four of them cap geometry with NaN coordinates and
    raw category offsets like 1.95 among the category names -- so the fix is as
    much a removal as an addition.

    Parameters
    ----------
    ax : Axes
        The axes the point plot was drawn on.
    **kwargs
        ``estimate`` is the ``Line2D`` carrying the group estimates, and
        ``intervals`` the per-group interval lines in category order. The
        patch resolves both and verifies they pair up before constructing
        this.

    See Also
    --------
    ErrorBarPlot : The base class, which reads an ``ErrorbarContainer``.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._estimate: Line2D | None = kwargs.pop("estimate", None)
        self._intervals: list[Line2D] = list(kwargs.pop("intervals", []))
        #: One estimate line per ``hue`` group, in the order seaborn drew
        #: them. Empty for an ungrouped chart, which keeps ``_estimate``.
        self._estimates: list[Line2D] = list(kwargs.pop("estimates", []))
        #: The name of each group, from the legend, parallel to
        #: ``_estimates``.
        self._groups: list[str] = list(kwargs.pop("groups", []))

        super().__init__(ax, **kwargs)

    def _extract_plot_data(self) -> list[dict] | list[list[dict]]:
        if self._estimates:
            return self._extract_grouped()
        return self._extract_single()

    def _extract_grouped(self) -> list[list[dict]]:
        """
        Describe a ``hue``-split chart as one series per group.

        The grouped ``error_bar`` shape -- ``ErrorBarPoint[][]`` with a ``z``
        on each point -- arrived in maidr 4.4.0 (xability/maidr#942). Before
        it, the layer carried a single flat series with no field naming the
        group, so a hued chart's intervals had nowhere to go and were dropped
        rather than mis-assigned: the reader got the means of a chart drawn to
        show the uncertainty around them (#462).

        Seaborn draws the interval polylines **estimate-major** -- every
        category of the first group, then every category of the second --
        which is the order the consumer wants its rows in, so each group
        takes a contiguous slice. Verified against the drawn geometry rather
        than assumed: each estimate's value falls inside the span of the
        interval its slice pairs it with.

        Returns
        -------
        list of list of dict
            A series per group, each point carrying ``z``.
        """
        is_vertical = self._is_vertical()
        self._orientation = "vert" if is_vertical else "horz"
        labels = self._category_labels(is_vertical)

        # Cleared for the reason `_extract_single` records, and filled
        # group-major so each group's rows take that group's slice. Handing
        # every row the whole list would light a second group's whips while
        # the cursor was in the first.
        self._elements.clear()

        # `_pairs_up` establishes that the intervals divide evenly among the
        # estimates, and the patch will not construct this type unless it
        # does. Checked here anyway: the invariant lives in another file, so
        # a caller constructing `PointPlot` directly -- or a future change to
        # the patch -- would otherwise mis-slice in silence, handing one
        # group another's bounds. That is the exact failure the `line`
        # fallback existed to prevent, and this module raises rather than
        # guesses everywhere else.
        if len(self._intervals) % len(self._estimates):
            raise ExtractionError(self.type, self.ax)

        per_group = len(self._intervals) // len(self._estimates)
        # All the groups are named or none is, so a layer never declares an
        # `axes.z` that some of its series do not carry. `_extract_axes_data`
        # reads the same predicate.
        named = self._named_groups()
        series: list[list[dict]] = []

        for index, estimate in enumerate(self._estimates):
            intervals = self._intervals[index * per_group : (index + 1) * per_group]
            group = self._groups[index] if named else ""
            points = self._points_of(estimate, intervals, is_vertical, labels, group)
            if not points:
                raise ExtractionError(self.type, self.ax)
            series.append(points)

        # No `if not series` guard here, deliberately: `_extract_plot_data`
        # routes to this method only when `_estimates` is non-empty, and
        # every iteration either appends or raises -- so an empty `series`
        # has no way to occur. A check that cannot fire is worse than none;
        # it sends a reader looking for the case that produces it.
        if len(self._elements) != sum(len(points) for points in series):
            # Same contract as the ungrouped path: one element per point or
            # no selector at all.
            self._elements.clear()
            self._support_highlighting = False

        return series

    def _points_of(
        self,
        estimate: Line2D,
        intervals: list[Line2D],
        is_vertical: bool,
        labels: dict[float, str],
        group: str,
    ) -> list[dict]:
        """
        Read one estimate line and the intervals drawn around it.

        Split out of ``_extract_single`` so the grouped path reads each of
        its series the same way rather than restating the pairing, the
        category labelling and the dodge-rounding independently.

        Parameters
        ----------
        estimate : Line2D
            The line carrying this group's estimates.
        intervals : list of Line2D
            This group's interval polylines, in category order.
        is_vertical : bool
            Whether the categories run along x.
        labels : dict
            Category coordinate to drawn name.
        group : str
            The group's name, emitted as ``z``. Empty for an ungrouped
            chart, which omits the key entirely.

        Returns
        -------
        list of dict
            One point per category.
        """
        xs, ys = estimate.get_data()
        if len(xs) != len(intervals):
            raise ExtractionError(self.type, self.ax)

        # The category runs along the axis the intervals do NOT span. The
        # schema names them `x` and `y` in both orientations and lets
        # `orientation` say which is on screen where -- see `ErrorBarPlot`,
        # whose docstring explains why this differs from how a bar travels.
        categories, values = (xs, ys) if is_vertical else (ys, xs)

        points = []
        for category, value, interval in zip(categories, values, intervals):
            coordinate = float(category)
            bounds = self._interval_bounds(interval, is_vertical)
            # Rounded as well as exact: a `dodge` shifts a group aside from
            # the tick that names it, and the group is still that group.
            label = labels.get(coordinate) or labels.get(float(round(coordinate)))
            point = {
                MaidrKey.X: label if label is not None else self._scalar(category),
                # `None`, not the raw NaN, where seaborn padded a hue level
                # missing from one category. The padding has a real position
                # and no measurement, and `null` is how the core has said
                # that since maidr 4.3.0 -- it sounds as the empty tone and
                # announces as "missing". A bare NaN stops the chart
                # initialising at all, since it is not JSON (#429), and a
                # zero would claim a reading of zero. Same rule
                # `MultiLinePlot._reading` applies, and this path inherited
                # the case from it along with the intervals (#462).
                MaidrKey.Y: self._scalar(value) if _is_drawn(value) else None,
            }
            if group:
                point[MaidrKey.Z] = group
            if bounds is not None:
                point[MaidrKey.Y_MIN], point[MaidrKey.Y_MAX] = bounds
                # Tag for highlighting only the intervals that produced a
                # bound. One path per sample, in the order the points are
                # emitted, which is the shape the consumer repeats across its
                # three sections.
                self._elements.append(interval)
            points.append(point)

        return points

    def _extract_single(self) -> list[dict]:
        if self._estimate is None or not self._intervals:
            raise ExtractionError(self.type, self.ax)

        is_vertical = self._is_vertical()
        self._orientation = "vert" if is_vertical else "horz"

        # Cleared rather than appended to. A layer is rendered more than once
        # -- `set_id` renders again when the schema is not yet cached -- and
        # the tagged elements have to stay one per point, in point order, or
        # the consumer highlights the wrong group.
        self._elements.clear()

        labels = self._category_labels(is_vertical)
        data = self._points_of(
            self._estimate, self._intervals, is_vertical, labels, ""
        )

        if not data:
            raise ExtractionError(self.type, self.ax)

        if len(self._elements) != len(data):
            # The consumer resolves the selector to one element per point, in
            # point order, and discards the result outright when the count
            # disagrees. A chart where only some groups have an interval --
            # ordinary imbalanced data, where one category holds a single
            # observation -- would therefore emit a selector that resolves
            # short and silently highlights nothing at all.
            #
            # Better to say so: the layer promises a selector only when it can
            # deliver one element for every point, and the announcement, which
            # is the reading, is unaffected either way.
            self._elements.clear()
            self._support_highlighting = False

        return data

    def _extract_axes_data(self) -> dict:
        """
        Add a ``z`` axis naming the grouping variable, when there is one.

        Taken from the legend title, which is the ``hue`` column's name --
        the same source ``MultiLinePlot`` uses, so a chart grouped by
        treatment says "Treatment" rather than "Group". Omitted for an
        ungrouped chart, which has nothing to name.

        Also omitted when the groups themselves could not be named. The two
        have to agree: declaring a ``z`` axis while some series carry no
        ``z`` is a shape the consumer has no reading for, and it is reachable
        whenever the legend does not list exactly one entry per drawn group.
        Either the whole layer is grouped-and-named or none of it is.

        Returns
        -------
        dict
            The per-axis ``AxisConfig`` mapping.
        """
        axes_data = super()._extract_axes_data()

        if not self._estimates or not self._named_groups():
            return axes_data

        z_label = self._legend_title()
        if z_label:
            axes_data[MaidrKey.Z] = self._axis_config(label=z_label)

        return axes_data

    def _named_groups(self) -> bool:
        """
        Whether every drawn group has a name to emit as ``z``.

        Returns
        -------
        bool
            True when the patch supplied one name per estimate.
        """
        return len(self._groups) == len(self._estimates) and all(self._groups)

    def _is_vertical(self) -> bool:
        """
        Decide which axis the categories run along.

        Read from the axes rather than from the caller's ``orient``, which is
        usually absent: seaborn infers the orientation from which variable is
        categorical and does not report what it decided. Two signals do report
        it, in order of authority:

        1. Seaborn draws its categorical axis through matplotlib's string-
           category machinery, which leaves ``UnitData`` on that axis and
           nothing on the other. That holds whatever the category *values*
           are -- a numeric grouping column still travels this way -- so it
           is the whole answer whenever it fires.
        2. Under ``native_scale=True`` the category axis is an ordinary
           numeric one and signal 1 is silent. Then the intervals themselves
           say it: an interval spans the value axis and, at the default
           ``capsize=0``, occupies a single coordinate on the category axis.

        Returns
        -------
        bool
            True when the categories run along x, which is seaborn's default
            and the answer when neither signal fires.
        """
        x_is_category = self.ax.xaxis.units is not None
        y_is_category = self.ax.yaxis.units is not None
        if x_is_category != y_is_category:
            return x_is_category

        x_flat = all(self._extent(line.get_xdata()) == 0 for line in self._intervals)
        y_flat = all(self._extent(line.get_ydata()) == 0 for line in self._intervals)
        if x_flat != y_flat:
            return x_flat

        return True

    def _category_labels(self, is_vertical: bool) -> dict[float, str]:
        """
        Map category coordinates to the names drawn beside them.

        Seaborn places the groups at 0, 1, 2, ... and writes their names on
        the ticks, so without this the reader hears the positions instead of
        the groups -- "0" where the chart says "Thur".

        Parameters
        ----------
        is_vertical : bool
            Whether the categories run along x.

        Returns
        -------
        dict
            Coordinate to label, for the labelled ticks only.
        """
        axis: Axis = self.ax.xaxis if is_vertical else self.ax.yaxis
        if axis.units is None:
            # A numeric axis under `native_scale=True`. Its tick labels are
            # renderings of the coordinates rather than names, and returning
            # them would replace a group's value with whatever rounding the
            # tick formatter happened to apply.
            return {}

        labels = {}
        for position, tick in zip(axis.get_ticklocs(), axis.get_ticklabels()):
            text = tick.get_text()
            if text:
                labels[float(position)] = text
        return labels

    @staticmethod
    def _interval_bounds(line: Line2D, is_vertical: bool) -> tuple[float, float] | None:
        """
        Return the ends of one interval along the value axis.

        Taking the extremes rather than a designated pair of vertices is what
        makes ``capsize`` irrelevant here: a cap is drawn at the bound it
        marks, so the polyline's furthest points along the value axis are the
        bounds whether the shape has two vertices or eight.

        Parameters
        ----------
        line : Line2D
            The polyline drawing one group's interval.
        is_vertical : bool
            Whether the value axis is y.

        Returns
        -------
        tuple of float, or None
            The lower and upper bound, or None when the group has no interval
            -- a single observation has nothing to estimate one from, and
            seaborn draws it as an empty line rather than as a zero-width one.
        """
        values = np.asarray(
            line.get_ydata() if is_vertical else line.get_xdata(), dtype=float
        )
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            return None

        # Cleaned the same way `ErrorBarPlot` cleans its own bounds, and for
        # the same reason: a bound is computed rather than authored, and
        # `5 - 4.0497` is not exactly representable. Reusing the base class's
        # helper rather than restating the rule keeps the two from drifting to
        # different precisions for the same quantity.
        return (
            ErrorBarPlot._without_float_noise(float(finite.min())),
            ErrorBarPlot._without_float_noise(float(finite.max())),
        )

    @staticmethod
    def _extent(coordinates: Sequence) -> float:
        """
        Return how far a polyline reaches along one axis, ignoring gaps.

        Parameters
        ----------
        coordinates : sequence
            One axis of a polyline's vertices, possibly holding the NaNs that
            separate a capped interval's three segments.

        Returns
        -------
        float
            The distance between the extremes, or 0 when nothing is finite.
        """
        values = np.asarray(coordinates, dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            # NaN rather than 0: a polyline with nothing finite on this axis is
            # not *flat* along it, it is absent from it, and the caller reads a
            # zero extent as evidence that this is the category axis. Answering
            # 0 here made a chart whose intervals carried no value at all look
            # like a chart drawn the other way round.
            return float("nan")

        return float(finite.max() - finite.min())
