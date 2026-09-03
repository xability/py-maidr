from __future__ import annotations

import uuid
from typing import Any, Sequence

import numpy as np
from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.plot.lineplot import _has_position, _reading
from maidr.exception import ExtractionError


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

        data: list[list[dict]] = []
        for index, values in enumerate(self._series):
            magnitudes = np.atleast_1d(np.asarray(values))
            if len(magnitudes) != len(positions):
                raise ExtractionError(self.type, self.ax)

            label = self._labels[index] if index < len(self._labels) else None
            points = []
            for position, magnitude in zip(positions, magnitudes):
                # The line layer's two rules, for the reason it gives: a
                # sample with no *position* is nowhere a reader could be
                # sent and is dropped -- from every series, since the
                # positions are shared, so the columns the consumer sums
                # stay aligned -- while one with a position and no *value*
                # is kept and emitted as `null`, which the core's area trace
                # reads as a gap that stays out of the running total. Either
                # written out as a bare `NaN` stops the chart initialising
                # (#427).
                x = self._scalar(position)
                if not _has_position(x):
                    continue
                point = {MaidrKey.X: x, MaidrKey.Y: _reading(self._scalar(magnitude))}
                if label:
                    point[MaidrKey.Z] = str(label)
                points.append(point)

            data.append(points)
            if index < len(self._collections):
                collection = self._collections[index]
                # Assigned here rather than relied upon: a gid is otherwise
                # only stamped at draw time, and the schema is built first.
                # `MultiLinePlot` does the same for the same reason.
                if collection.get_gid() is None:
                    collection.set_gid(f"maidr-{uuid.uuid4()}")
                self._elements.append(collection)

        if len(self._elements) != len(data):
            # The consumer resolves the selector to one element per series and
            # discards the result outright when the count disagrees, so a
            # partial list would emit a selector that silently highlights
            # nothing. Saying so is better than promising it.
            self._elements.clear()
            self._support_highlighting = False

        return data

    def _get_selector(self) -> list[str]:
        """
        Return one selector per drawn band, in series order.

        Parameters
        ----------
        None

        Only reached when every series was tagged: extraction clears the flag
        otherwise, so this never has to describe a partial list.

        Returns
        -------
        list of str
            One selector per band.
        """
        return [f"g[id='{element.get_gid()}'] path" for element in self._elements]

    @staticmethod
    def _scalar(value: Any) -> Any:
        """
        Convert one coordinate to a JSON-serialisable scalar.

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
        is a stacked area drawn around a floating centre and reads as one.

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
