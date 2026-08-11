from __future__ import annotations

import numpy.ma as ma
from matplotlib.axes import Axes
from matplotlib.cm import ScalarMappable
from matplotlib.collections import PolyQuadMesh, QuadMesh

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import (
    DictMergerMixin,
    LevelExtractorMixin,
    ScalarMappableExtractorMixin,
)


class HeatPlot(
    MaidrPlot, LevelExtractorMixin, ScalarMappableExtractorMixin, DictMergerMixin
):
    def __init__(self, ax: Axes, **kwargs) -> None:
        self._z_label = kwargs.pop("z_label", "Z")
        self._fmt = kwargs.pop("fmt", "")
        super().__init__(ax, PlotType.HEAT)

    def render(self) -> dict:
        base_maidr = super().render()
        heat_maidr = {
            MaidrKey.LABELS: {
                MaidrKey.Z: self._z_label,
            },
        }
        return self.merge_dict(base_maidr, heat_maidr)

    def _extract_axes_data(self) -> dict:
        """
        Extend the base per-axis ``AxisConfig`` mapping with a ``z`` axis
        describing the colormap / fill dimension.

        The base class already supplies ``x`` and ``y`` as ``AxisConfig`` dicts
        (``{"label": ...}``). Here we simply add ``z`` with its label.
        """
        axes_data = super()._extract_axes_data()
        axes_data[MaidrKey.Z] = self._axis_config(label=self._z_label)
        return axes_data

    def _extract_plot_data(self) -> dict:
        plot = self.extract_scalar_mappable(self.ax)
        data = self._extract_scalar_mappable_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        return {
            MaidrKey.POINTS: data,
            MaidrKey.X: self.extract_level(self.ax, MaidrKey.X),
            MaidrKey.Y: self.extract_level(self.ax, MaidrKey.Y),
        }

    def _extract_scalar_mappable_data(
        self, sm: ScalarMappable | None
    ) -> list[list] | None:
        if sm is None or sm.get_array() is None:
            return None

        array = sm.get_array().data
        if isinstance(sm, (QuadMesh, PolyQuadMesh)):
            # The two mesh classes disagree about the shape they keep their
            # values in: `pcolormesh`'s QuadMesh flattens them, while
            # `pcolor`'s PolyQuadMesh keeps the grid. Reshaping unconditionally
            # would fail on the one that is already two-dimensional, so the
            # recovery is driven by the array rather than by the class.
            if array.ndim == 1:
                m, n, _ = ma.shape(sm.get_coordinates())
                # Coordinates shape is (M + 1, N + 1)
                array = array.reshape(m - 1, n - 1)

            # Tag the elements for highlighting
            self._elements.append(sm)
        else:
            self._support_highlighting = False

        return [list(map(lambda x: float(format(x, self._fmt)), row)) for row in array]
