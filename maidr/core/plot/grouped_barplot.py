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

    def _extract_axes_data(self) -> dict:
        base_ax_schema = super()._extract_axes_data()
        grouped_ax_schema = {
            MaidrKey.X.value: self.ax.get_xlabel(),
            MaidrKey.Y.value: self.ax.get_ylabel(),
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
        if x_level is None:
            return None

        data = []

        self._elements.extend(
            [patch for container in plot for patch in container.patches]
        )

        # Get hue categories from legend
        hue_categories = self._extract_hue_categories_from_legend()

        for i, container in enumerate(plot):
            if len(x_level) != len(container.patches):
                return None
            container_data = []

            # Use hue category if available, otherwise fall back to container label
            fill_value = hue_categories[i] if i < len(hue_categories) else container.get_label()

            for x, y in zip(x_level, container.patches):
                container_data.append(
                    {
                        MaidrKey.X.value: x,
                        MaidrKey.FILL.value: fill_value,
                        MaidrKey.Y.value: float(y.get_height()),
                    }
                )
            data.append(container_data)

        return data

    def _extract_hue_categories_from_legend(self) -> list[str]:
        """
        Extract hue categories from the axes legend.

        This method reads the legend text elements from the axes legend,
        trims whitespace from each text, and returns a list of cleaned
        category names. This is used to get the actual category names
        instead of using the generic container labels like '_container0', '_container1'.

        Parameters
        ----------
        None
            This method uses the instance's axes object.

        Returns
        -------
        list[str]
            List of trimmed hue category names from the legend.
            Returns empty list if no legend is found or if legend has no text elements.

        Examples
        --------
        >>> # For a seaborn barplot with hue='category' and legend showing 'Below', 'Above'
        >>> plot = GroupedBarPlot(ax, PlotType.DODGED)
        >>> categories = plot._extract_hue_categories_from_legend()
        >>> print(categories)
        ['Below', 'Above']

        >>> # If no legend exists
        >>> categories = plot._extract_hue_categories_from_legend()
        >>> print(categories)
        []
        """
        legend = self.ax.get_legend()
        if legend is None:
            return []

        # Get legend text elements
        legend_texts = legend.get_texts()
        if not legend_texts:
            return []

        # Extract text content from legend elements and trim whitespace
        hue_categories = [text.get_text().strip() for text in legend_texts]

        # Filter out empty strings and return
        return [category for category in hue_categories if category]
