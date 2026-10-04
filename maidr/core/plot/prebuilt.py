"""A layer whose schema its reader built, for a chart no patched call draws.

Some readers know a chart's data before they draw it and draw it with artists
nothing reads -- a parallel coordinates plot is lines on axes of their own
scale, and reading the drawn lines would announce the scaled positions rather
than the values. Such a reader builds the layer from its data and registers it
with :meth:`~maidr.core.figure_manager.FigureManager.add_plot`.
"""

from __future__ import annotations

import copy
from typing import Any

from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot.maidr_plot import MaidrPlot


class PrebuiltPlot(MaidrPlot):
    """
    A layer of a given type, data and selectors.

    Parameters
    ----------
    ax : Axes
        The axes its marks are drawn on.
    plot_type : PlotType
        What the layer is read as.
    labels : dict
        What each of its axes, ``"x"``, ``"y"`` and optionally ``"z"``, is
        called.
    data : Any
        The layer's ``data``, in the shape its type reads.
    selectors : Any
        The layer's ``selectors``, in the shape its type reads.
    """

    def __init__(
        self,
        ax: Axes,
        plot_type: PlotType,
        *,
        labels: dict[str, str],
        data: Any,
        selectors: Any,
    ) -> None:
        super().__init__(ax, plot_type)
        self._labels = labels
        self._data = data
        self._selectors = selectors

    def _extract_axes_data(self) -> dict:
        """Each axis the layer names, labelled as given."""
        return {
            MaidrKey(key): self._axis_config(label=label)
            for key, label in self._labels.items()
        }

    def _extract_plot_data(self) -> Any:
        """A copy of the data the layer was built with."""
        return copy.deepcopy(self._data)

    def _get_selector(self) -> Any:  # type: ignore[override]
        """A copy of the selectors the layer was built with."""
        return copy.deepcopy(self._selectors)
