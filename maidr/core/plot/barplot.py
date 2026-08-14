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


class BarPlot(MaidrPlot, ContainerExtractorMixin, LevelExtractorMixin, DictMergerMixin):
    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.BAR)
        self._orientation = "vert"
        # The container this layer's own call drew, when the patch could say.
        # `None` falls back to sweeping the axes, which is what seaborn needs:
        # it draws one layer as several containers, one per hue group.
        self._own_bars = kwargs.get("_maidr_bars", None)

    @property
    def _is_horizontal(self) -> bool:
        return self._orientation == "horz"

    @property
    def _level_key(self) -> MaidrKey:
        """
        The axis the bar labels sit on: ``y`` for a horizontal bar plot
        (``Axes.barh``, ``seaborn.barplot(orient="h")``), ``x`` otherwise.
        """
        return MaidrKey.Y if self._is_horizontal else MaidrKey.X

    @staticmethod
    def _extract_orientation(plot: list[BarContainer] | None) -> str:
        """
        Read the orientation matplotlib recorded on the bar container.

        Only the first container is asked: every container on one Axes is
        drawn by the same call, so a layer runs one way or the other, never
        both. A mixed-orientation layer would need this to say so per bar.

        Parameters
        ----------
        plot : list of BarContainer, optional
            The containers holding the bars of this layer.

        Returns
        -------
        str
            ``"horz"`` for a horizontal bar plot, ``"vert"`` otherwise.
        """
        if not plot:
            return "vert"

        return "horz" if plot[0].orientation == "horizontal" else "vert"

    def render(self) -> dict:
        """Add ``orientation`` to the base schema."""
        # Read after the super call, not before: `self._orientation` is
        # populated by `_extract_plot_data`, which that call runs.
        base_schema = super().render()
        bar_orientation = {MaidrKey.ORIENTATION: self._orientation}
        return DictMergerMixin.merge_dict(base_schema, bar_orientation)

    def _extract_plot_data(self) -> list:
        plot = self._own_containers()
        self._orientation = self._extract_orientation(plot)
        levels = self.extract_level(self.ax, self._level_key)

        data = self._extract_bar_container_data(plot, levels)
        if data is None:
            raise ExtractionError(self.type, plot)

        # A horizontal bar's magnitude runs along x and its label sits on y,
        # which is the layout the renderer reads for a horizontal layer. The
        # vertical layer is the mirror of that.
        if self._is_horizontal:
            combined_data = list(zip(data, levels))  # type: ignore
        else:
            combined_data = list(zip(levels, data))  # type: ignore

        if not combined_data:
            raise ExtractionError(self.type, plot)

        return [{"x": x, "y": y} for x, y in combined_data]

    def _own_containers(self) -> list[BarContainer]:
        """
        The containers this layer describes.

        The containers its own call drew when the patch could name them, and
        every ``BarContainer`` on the axes otherwise.

        The sweep is not a fallback in the apologetic sense -- seaborn draws
        one bar layer as several containers, one per hue group, and registers
        it from a seaborn-level patch where no single container is the answer.
        What the sweep cannot do is tell one ``ax.bar()`` call's bars from
        another's, so two overlaid calls each found both containers' patches,
        failed the count check against one axis' worth of tick labels, and
        raised ``ExtractionError`` -- fatal to the whole figure (#380).

        Returns
        -------
        list of BarContainer
            One or more containers, in the order the axes holds them.
        """
        if self._own_bars is not None:
            return [self._own_bars]
        return self.extract_container(self.ax, BarContainer, include_all=True)

    def _extract_bar_container_data(
        self, plot: list[BarContainer] | None, levels: list[str] | None
    ) -> list | None:
        """
        Read one magnitude per bar, in the containers' own order.

        Parameters
        ----------
        plot : list of BarContainer, optional
            The containers holding the bars of this layer.
        levels : list of str, optional
            The bar labels read off the categorical axis. Used only to check
            that the axis has one label per bar; an axis with no tick labels
            at all is not checked here — the caller pairs the magnitudes with
            the labels, so it ends up raising `ExtractionError` on an empty
            list regardless.

        Returns
        -------
        list, optional
            One magnitude per bar, or None when the bars and the labels do
            not line up.
        """
        if plot is None:
            return None

        # Since v0.13, Seaborn has transitioned from using `list[Patch]` to
        # `list[BarContainers] for plotting bar plots.
        # So, extract data correspondingly based on the level.
        # Flatten all the `list[BarContainer]` to `list[Patch]`.
        plot = [patch for container in plot for patch in container.patches]
        if levels and len(plot) != len(levels):
            return None

        self._elements.extend(plot)

        # A bar's magnitude is the dimension it grows along: the width of a
        # horizontal bar, the height of a vertical one.
        if self._is_horizontal:
            return [float(patch.get_width()) for patch in plot]

        return [float(patch.get_height()) for patch in plot]
