from __future__ import annotations

import math

from typing import Any, Sequence

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.container import ErrorbarContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.plot.maidr_plot import group_name_of
from maidr.exception import ExtractionError
from maidr.util.mixin import DictMergerMixin


def _is_drawn(value: object) -> bool:
    """
    Whether matplotlib put this coordinate anywhere.

    A non-finite number has no position, so nothing is rendered for it.
    Anything ``math.isfinite`` cannot judge is a categorical coordinate,
    which is always drawn and is never a JSON hazard.

    Parameters
    ----------
    value : object
        A coordinate as read off the container.

    Returns
    -------
    bool
        False only for a number that is NaN or infinite.
    """
    try:
        return math.isfinite(value)  # type: ignore[arg-type]
    except TypeError:
        return True


def _plain_array(column: Any) -> bool:
    """
    Whether a column of centers is a plain 1-D array of floats or integers.

    Exactly ``np.ndarray``, never a subclass: a masked array iterates its
    masked samples as ``np.ma.masked``, which the per-sample loop reads as
    drawn, where ``astype`` would hand over the value under the mask.
    Booleans and floats wider than 64 bits are left to the loop too.

    Centers passed as lists reach the data line as an object array, and are
    read in bulk only when every value is exactly a Python ``float`` or
    ``int``, or a ``np.float64`` or ``np.int64`` -- what ``list()`` of an
    array holds. The type is told by identity, never by hashing it or
    comparing it with ``==``, which a metaclass can answer as it likes: a
    string, a date, a bool, ``None`` or a ``Decimal`` keeps the loop, where
    :meth:`_scalar` reads it.
    """
    if type(column) is not np.ndarray or column.ndim != 1:
        return False
    kind = column.dtype.kind
    if kind in "fiu":
        return column.dtype.itemsize <= 8
    if kind == "O":
        return all(map(_is_plain_number_type, map(type, column.tolist())))
    return False


def _is_plain_number_type(kind: type) -> bool:
    """Whether a value of this exact type is a number ``float()`` reads as is."""
    return kind is float or kind is int or kind is np.float64 or kind is np.int64


def _segment_bounds(segments: list, count: int, component: int) -> list | None:
    """
    Each sample's interval, as :meth:`ErrorBarPlot._extract_bounds` reads it,
    before the float noise is taken off.

    Read for every segment at once when each one a sample has is a two-point
    segment, which is what ``LineCollection.get_segments`` returns for a bar
    with both ends drawn. ``min([a, b])`` keeps ``a`` unless ``b < a`` and
    ``max([a, b])`` keeps ``a`` unless ``b > a``, so ``np.where`` picks the
    same endpoint even between ``0.0`` and ``-0.0``.

    Parameters
    ----------
    segments : list
        The drawn bar segments, one per sample.
    count : int
        How many samples there are.
    component : int
        0 to read x, 1 to read y.

    Returns
    -------
    list or None
        One ``(low, high)`` per sample that has a segment, ``None`` for one
        whose ends are not both finite; or ``None`` for the whole column when
        a segment is anything but two points -- a bar NaN removed an end
        from, say -- which reads every sample through ``_extract_bounds``.
    """
    bounded = min(count, len(segments))
    if not bounded:
        return []
    try:
        ends = np.asarray(segments[:bounded], dtype=float)
    except (TypeError, ValueError):
        return None
    if ends.shape != (bounded, 2, 2):
        return None
    first = ends[:, 0, component]
    second = ends[:, 1, component]
    finite = (np.isfinite(first) & np.isfinite(second)).tolist()
    lows = np.where(second < first, second, first).tolist()
    highs = np.where(second > first, second, first).tolist()
    return [(low, high) if ok else None for ok, low, high in zip(finite, lows, highs)]


class ErrorBarPlot(MaidrPlot, DictMergerMixin):
    """
    A plot that draws an estimate together with the interval around it.

    Uncertainty is not decoration in a statistical graphic; it is frequently
    the finding. Whether two group means differ is answered by whether their
    intervals overlap, and before this existed a MAIDR reader got the estimate
    and nothing else, so the comparison the chart was drawn to support could
    not be made at all.

    The bounds are read off the **drawn geometry** rather than recomputed from
    the ``yerr`` the caller passed. Those are not the same quantity:
    matplotlib takes an *offset* while the MAIDR schema carries an *absolute
    position*, and the offset form has three shapes -- scalar, ``(N,)``, and
    ``(2, N)`` -- before ``uplims``/``lolims`` change what the bar means again.
    The ``LineCollection`` matplotlib actually rendered has already resolved
    every one of those into two endpoints, so reading it is both shorter and
    correct for cases this module would otherwise have to enumerate.

    Note that ``x`` and ``y`` mean *category* and *magnitude* here in both
    orientations, which is **not** how ``BarPlot`` and ``HistPlot`` travel --
    they emit screen-aligned keys that swap with orientation. The difference
    is not an oversight: the shape is set by the consumer, and ``ErrorBarTrace``
    reads the magnitude as ``y``/``yMin``/``yMax`` with no orientation branch,
    while ``ErrorBarPoint`` declares no ``xMin``/``xMax`` to hold a bound.
    Emitting the bar convention would leave a horizontal chart with no interval
    at all.

    Parameters
    ----------
    ax : Axes
        The axes the error bars were drawn on.
    **kwargs
        ``container`` is the ``ErrorbarContainer`` the patched call returned;
        ``x`` and ``y`` are the center coordinates the caller passed, used
        only when the container carries no data line.

    See Also
    --------
    MaidrPlot : The base class for MAIDR plot data objects.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        # The hue group these estimates belong to, when the patch could name
        # it. `lmplot(x_estimator=..., hue=...)` draws one estimate-and-band
        # per level and the curve beside it is already named, so leaving this
        # unnamed announced a group and its own uncertainty as unrelated
        # layers (#612). Opted into here rather than read by `MaidrPlot`; see
        # `GROUP_NAME` for why that is per class.
        self._group_name = group_name_of(kwargs)

        super().__init__(ax, PlotType.ERRORBAR)

        # The patch hands over the exact container its call produced. Looking
        # one up on the axes instead would break the moment a figure carries
        # two `errorbar` calls: both layers would find the first container and
        # describe the same series twice, silently losing the second.
        self._container = kwargs.pop("container", None)
        self._fallback_x = kwargs.pop("x", None)
        self._fallback_y = kwargs.pop("y", None)

        # Resolved from the drawn container during extraction, which `render`
        # runs before it reads this.
        self._orientation = "vert"

    def render(self) -> dict:
        """
        Build the layer schema, adding the orientation the bars were drawn in.

        Adds the group's name too, when the chart has one -- the same field,
        and for the same reason, as ``SmoothPlot``: a hue-split ``lmplot``
        draws one band per level, and two of them over one axes with nothing
        to tell them apart leave a reader hearing the identical announcement
        twice.

        Returns
        -------
        dict
            The MAIDR layer schema.
        """
        # `super().render()` runs `_extract_plot_data`, which is what resolves
        # `self._orientation` -- so the read below has to come after it, not
        # alongside it.
        base_schema = super().render()
        added: dict = {MaidrKey.ORIENTATION: self._orientation}

        # A callable is resolved here rather than at registration, which is
        # what an `lmplot` needs: `FacetGrid.add_legend()` runs after every
        # panel is drawn, so the legend that names the colors does not exist
        # when the layer registers (#561, #612).
        name = self._group_name() if callable(self._group_name) else self._group_name
        if name:
            added[MaidrKey.NAME] = name

        return self.merge_dict(base_schema, added)

    def _extract_plot_data(self) -> list[dict]:
        container = self._resolve_container()
        if container is None:
            raise ExtractionError(self.type, self.ax)

        # `has_yerr` decides the value axis, and an errorbar carrying neither
        # is still a legitimate call -- it draws bare points -- so it reads as
        # vertical rather than as a failure.
        is_vertical = container.has_yerr or not container.has_xerr
        self._orientation = "vert" if is_vertical else "horz"

        centers = self._extract_centers(container)
        if centers is None:
            raise ExtractionError(self.type, container)
        xs, ys = centers

        bars = self._extract_interval_bars(container, is_vertical)
        segments = bars.get_segments() if bars is not None else []
        if bars is not None:
            # Tag for highlighting. One path per sample, in data order, which
            # is the shape the JS trace repeats across its three sections.
            self._elements.append(bars)
        else:
            # A call passing no error at all draws bare estimates: there is no
            # bar collection, so nothing carries the `maidr` attribute the
            # selector goes looking for. Leaving the flag set would emit a
            # selector promising highlightable paths that the document does
            # not contain. Cleared the same way `HeatPlot` clears it when the
            # artist is not a mesh.
            self._support_highlighting = False

        # The category runs along the axis the bars do NOT span, and the
        # magnitude along the one they do. The schema names them `x` and `y`
        # in BOTH orientations, and lets `orientation` say which is on screen
        # where.
        #
        # That differs from how a bar or a histogram travels, and deliberately
        # so: the shape is set by the consumer. `ErrorBarTrace` reads the
        # magnitude as `y`/`yMin`/`yMax` with no orientation branch, and
        # `ErrorBarPoint` declares no `xMin`/`xMax` to put a bound in --
        # so emitting the screen-aligned form a bar uses would leave a
        # horizontal chart with no interval at all, which is the one thing the
        # trace type exists to convey.
        categories, values = (xs, ys) if is_vertical else (ys, xs)
        component = 1 if is_vertical else 0

        data = self._numeric_samples(categories, values, segments, component)
        if data is not None:
            if not data:
                raise ExtractionError(self.type, container)
            return data

        data = []
        for index, (category, value) in enumerate(zip(categories, values)):
            # Only the samples matplotlib drew. It renders neither a marker
            # nor a bar for a non-finite estimate, so emitting one leaves the
            # layer longer than the elements the selector resolves to and
            # every sample after it is highlighted at its neighbour's. It also
            # keeps the payload loadable: `json.dumps` writes `NaN` as a bare
            # token, which is legal JavaScript and invalid JSON, and the core
            # parses the SVG's `maidr` attribute with `JSON.parse` (#429).
            #
            # A missing *bound* is a different case and needs nothing here.
            # `_extract_bounds` already returns None for one, the point keeps
            # its estimate, and the interval is simply absent -- an estimate
            # with no interval is a reading, not a gap.
            #
            # `index` goes on counting over every sample, because it addresses
            # the segments matplotlib built for the whole series. Renumbering
            # it against the survivors would pair each remaining estimate with
            # the next one's bounds.
            if not (_is_drawn(category) and _is_drawn(value)):
                continue

            point = {
                MaidrKey.X: self._scalar(category),
                MaidrKey.Y: self._scalar(value),
            }
            bounds = self._extract_bounds(segments, index, component)
            if bounds is not None:
                point[MaidrKey.Y_MIN], point[MaidrKey.Y_MAX] = bounds
            data.append(point)

        if not data:
            raise ExtractionError(self.type, container)

        return data

    @staticmethod
    def _numeric_samples(
        categories: Any, values: Any, segments: list, component: int
    ) -> list[dict] | None:
        """
        The points the per-sample loop makes, read a column at a time.

        For centers that are plain arrays of floats or integers, every step of
        that loop is known for the whole column at once: :func:`_is_drawn` is
        ``np.isfinite``, and :meth:`_scalar` is the value as a Python float,
        which is what ``astype(float).tolist()`` hands over. The loop asked
        both of every sample, and :meth:`_extract_bounds` built a list and
        called ``np.isfinite`` on each endpoint, which on a long series was
        most of the extraction.

        The bounds come from :func:`_segment_bounds`, which reads the drawn
        segments the same way, or one sample at a time through
        :meth:`_extract_bounds` when they are not all two-point segments.

        The points are keyed by the plain strings ``MaidrKey`` members stand
        for. The JSON is the same, and a dict keyed by an enum member is one
        the garbage collector has to track -- one per sample here.

        Parameters
        ----------
        categories, values : Any
            The centers along the category and the value axis.
        segments : list
            The drawn bar segments, one per sample.
        component : int
            0 to read the bounds off x, 1 off y.

        Returns
        -------
        list of dict or None
            The points, or ``None`` when either column is anything but a plain
            1-D array of floats or integers -- a masked array, dates, strings
            or booleans -- or the two differ in length, which keeps the
            per-sample loop.
        """
        if not (_plain_array(categories) and _plain_array(values)):
            return None
        count = len(categories)
        if len(values) != count:
            return None
        try:
            across = categories.astype(float)
            along = values.astype(float)
        except OverflowError:
            # An integer beyond the float range. The loop raises on it, as
            # it always has.
            return None
        drawn = (np.isfinite(across) & np.isfinite(along)).tolist()
        across, along = across.tolist(), along.tolist()
        bounds = _segment_bounds(segments, count, component)
        kx, ky = MaidrKey.X.value, MaidrKey.Y.value
        kmin, kmax = MaidrKey.Y_MIN.value, MaidrKey.Y_MAX.value
        noise = ErrorBarPlot._without_float_noise
        data = []
        for index in range(count):
            # Only the samples matplotlib drew, and `index` still counts every
            # sample, as in the per-sample loop.
            if not drawn[index]:
                continue
            point = {kx: across[index], ky: along[index]}
            if bounds is None:
                read = ErrorBarPlot._extract_bounds(segments, index, component)
                if read is not None:
                    point[kmin], point[kmax] = read
            elif index < len(bounds) and bounds[index] is not None:
                low, high = bounds[index]
                point[kmin], point[kmax] = noise(low), noise(high)
            data.append(point)
        return data

    def _resolve_container(self) -> ErrorbarContainer | None:
        """
        Return the container to describe.

        There is deliberately no fallback to "the first container on the
        axes". That lookup is precisely the bug this class is built to avoid:
        a figure with two ``errorbar`` calls carries two containers, and both
        layers searching for one would find the first, describing one series
        twice and losing the other with no error to say so. Falling back to it
        when the patch has not supplied a container would reintroduce that
        silently on any future path that constructed this class directly.

        Returns
        -------
        ErrorbarContainer or None
            The container the patched call supplied, or None when there is
            none -- which the caller turns into an ``ExtractionError`` rather
            than guessing.
        """
        return self._container

    def _extract_centers(
        self, container: ErrorbarContainer
    ) -> tuple[Sequence, Sequence] | None:
        """
        Return the estimate coordinates the bars are centered on.

        Parameters
        ----------
        container : ErrorbarContainer
            The container to read.

        Returns
        -------
        tuple of sequence, or None
            The x and y coordinates, or None when neither the container nor
            the caller's arguments supply them.
        """
        data_line = container.lines[0]
        if data_line is not None:
            x_data, y_data = data_line.get_data()
            return x_data, y_data

        # `fmt="none"` draws the intervals without the estimate markers, so
        # the container has no data line to read. The centers are genuinely
        # unrecoverable from the geometry -- an asymmetric bar is not centered
        # on its own midpoint -- so they come from the arguments the caller
        # passed, which the patch kept for exactly this case.
        if self._fallback_x is None or self._fallback_y is None:
            return None
        return np.atleast_1d(self._fallback_x), np.atleast_1d(self._fallback_y)

    @staticmethod
    def _extract_interval_bars(
        container: ErrorbarContainer, is_vertical: bool
    ) -> LineCollection | None:
        """
        Return the collection drawing the interval along the value axis.

        A call passing both ``xerr`` and ``yerr`` renders two collections, x
        first and then y. Only one interval fits the schema, so the value axis
        picks the collection and the other is left undescribed.

        Parameters
        ----------
        container : ErrorbarContainer
            The container to read.
        is_vertical : bool
            Whether the value axis is y.

        Returns
        -------
        LineCollection or None
            The collection spanning the value axis, or None when the call
            passed no error at all.
        """
        bar_collections = container.lines[2]
        if not bar_collections:
            return None

        if container.has_xerr and container.has_yerr:
            return bar_collections[1] if is_vertical else bar_collections[0]
        return bar_collections[0]

    @staticmethod
    def _extract_bounds(
        segments: list, index: int, component: int
    ) -> tuple[float, float] | None:
        """
        Return one sample's interval endpoints, low then high.

        Parameters
        ----------
        segments : list
            The drawn bar segments, one per sample.
        index : int
            Which sample to read.
        component : int
            0 to read the x coordinate of each endpoint, 1 to read y.

        Returns
        -------
        tuple of float, or None
            The lower and upper bound, or None when this sample has no bar.
        """
        if index >= len(segments):
            return None

        segment = segments[index]
        # A NaN error drops that one sample's bar to an empty segment while
        # keeping its position in the list, so the sample still lines up with
        # its neighbours -- but there is no endpoint to read. Emitting no
        # bounds is what the JS trace treats as "this sample has none".
        if len(segment) == 0:
            return None

        magnitudes = [float(point[component]) for point in segment]
        if not all(np.isfinite(magnitude) for magnitude in magnitudes):
            return None

        return (
            ErrorBarPlot._without_float_noise(min(magnitudes)),
            ErrorBarPlot._without_float_noise(max(magnitudes)),
        )

    @staticmethod
    def _without_float_noise(value: float) -> float:
        """
        Strip binary floating-point noise from a derived bound.

        A bound is not authored, it is computed: matplotlib draws the bar at
        ``y - err``, and ``4.2 - 0.4`` is ``3.8000000000000003`` in IEEE 754.
        The estimate itself is left exact because nothing subtracted it -- only
        the endpoints arithmetic touched are cleaned.

        Twelve significant figures rather than a fixed number of decimals,
        because the decimals a chart needs depend on its scale: rounding to two
        would report a bound of 0.003 as zero, which is a worse answer than the
        noise it was meant to remove.

        Parameters
        ----------
        value : float
            A bound obtained from the drawn geometry.

        Returns
        -------
        float
            The same bound without the trailing artifact.
        """
        return float(f"{value:.12g}")

    @staticmethod
    def _scalar(value: Any) -> Any:
        """
        Convert one coordinate to a JSON-serializable scalar.

        Parameters
        ----------
        value : Any
            A coordinate read off a matplotlib artist.

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
            # A date axis is the case that reaches here: `ax.errorbar(dates,
            # ...)` is ordinary on a time series, and matplotlib hands the
            # dates back as `datetime` objects rather than as the ordinals it
            # drew. Raising would take out the user's whole figure over an axis
            # matplotlib is perfectly happy with, so the label travels as a
            # string -- which the schema allows for `x`, and which reads better
            # than the bare ordinal a scatter emits.
            return str(value)
