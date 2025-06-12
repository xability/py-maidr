from __future__ import annotations

from typing import List, Union

from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot


class KdePlot(MaidrPlot):
    """
    Extracts data from a single unfilled KDE line plot.
    """

    def __init__(self, ax, **kwargs):
        super().__init__(ax, PlotType.SMOOTH)
        self._smooth_gid = None

    def _get_selector(self):
        # Use the unique gid if available for precise selection
        if self._smooth_gid:
            return [f"g[id='{self._smooth_gid}'] > path"]
        return ["g[id^='maidr-'] > path"]

    def _extract_plot_data(self):
        # Only extract the first Line2D object (the KDE line)
        lines = [line for line in self.ax.get_lines() if isinstance(line, Line2D)]
        if not lines:
            return None
        line = lines[0]
        self._elements.append(line)
        self._smooth_gid = line.get_gid()
        label = line.get_label()
        curve_data = [
            {MaidrKey.X: float(x), MaidrKey.Y: float(y), MaidrKey.FILL: label}
            for x, y in line.get_xydata()
        ]
        return [curve_data] if curve_data else None

    def _get_legend_labels(self) -> List[str]:
        """Get the legend labels in the order they appear in the plot."""
        # Use ax.get_legend_handles_labels() for more robust label extraction
        handles, labels = self.ax.get_legend_handles_labels()
        return labels

    def _extract_line_data(
        self, plot: Union[List[Line2D], None]
    ) -> Union[List[dict], None]:
        """
        Extract data from a single line object representing a KDE curve.
        Only the first line is considered for single-line smooth plots.
        """
        if plot is None or len(plot) == 0:
            return None

        # Only consider the first line for single-line smooth plots
        line = plot[0]
        if line.get_xydata() is None:
            return None

        self._elements.append(line)
        label = line.get_label()
        curve_data = [
            {MaidrKey.X: float(x), MaidrKey.Y: float(y), MaidrKey.FILL: label}
            for x, y in line.get_xydata()
        ]
        return [curve_data] if curve_data else None

    def _extract_collection_data(
        self, plot: Union[PathCollection, None]
    ) -> Union[List[dict], None]:
        """
        Extract data from filled KDE curves represented as PathCollection.

        Parameters
        ----------
        plot : PathCollection | None
            PathCollection object to extract data from.

        Returns
        -------
        list[dict] | None
            List of dictionaries containing x,y coordinates and curve identifiers,
            or None if the plot data is invalid.
        """
        if plot is None or plot.get_paths() is None:
            return None

        # Get legend labels in order
        legend_labels = self._get_legend_labels()

        # Tag the element for highlighting
        self._elements.append(plot)

        # Extract data from the collection
        all_curve_data = []
        for i, path in enumerate(plot.get_paths()):
            vertices = path.vertices
            if vertices is not None and len(vertices) > 0:
                # Use legend label if available, otherwise use collection label
                label = legend_labels[i] if i < len(legend_labels) else plot.get_label()

                curve_data = [
                    {
                        MaidrKey.X: float(x),
                        MaidrKey.Y: float(y),
                        MaidrKey.FILL: label if not label.startswith("_child") else "",
                    }
                    for x, y in vertices
                ]
                if curve_data:
                    all_curve_data.append(curve_data)

        return all_curve_data if all_curve_data else None
