from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.patches import Rectangle

from maidr.core.enum import PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import (
    ContainerExtractorMixin,
    DictMergerMixin,
    LevelExtractorMixin,
)
from maidr.util.mplfinance_utils import MplfinanceDataExtractor
from maidr.core.enum.maidr_key import MaidrKey


class MplfinanceBarPlot(
    MaidrPlot, ContainerExtractorMixin, LevelExtractorMixin, DictMergerMixin
):
    """
    Specialized bar plot class for mplfinance volume bars.

    This class handles the extraction and processing of volume data from mplfinance
    plots, including proper date conversion and data validation.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.BAR)
        # Store custom patches passed from mplfinance patch
        self._custom_patches = kwargs.get("_maidr_patches", None)
        # Store date numbers for volume bars (from mplfinance)
        self._maidr_date_nums = kwargs.get("_maidr_date_nums", None)
        # Store custom title

    def set_title(self, title: str) -> None:
        """Set a custom title for this volume bar plot."""
        self._title = title

    def _extract_plot_data(self) -> list:
        """Extract data from mplfinance volume patches."""
        if self._custom_patches:
            return self._extract_volume_patches_data(self._custom_patches)

        # Fallback to original bar plot logic if no custom patches
        plot = self.extract_container(
            self.ax, ContainerExtractorMixin, include_all=True
        )
        data = self._extract_bar_container_data(plot)
        levels = self.extract_level(self.ax)
        formatted_data = []
        combined_data = list(
            zip(levels, data)
            if plot[0].orientation == "vertical"
            else zip(data, levels)  # type: ignore
        )
        if combined_data:  # type: ignore
            for x, y in combined_data:  # type: ignore
                formatted_data.append({"x": x, "y": y})
            return formatted_data
        if len(formatted_data) == 0:
            raise ExtractionError(self.type, plot)
        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_volume_patches_data(self, volume_patches: list[Rectangle]) -> list:
        """
        Extract data from volume Rectangle patches (used by mplfinance volume bars).
        """
        if not volume_patches:
            return []

        # Sort patches by x-coordinate to maintain order
        sorted_patches = sorted(volume_patches, key=lambda p: p.get_x())

        # Set elements for highlighting (use the patches directly)
        self._elements = sorted_patches

        # Use the utility class to extract data
        return MplfinanceDataExtractor.extract_volume_data(
            sorted_patches, self._maidr_date_nums
        )

    def _extract_bar_container_data(self, plot: list | None) -> list | None:
        """Fallback method for regular bar containers."""
        if plot is None:
            return None

        # Since v0.13, Seaborn has transitioned from using `list[Patch]` to
        # `list[BarContainers] for plotting bar plots.
        # So, extract data correspondingly based on the level.
        # Flatten all the `list[BarContainer]` to `list[Patch]`.
        patches = [patch for container in plot for patch in container.patches]
        level = self.extract_level(self.ax)
        if level is None or len(level) == 0:  # type: ignore
            level = ["" for _ in range(len(patches))]  # type: ignore

        if len(patches) != len(level):
            return None

        self._elements.extend(patches)

        return [float(patch.get_height()) for patch in patches]

    def _extract_axes_data(self) -> dict:
        """Extract axes data with mplfinance-specific cleaning."""
        ax_data = super()._extract_axes_data()

        # For mplfinance volume plots, clean up the y-axis label
        if self._custom_patches:
            y_label = ax_data.get("y")
            if y_label:
                ax_data["y"] = MplfinanceDataExtractor.clean_axis_label(y_label)

        return ax_data

    def _get_selector(self) -> str:
        """Return the CSS selector for highlighting bar elements in the SVG output."""
        # Use the standard working selector that gets replaced with UUID by Maidr class
        # This works for both original bar plots and mplfinance volume bars
        return "g[maidr='true'] > path"

    def render(self) -> dict:
        base_schema = super().render()
        base_schema[MaidrKey.TITLE] = "Volume Bar Plot"
        base_schema[MaidrKey.AXES] = self._extract_axes_data()
        base_schema[MaidrKey.DATA] = self._extract_plot_data()
        if self._support_highlighting:
            base_schema[MaidrKey.SELECTOR] = self._get_selector()
        return base_schema
