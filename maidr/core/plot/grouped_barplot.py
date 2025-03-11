from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import (
    ContainerExtractorMixin,
    DictMergerMixin,
    LevelExtractorMixin,
)


class GroupedBarPlot(
    MaidrPlot, ContainerExtractorMixin, LevelExtractorMixin, DictMergerMixin
):
    def __init__(self, ax: Axes, plot_type: PlotType, **kwargs) -> None:
        super().__init__(ax, plot_type)
        self._support_highlighting = False

    def _extract_axes_data(self) -> dict:
        base_ax_schema = super()._extract_axes_data()
        grouped_ax_schema = {
            MaidrKey.X.value: {
                MaidrKey.LEVEL.value: self.extract_level(self.ax, MaidrKey.X),
            },
            MaidrKey.FILL.value: {
                MaidrKey.LABEL.value: "Fill",
                MaidrKey.LEVEL.value: self.extract_level(self.ax, MaidrKey.FILL),
            },
        }
        return self.merge_dict(base_ax_schema, grouped_ax_schema)

    def _extract_plot_data(self):
        plot = self.extract_container(self.ax, BarContainer, include_all=True)
        data = self._extract_grouped_bar_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_grouped_bar_data(
        self, plot: list[BarContainer] | None
    ) -> list[dict] | None:
        if plot is None:
            return None

        x_level = self.extract_level(self.ax)
        data = []

        for container in plot:
            if len(x_level) != len(container.patches):
                return None

            for x, y in zip(x_level, container.patches):
                data.append(
                    {
                        MaidrKey.X.value: x,
                        MaidrKey.FILL.value: container.get_label(),
                        MaidrKey.Y.value: float(y.get_height()),
                    }
                )

        return data
