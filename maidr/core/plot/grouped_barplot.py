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
        self._orientation = "vert"

    @property
    def _is_horizontal(self) -> bool:
        return self._orientation == "horz"

    @property
    def _level_key(self) -> MaidrKey:
        """
        The axis the bar labels sit on: ``y`` for a horizontal layer
        (``seaborn.barplot(orient="h", hue=...)``), ``x`` otherwise.
        """
        return MaidrKey.Y if self._is_horizontal else MaidrKey.X

    @staticmethod
    def _extract_orientation(plot: list[BarContainer] | None) -> str:
        """
        Read the orientation matplotlib recorded on the bar containers.

        Only the first container is asked: the containers of one layer are
        drawn by the same call, so they all run the same way.

        Parameters
        ----------
        plot : list of BarContainer, optional
            The containers holding the bars of this layer, one per group.

        Returns
        -------
        str
            ``"horz"`` for a horizontal layer, ``"vert"`` otherwise.
        """
        if not plot:
            return "vert"

        return "horz" if plot[0].orientation == "horizontal" else "vert"

    def render(self) -> dict:
        """Add ``orientation`` to the base schema."""
        # Read after the super call, not before: `self._orientation` is
        # populated by `_extract_plot_data`, which that call runs.
        base_schema = super().render()
        orientation = {MaidrKey.ORIENTATION: self._orientation}
        return DictMergerMixin.merge_dict(base_schema, orientation)

    def _extract_axes_data(self) -> dict:
        """
        Extend the base per-axis ``AxisConfig`` mapping with a ``z`` axis whose
        label is sourced from the legend title (the hue/group column).

        If no legend or no legend title is available, ``z`` is omitted —
        per-point ``z`` values remain in the data payload.
        """
        axes_data = super()._extract_axes_data()

        z_label = self._extract_z_label_from_legend()
        if z_label:
            axes_data[MaidrKey.Z] = self._axis_config(label=z_label)

        return axes_data

    def _extract_z_label_from_legend(self) -> str:
        """Return the legend title text (trimmed) or an empty string."""
        legend = self.ax.get_legend()
        if legend is None:
            return ""
        title = legend.get_title()
        if title is None:
            return ""
        return title.get_text().strip()

    def _extract_plot_data(self) -> list[list[dict]]:
        plot = self.extract_container(self.ax, BarContainer, include_all=True)
        data = self._extract_grouped_bar_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_grouped_bar_data(
        self, plot: list[BarContainer] | None
    ) -> list[list[dict]] | None:
        if plot is None:
            return None

        self._orientation = self._extract_orientation(plot)

        level = self.extract_level(self.ax, self._level_key)
        if not level:
            return None

        data = []

        self._elements.extend(
            [patch for container in plot for patch in container.patches]
        )

        # Get hue categories from legend
        hue_categories = self._extract_hue_categories_from_legend()

        for i, container in enumerate(plot):
            if len(level) != len(container.patches):
                return None
            container_data = []

            # Use hue category if available, otherwise fall back to container label
            fill_value = hue_categories[i] if i < len(hue_categories) else container.get_label()

            for label, patch in zip(level, container.patches):
                # A horizontal bar's magnitude runs along x and its label sits
                # on y, which is the layout the renderer reads for a
                # horizontal layer. The vertical layer is the mirror of that.
                if self._is_horizontal:
                    point = {
                        MaidrKey.X.value: float(patch.get_width()),
                        MaidrKey.Z.value: fill_value,
                        MaidrKey.Y.value: label,
                    }
                else:
                    point = {
                        MaidrKey.X.value: label,
                        MaidrKey.Z.value: fill_value,
                        MaidrKey.Y.value: float(patch.get_height()),
                    }
                container_data.append(point)
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
