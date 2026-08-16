from __future__ import annotations

import math

import numpy as np
import numpy.ma as ma
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import CollectionExtractorMixin, LineExtractorMixin


#: The keyword ``Axes.scatter`` hands its own ``PathCollection`` to this layer
#: under. Named once and imported at both ends rather than spelled twice:
#: ``kwargs.get`` falls back to sweeping the axes on a mismatch, so a typo
#: would not raise -- it would quietly restore the behaviour #426 removed.
#:
#: Lives here rather than beside ``common.drawn_as`` because ``maidr.patch``
#: imports ``maidr.core`` and not the other way about.
DRAWN_POINTS = "_maidr_points"


class ScatterPlot(MaidrPlot, CollectionExtractorMixin, LineExtractorMixin):
    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.SCATTER)
        # The collection this layer's own call drew, when the patch could say.
        # `None` falls back to the first collection on the axes, which is the
        # right answer only while a layer *is* one collection.
        #
        # Guarded on the type rather than on presence: `seaborn.scatterplot`
        # is patched through the same wrapper and returns an `Axes`, not the
        # collection. Falling back is correct there -- measured, it draws a
        # single `PathCollection` of every point even under `hue`, so the
        # sweep finds exactly the right one.
        own_points = kwargs.get(DRAWN_POINTS, None)
        self._own_points = (
            own_points if isinstance(own_points, PathCollection) else None
        )

    def _get_selector(self) -> str | list[str]:
        return ["g[maidr='true'] > g > use"]

    def _extract_axes_data(self) -> dict:
        """Extract axes data as canonical per-axis ``AxisConfig`` objects.

        Always returns per-axis objects with ``label``. When the grid
        navigation preconditions hold (linear scales, uniform ticks, valid
        bounds), ``min``, ``max``, and ``tickStep`` are additionally included
        on both axes. If any precondition fails, those numeric fields are
        omitted on both axes, silently disabling grid navigation while still
        complying with the canonical axes shape.
        """
        # Labels (with fallback matching base class behavior).
        x_label = self.ax.get_xlabel()
        if not x_label:
            x_label = self.extract_shared_xlabel(self.ax)
        if not x_label:
            x_label = "X"
        y_label = self.ax.get_ylabel()
        if not y_label:
            y_label = self.extract_shared_ylabel(self.ax)
        if not y_label:
            y_label = "Y"

        # Axis limits.
        x_min, x_max = self.ax.get_xlim()
        y_min, y_max = self.ax.get_ylim()

        # Tick step from major tick intervals.
        x_tick_step = self._compute_tick_step(self.ax.get_xticks())
        y_tick_step = self._compute_tick_step(self.ax.get_yticks())

        # If grid config is invalid, emit bare AxisConfig objects with labels
        # only (no min/max/tickStep). This keeps the canonical per-axis shape.
        if not self._is_valid_grid_config(
            x_min, x_max, x_tick_step, y_min, y_max, y_tick_step
        ):
            return {
                MaidrKey.X: self._axis_config(label=x_label),
                MaidrKey.Y: self._axis_config(label=y_label),
            }

        return {
            MaidrKey.X: self._axis_config(
                label=x_label,
                min=float(x_min),
                max=float(x_max),
                tick_step=float(x_tick_step),
            ),
            MaidrKey.Y: self._axis_config(
                label=y_label,
                min=float(y_min),
                max=float(y_max),
                tick_step=float(y_tick_step),
            ),
        }

    @staticmethod
    def _compute_tick_step(ticks: np.ndarray) -> float | None:
        """Compute tick step from an array of tick positions.

        Returns the tick interval if ticks are uniformly spaced,
        otherwise returns ``None``.
        """
        if ticks is None or len(ticks) < 2:
            return None
        diffs = np.diff(ticks)
        if np.allclose(diffs, diffs[0]):
            return float(diffs[0])
        return None

    def _is_valid_grid_config(
        self,
        x_min: float,
        x_max: float,
        x_tick_step: float | None,
        y_min: float,
        y_max: float,
        y_tick_step: float | None,
    ) -> bool:
        """Validate that all grid navigation parameters are present and sane.

        Checks per the spec:
        - All 6 numeric values present (not None).
        - min < max for both axes.
        - tickStep > 0 for both axes.
        - tickStep <= (max - min) for both axes (at least 1 bin).
        - Both axes use linear scale.
        """
        # Both axes must be linear scale.
        if self.ax.get_xscale() != "linear" or self.ax.get_yscale() != "linear":
            return False

        # All tick steps must be present.
        if x_tick_step is None or y_tick_step is None:
            return False

        # min < max.
        if x_min >= x_max or y_min >= y_max:
            return False

        # tickStep > 0.
        if x_tick_step <= 0 or y_tick_step <= 0:
            return False

        # tickStep <= range (at least 1 bin).
        if x_tick_step > (x_max - x_min) or y_tick_step > (y_max - y_min):
            return False

        return True

    def _extract_plot_data(self) -> list[dict]:
        plot = self._own_points
        if plot is None:
            plot = self.extract_collection(self.ax, PathCollection)
        data = self._extract_point_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_point_data(self, plot: PathCollection | None) -> list[dict] | None:
        if plot is None or plot.get_offsets() is None:
            return None

        # Tag the elements for highlighting.
        self._elements.append(plot)

        # Only the points matplotlib actually drew. A marker with a non-finite
        # coordinate is not rendered -- there is nowhere to put it -- so
        # emitting one leaves the layer with more entries than the selector
        # resolves to `<use>` elements, and every point after it is highlighted
        # at its neighbour's marker while the last has none left. That is worse
        # than an absent point: the reader is shown a mark that does not
        # correspond to the value being announced, and nothing says so (#429).
        #
        # It is also what keeps the payload loadable. `json.dumps` writes `NaN`
        # as a bare token, which is legal JavaScript and invalid JSON, and the
        # core parses the SVG's `maidr` attribute with `JSON.parse` -- so one
        # of them stops the chart initialising at all (#427).
        #
        # Unlike a bar, a scatter point has nothing left to announce once its
        # position is gone: a bar keeps its category and reports a missing
        # height, while a marker at no coordinates has neither. Dropping is the
        # whole answer here rather than half of one. Masked entries arrive as
        # `NaN` through `getdata`, so they take the same path.
        x_slots = sorted(self._category_tick_labels(self.ax, "x"))
        y_slots = sorted(self._category_tick_labels(self.ax, "y"))

        return [
            {
                MaidrKey.X: self._on_axis(float(x), x_slots),
                MaidrKey.Y: self._on_axis(float(y), y_slots),
            }
            for x, y in ma.getdata(plot.get_offsets())
            if math.isfinite(x) and math.isfinite(y)
        ]

    @staticmethod
    def _on_axis(coordinate: float, slots: list[float]) -> float:
        """
        Where a point sits on its axis, rather than where it was drawn.

        On a category axis the two are not the same. ``sns.stripplot`` scatters
        each point sideways by a random offset so overlapping observations stay
        separable, and ``sns.swarmplot`` runs a packing algorithm to the same
        end. Neither offset is an observation -- both are chosen by the
        renderer, and the jitter is literally random -- but the offset is what
        ``get_offsets`` returns, so it is what was announced. Measured on a
        three-category strip plot::

            {"x": -0.0399..., "y": 0.1257...}
            {"x":  0.0629..., "y": -0.1321...}
            {"x": -0.0739..., "y": 0.6404...}

        against an axis labelled ``g`` whose ticks read ``a``, ``b``, ``c``. A
        reader was given a precise number for a quantity that does not exist,
        where the chart says a name.

        Snapping also restores the chart's shape. ``ScatterTrace`` groups
        points into columns by exact ``x`` equality, so 90 jittered points
        became 90 columns of one point each instead of 3 columns of 30 --
        column navigation stepped through individual observations and never
        through categories.

        This does not put the *name* in the payload: ``ScatterPoint.x`` is
        typed ``number`` in the grammar and the trace subtracts x values to
        sort and to group, so a string there would not survive
        (xability/maidr#927). What it does is stop a rendering artefact being
        reported as a measurement, and put the point on the tick a sighted
        reader sees it against.

        Parameters
        ----------
        coordinate : float
            The drawn coordinate.
        slots : list of float
            Tick coordinates of the category axis, ascending, or empty when
            the axis is numeric.

        Returns
        -------
        float
            The nearest category slot, or the coordinate unchanged on a
            numeric axis -- where the drawn position *is* the value, and
            snapping it would destroy the data.
        """
        if not slots:
            return coordinate

        return min(slots, key=lambda slot: abs(slot - coordinate))
