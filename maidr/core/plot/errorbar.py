from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.container import ErrorbarContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import ContainerExtractorMixin, DictMergerMixin


class ErrorBarPlot(MaidrPlot, ContainerExtractorMixin, DictMergerMixin):
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

    Parameters
    ----------
    ax : Axes
        The axes the error bars were drawn on.
    **kwargs
        ``container`` is the ``ErrorbarContainer`` the patched call returned;
        ``x`` and ``y`` are the centre coordinates the caller passed, used
        only when the container carries no data line.

    See Also
    --------
    MaidrPlot : The base class for MAIDR plot data objects.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
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

        Returns
        -------
        dict
            The MAIDR layer schema.
        """
        base_schema = super().render()
        return self.merge_dict(
            base_schema, {MaidrKey.ORIENTATION: self._orientation}
        )

    def _extract_plot_data(self) -> list[dict]:
        container = self._resolve_container()
        if container is None:
            raise ExtractionError(self.type, self.ax)

        # `has_yerr` decides the value axis, and an errorbar carrying neither
        # is still a legitimate call -- it draws bare points -- so it reads as
        # vertical rather than as a failure.
        is_vertical = bool(container.has_yerr) or not bool(container.has_xerr)
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

        data = []
        for index, (category, value) in enumerate(zip(categories, values)):
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

    def _resolve_container(self) -> ErrorbarContainer | None:
        """
        Return the container to describe.

        Returns
        -------
        ErrorbarContainer or None
            The container the patch supplied, falling back to the first one on
            the axes, or None when the axes carries none.
        """
        if self._container is not None:
            return self._container

        containers = self.extract_container(
            self.ax, ErrorbarContainer, include_all=True
        )
        return containers[0] if containers else None

    def _extract_centers(
        self, container: ErrorbarContainer
    ) -> tuple[Sequence, Sequence] | None:
        """
        Return the estimate coordinates the bars are centred on.

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
        # the container has no data line to read. The centres are genuinely
        # unrecoverable from the geometry -- an asymmetric bar is not centred
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
        Convert one coordinate to a JSON-serialisable scalar.

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
