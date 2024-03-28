from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.maidr_plot import MaidrPlot
from maidr.core.mixin.extractor_mixin import ContainerExtractorMixin
from maidr.exception.extraction_error import ExtractionError


class HistPlot(MaidrPlot, ContainerExtractorMixin):
    def __init__(self, ax: Axes) -> None:
        super().__init__(ax, PlotType.HIST)

    def _extract_plot_data(self) -> list[dict]:
        plot = self.extract_container(self.ax, BarContainer)
        data = HistPlot.__extract_bar_container_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    @staticmethod
    def __extract_bar_container_data(plot: BarContainer | None) -> list[dict] | None:
        if plot is None or plot.patches is None:
            return None

        data = list()

        for patch in plot.patches:
            y = float(patch.get_height())
            x = float(patch.get_x())
            width = float(patch.get_width())

            data.append(
                {
                    MaidrKey.Y.value: y,
                    MaidrKey.X.value: x + width / 2,
                    MaidrKey.X_MIN.value: x,
                    MaidrKey.X_MAX.value: x + width,
                    MaidrKey.Y_MIN.value: 0,
                    MaidrKey.Y_MAX.value: y,
                }
            )

        return data
