from __future__ import annotations

from matplotlib.axes import Axes
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.exception.extraction_error import ExtractionError
import numpy as np
from maidr.core.enum.plot_type import PlotType
from maidr.core.enum.maidr_key import MaidrKey


class SmoothPlot(MaidrPlot):
    """
    Extracts and represents a regression line as a smooth plot for MAIDR.

    Parameters
    ----------
    ax : Axes
        The matplotlib axes object containing the regression line.
    """

    def __init__(self, ax: Axes, **kwargs):
        """
        Initialize a SmoothPlot for a regression line.

        Parameters
        ----------
        ax : Axes
            The matplotlib axes object containing the regression line.
        """
        super().__init__(ax, PlotType.SMOOTH)

    def _get_selector(self):
        """
        Return the CSS selector for highlighting the regression line in the SVG output.
        """
        return ["g[id^='maidr-'] path"]

    def _extract_plot_data(self):
        """
        Extract XY data from the regression line for serialization.

        Returns
        -------
        list
            A list of lists containing dictionaries with X and Y coordinates, or an empty list if no regression line is present.
        """
        from matplotlib.lines import Line2D

        regression_line = next(
            (
                artist
                for artist in self.ax.get_children()
                if isinstance(artist, Line2D)
                and artist.get_label() not in (None, "", "_nolegend_")
                and artist.get_xydata() is not None
                and np.asarray(artist.get_xydata()).size > 0
            ),
            None,
        )
        self._elements.append(regression_line)
        if regression_line is None:
            raise ExtractionError(PlotType.SMOOTH, self.ax)
        xydata = np.asarray(regression_line.get_xydata())
        return [[{MaidrKey.X: float(x), MaidrKey.Y: float(y)} for x, y in xydata]]
