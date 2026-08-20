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
        # Read after the super call, not before: `self._orientation` is
        # populated by `_extract_plot_data`, which that call runs.
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

    @staticmethod
    def _bin_point(
        orientation: str, bin_start: float, bin_size: float, count: float | None
    ) -> dict:
        """
        Build one bin's point, whichever way the histogram was drawn.

        Shared with :class:`~maidr.core.plot.stairs.StairsPlot`, so the two
        spellings of a histogram -- a row of bars from ``Axes.hist``, a
        staircase from ``Axes.stairs`` -- emit the same payload for the same
        chart rather than two that merely resemble one another.

        Parameters
        ----------
        orientation : str
            ``"horz"`` when the bins run up the y axis, ``"vert"`` otherwise.
        bin_start : float
            The bin's lower edge, along the axis the bins run on.
        bin_size : float
            The width of the bin, on that same axis.
        count : float or None
            What the bin holds, or ``None`` when it holds nothing measurable.

        Returns
        -------
        dict
            The point, with the bin edges on the axis the bins run on.

        Notes
        -----
        The bounds across the bins -- ``yMin``/``yMax`` on a vertical
        histogram, ``xMin``/``xMax`` on a horizontal one -- are emitted for
        the shape's sake and are not read: the core's ``Histogram`` trace
        takes its bin range from the pair on the *binned* axis and never
        looks at the other.
        """
        if orientation == "horz":
            return {
                MaidrKey.X.value: count,
                MaidrKey.Y.value: bin_start + bin_size / 2,
                MaidrKey.Y_MIN.value: bin_start,
                MaidrKey.Y_MAX.value: bin_start + bin_size,
                MaidrKey.X_MIN.value: 0,
                MaidrKey.X_MAX.value: count,
            }

        return {
            MaidrKey.Y.value: count,
            MaidrKey.X.value: bin_start + bin_size / 2,
            MaidrKey.X_MIN.value: bin_start,
            MaidrKey.X_MAX.value: bin_start + bin_size,
            MaidrKey.Y_MIN.value: 0,
            MaidrKey.Y_MAX.value: count,
        }

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
                data.append(
                    self._bin_point(
                        "horz",
                        float(patch.get_y()),
                        float(patch.get_height()),
                        float(patch.get_width()),
                    )
                )
                continue

            data.append(
                self._bin_point(
                    "vert",
                    float(patch.get_x()),
                    float(patch.get_width()),
                    float(patch.get_height()),
                )
            )

        # Tag the elements for highlighting
        self._elements.extend(plot.patches)

        return data
