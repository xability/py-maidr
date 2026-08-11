from __future__ import annotations

from typing import Sequence

import numpy as np
from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.lines import Line2D

from maidr.core.enum import MaidrKey
from maidr.core.plot.errorbar import ErrorBarPlot
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

        super().__init__(ax, **kwargs)

    def _extract_plot_data(self) -> list[dict]:
        if self._estimate is None or not self._intervals:
            raise ExtractionError(self.type, self.ax)

        xs, ys = self._estimate.get_data()
        if len(xs) != len(self._intervals):
            raise ExtractionError(self.type, self.ax)

        is_vertical = self._is_vertical()
        self._orientation = "vert" if is_vertical else "horz"

        # Cleared rather than appended to. A layer is rendered more than once
        # -- `set_id` renders again when the schema is not yet cached -- and
        # the tagged elements have to stay one per point, in point order, or
        # the consumer highlights the wrong group.
        self._elements.clear()

        # The category runs along the axis the intervals do NOT span. The
        # schema names them `x` and `y` in both orientations and lets
        # `orientation` say which is on screen where -- see `ErrorBarPlot`,
        # whose docstring explains why this differs from how a bar travels.
        categories, values = (xs, ys) if is_vertical else (ys, xs)
        labels = self._category_labels(is_vertical)

        data = []
        for category, value, interval in zip(categories, values, self._intervals):
            coordinate = float(category)
            bounds = self._interval_bounds(interval, is_vertical)
            # Rounded as well as exact: a `dodge` shifts a group aside from
            # the tick that names it, and the group is still that group.
            label = labels.get(coordinate) or labels.get(float(round(coordinate)))
            point = {
                MaidrKey.X: label if label is not None else self._scalar(category),
                MaidrKey.Y: self._scalar(value),
            }
            if bounds is not None:
                point[MaidrKey.Y_MIN], point[MaidrKey.Y_MAX] = bounds
                # Tag for highlighting only the intervals that produced a
                # bound. One path per sample, in the order the points are
                # emitted, which is the shape the consumer repeats across its
                # three sections.
                self._elements.append(interval)
            data.append(point)

        if not data:
            raise ExtractionError(self.type, self.ax)

        if not self._elements:
            # Every interval was empty -- a group with a single observation
            # has no interval to draw -- so nothing carries the `maidr`
            # attribute the selector goes looking for, and emitting one would
            # promise highlightable paths the document does not contain.
            self._support_highlighting = False

        return data

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
