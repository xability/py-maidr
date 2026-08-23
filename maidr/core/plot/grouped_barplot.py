from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.legend_names import legend_of
from maidr.util.mixin import (
    BarPositionMixin,
    ContainerExtractorMixin,
    DictMergerMixin,
    LevelExtractorMixin,
)

#: Key a patch uses to hand this layer the containers it drew, one per group,
#: instead of letting it sweep the axes. A `seaborn.objects` bar needs it for
#: a reason the classic path never has: `so.Bar(color=)` draws every level
#: into *one* container, so the groups are synthesised from the bars' colours
#: and are not on the axes to be found (#617).
DRAWN_GROUPS = "_maidr_bar_groups"


class GroupedBarPlot(
    MaidrPlot,
    BarPositionMixin,
    ContainerExtractorMixin,
    LevelExtractorMixin,
    DictMergerMixin,
):
    def __init__(self, ax: Axes, plot_type: PlotType, **kwargs) -> None:
        super().__init__(ax, plot_type)
        self._orientation = "vert"
        self._own_groups = kwargs.get(DRAWN_GROUPS, None)

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
        """
        Return the legend title text (trimmed) or an empty string.

        Through :func:`~maidr.util.legend_names.legend_of` rather than
        ``ax.get_legend()``, which is what this read before. The two answer
        the same question -- which legend names this axes' groups -- and the
        wider answer also reads a lone *figure* legend, which is where
        ``so.Plot`` puts the only legend a colour-split bar has (#617).
        """
        legend = legend_of(self.ax)
        if legend is None:
            return ""
        title = legend.get_title()
        if title is None:
            return ""
        return title.get_text().strip()

    def _own_containers(self) -> list[BarContainer] | None:
        """
        The containers this layer holds: the ones handed to it, or the axes'.

        Sweeping the axes is what every grouped bar read before, and it is
        right for the classic spelling -- ``seaborn.barplot(hue=)`` draws one
        container per level and nothing else onto that axes. It cannot serve
        a ``seaborn.objects`` bar, whose levels arrive in a single container
        and are split by colour after the fact (#617): the sweep would find
        the one undivided container and read every level as one group.

        The same shape :meth:`maidr.core.plot.barplot.BarPlot._own_containers`
        already has, for the reason #527 gave it -- a layer reads the artists
        its own call drew.

        Returns
        -------
        list of BarContainer, optional
            The handed-over containers when there are any, otherwise every
            container on the axes.
        """
        if self._own_groups is not None:
            return self._own_groups
        return self.extract_container(self.ax, BarContainer, include_all=True)

    def _extract_plot_data(self) -> list[list[dict]]:
        plot = self._own_containers()
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

        level = self._labels_for(plot)
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
                # Guarded above by `_labels_for`, which either found one tick
                # per bar or built one label per bar. A container of a
                # different length from its siblings would still land here,
                # and there is nothing honest to pair it with.
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

    def _labels_for(self, plot: list[BarContainer]) -> list[str]:
        """
        What to announce alongside each bar of every series.

        The tick labels when there is one per bar, and the positions the bars
        were drawn at otherwise. Decided once for the layer rather than per
        container, because every series of a segmented chart shares one
        category axis -- so the announcement has to agree across them, and a
        per-container answer could name a category in one series and a
        position in the next.

        matplotlib puts exactly one tick per category on a categorical axis,
        so the counts agree there by construction; on a numeric axis the tick
        locator picks its own breaks and they have no reason to. This used to
        return ``None`` for that mismatch, which the caller turned into an
        ``ExtractionError`` and so into an empty render -- a stacked chart
        over ``np.arange(len(species))`` produced no HTML at all (#384), the
        segmented half of #382.

        The first container is the one measured. Every container of a
        segmented layer holds one bar per category by construction, so they
        agree; a layer where they do not is caught by the length check at the
        pairing loop, which has nothing honest to pair such a container with.

        Parameters
        ----------
        plot : list of BarContainer
            The containers holding this layer's series.

        Returns
        -------
        list of str
            One label per category, from the axis or from the bars.
        """
        level = self.extract_level(self.ax, self._level_key)
        first = plot[0].patches if plot else []
        if level and len(level) == len(first):
            return level

        return [self._bar_position(patch) for patch in first]

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

        Notes
        -----
        Read through :func:`~maidr.util.legend_names.legend_of`, so a lone
        figure legend counts -- ``so.Plot`` puts the only legend a
        colour-split bar has there, and ``ax.get_legend()`` is ``None`` (#617).
        """
        legend = legend_of(self.ax)
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
