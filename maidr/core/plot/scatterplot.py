from __future__ import annotations

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
