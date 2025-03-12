from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.environment import Environment
from maidr.util.mixin import (
    ContainerExtractorMixin,
    DictMergerMixin,
    LevelExtractorMixin,
)


class BarPlot(MaidrPlot, ContainerExtractorMixin, LevelExtractorMixin, DictMergerMixin):
    def __init__(self, ax: Axes) -> None:
        super().__init__(ax, PlotType.BAR)

    def _extract_axes_data(self) -> dict:
        engine = Environment.get_engine()

        base_schema = super()._extract_axes_data()
        bar_ax_schema = {}
        if engine == "js":
            bar_ax_schema = {
                MaidrKey.X: {
                    MaidrKey.LEVEL: self.extract_level(self.ax),
                },
            }
        return self.merge_dict(base_schema, bar_ax_schema)

    def _extract_plot_data(self) -> list:
        engine = Environment.get_engine()
        plot = self.extract_container(self.ax, BarContainer, include_all=True)
        data = self._extract_bar_container_data(plot)
        levels = self.extract_level(self.ax)
        if engine == "ts":
            formatted_data = []
            combined_data = (
                zip(levels, data) if plot[0].orientation == "vertical" else zip(levels, data)  # type: ignore
            )
            if len(data) == len(plot):  # type: ignore
                for x, y in combined_data:  # type: ignore
                    formatted_data.append({"x": x, "y": y})
                return formatted_data
            if len(formatted_data) == 0:
                raise ExtractionError(self.type, plot)
        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_bar_container_data(
        self, plot: list[BarContainer] | None
    ) -> list | None:
        if plot is None:
            return None

        # Since v0.13, Seaborn has transitioned from using `list[Patch]` to
        # `list[BarContainers] for plotting bar plots.
        # So, extract data correspondingly based on the level.
        # Flatten all the `list[BarContainer]` to `list[Patch]`.
        plot = [patch for container in plot for patch in container.patches]
        level = self.extract_level(self.ax)

        if len(plot) != len(level):
            return None

        # Tag the elements for highlighting.
        self._elements.extend(plot)

        return [float(patch.get_height()) for patch in plot]
