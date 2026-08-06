from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import ContainerExtractorMixin, DictMergerMixin


class HistPlot(MaidrPlot, ContainerExtractorMixin, DictMergerMixin):
    def __init__(self, ax: Axes) -> None:
        super().__init__(ax, PlotType.HIST)
        self._orientation = "vert"

    @staticmethod
    def _extract_orientation(plot: BarContainer | None) -> str:
        """
        Read the orientation matplotlib recorded on the bar container.

        Parameters
        ----------
        plot : BarContainer, optional
            The container holding the histogram bars.

        Returns
        -------
        str
            ``"horz"`` for ``hist(orientation="horizontal")``, ``"vert"``
            otherwise.
        """
        if plot is None:
            return "vert"

        return "horz" if plot.orientation == "horizontal" else "vert"

    def render(self) -> dict:
        """Add ``orientation`` to the base schema."""
        base_schema = super().render()
        hist_orientation = {MaidrKey.ORIENTATION: self._orientation}
        return DictMergerMixin.merge_dict(base_schema, hist_orientation)

    def _extract_plot_data(self) -> list[dict]:
        plot = self.extract_container(self.ax, BarContainer)
        self._orientation = self._extract_orientation(plot)
        data = self._extract_bar_container_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_bar_container_data(
        self, plot: BarContainer | None
    ) -> list[dict] | None:
        if plot is None or plot.patches is None:
            return None

        data = []
        for patch in plot.patches:
            # A horizontal histogram runs its bins up the y axis and its
            # counts along x, so the bin edges come off the patch's y and
            # height and the count off its width. The vertical case is the
            # mirror of that.
            if self._orientation == "horz":
                count = float(patch.get_width())
                bin_start = float(patch.get_y())
                bin_size = float(patch.get_height())

                data.append(
                    {
                        MaidrKey.X.value: count,
                        MaidrKey.Y.value: bin_start + bin_size / 2,
                        MaidrKey.Y_MIN.value: bin_start,
                        MaidrKey.Y_MAX.value: bin_start + bin_size,
                        MaidrKey.X_MIN.value: 0,
                        MaidrKey.X_MAX.value: count,
                    }
                )
                continue

            count = float(patch.get_height())
            bin_start = float(patch.get_x())
            bin_size = float(patch.get_width())

            data.append(
                {
                    MaidrKey.Y.value: count,
                    MaidrKey.X.value: bin_start + bin_size / 2,
                    MaidrKey.X_MIN.value: bin_start,
                    MaidrKey.X_MAX.value: bin_start + bin_size,
                    MaidrKey.Y_MIN.value: 0,
                    MaidrKey.Y_MAX.value: count,
                }
            )

        # Tag the elements for highlighting
        self._elements.extend(plot.patches)

        return data
