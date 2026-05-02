from __future__ import annotations

import numpy as np
import numpy.ma as ma
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import CollectionExtractorMixin


class ScatterPlot(MaidrPlot, CollectionExtractorMixin):
    def __init__(self, ax: Axes) -> None:
        super().__init__(ax, PlotType.SCATTER)

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
        y_label = self.ax.get_ylabel() or "Y"

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

        return [
            {
                MaidrKey.X: float(x),
                MaidrKey.Y: float(y),
            }
            for x, y in ma.getdata(plot.get_offsets())
        ]
