from __future__ import annotations

from matplotlib.axes import Axes
from maidr.core.plot.maidr_plot import GROUP_NAME, MaidrPlot
from maidr.exception.extraction_error import ExtractionError
import numpy as np
from maidr.core.enum.plot_type import PlotType
from maidr.core.enum.maidr_key import MaidrKey
from maidr.util.resample_utils import resample_curve
from maidr.util.confidence_band import band_edges_at
from maidr.util.regression_line_utils import find_regression_line
from maidr.util.svg_utils import (
    data_to_svg_coords,
    from_scaled_coords,
    to_scaled_coords,
)

#: Default maximum number of output points per smooth curve.
_DEFAULT_MAX_SMOOTH_POINTS = 30



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
        # The hue group this curve belongs to, when the patch could name it.
        # A `kdeplot(hue=...)` draws one curve per level and both were
        # announced identically before (#558). Opted into here rather than
        # read by `MaidrPlot`; see `GROUP_NAME` for why that is per class.
        group_name = kwargs.get(GROUP_NAME, None)
        self._group_name = group_name if isinstance(group_name, str) else None
        super().__init__(ax, PlotType.SMOOTH)
        self._smooth_gid = None
        self._regression_line = kwargs.get("regression_line", None)
        self._poly_gid = kwargs.get("poly_gid", None)
        self._is_polycollection = kwargs.get("is_polycollection", False)

    def render(self) -> dict:
        """
        Add the group's name when the curve is one of several.

        The same field, and for the same reason, as ``HistPlot``: several
        ``smooth`` layers over one axis with nothing to tell them apart leave
        a reader hearing the identical announcement twice.
        """
        schema = super().render()
        if self._group_name:
            schema[MaidrKey.NAME] = self._group_name
        return schema

    def _get_selector(self):
        """
        Return the CSS selector for highlighting the regression line or PolyCollection in the SVG output.
        """
        if self._is_polycollection and self._poly_gid:
            return [f"g[id='{self._poly_gid}'] > defs > path"]
        if self._smooth_gid:
            return [f"g[id='{self._smooth_gid}'] path"]
        return ["g[id^='maidr-'] path"]

    def _thin_to_even_steps(
        self, x_data: np.ndarray, y_data: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Thin the curve to points that step evenly across the plot.

        The points are navigated and auto-played one at a time at a fixed rate,
        so the sweep only tracks the drawn line while the steps look even on
        screen.  Shape-based simplification gives the opposite: it collapses a
        straight fit to its two endpoints and spends fewer steps on the flat
        stretches of a curved one than on the bends.

        Thinning happens in scale space, so a log axis paces by the distance it
        draws rather than by raw data distance — on a linear axis the two are
        the same thing and this costs nothing.

        Parameters
        ----------
        x_data, y_data : np.ndarray
            Vertices of the fitted line, in data coordinates.

        Returns
        -------
        tuple of np.ndarray
            The retained vertices, in data coordinates.
        """
        if len(x_data) <= _DEFAULT_MAX_SMOOTH_POINTS:
            # Nothing to thin, so hand the vertices straight back.  Mapping
            # them into scale space and out again would return them shifted by
            # the round trip's last bit or two, for no gain.
            return x_data, y_data

        scaled = to_scaled_coords(self.ax, x_data, y_data)
        if scaled is None:
            # The scale cannot represent this data, leaving data coordinates as
            # the only ordering to thin along.
            xy = resample_curve(
                np.column_stack([x_data, y_data]),
                target=_DEFAULT_MAX_SMOOTH_POINTS,
            )
            return xy[:, 0], xy[:, 1]

        xy = resample_curve(np.column_stack(scaled), target=_DEFAULT_MAX_SMOOTH_POINTS)
        return from_scaled_coords(self.ax, xy[:, 0], xy[:, 1])

    def _extract_plot_data(self) -> list:
        """
        Extract XY data from the regression line for serialization, including SVG coordinates.

        Returns
        -------
        list
            A list of lists containing dictionaries with X and Y coordinates, and SVG coordinates.
        """
        regression_line = (
            self._regression_line
            if self._regression_line is not None
            else find_regression_line(self.ax)
        )
        if regression_line is None:
            raise ExtractionError(PlotType.SMOOTH, self.ax)
        self._elements.append(regression_line)
        self._smooth_gid = regression_line.get_gid()
        xydata = np.asarray(regression_line.get_xydata())
        x_data, y_data = xydata[:, 0], xydata[:, 1]

        x_data, y_data = self._thin_to_even_steps(x_data, y_data)

        x_svg, y_svg = data_to_svg_coords(self.ax, x_data, y_data)
        lower, upper = self._confidence_band_at(x_data, y_data)
        points = []
        for i, (x, y, sx, sy) in enumerate(zip(x_data, y_data, x_svg, y_svg)):
            point = {
                MaidrKey.X: float(x),
                MaidrKey.Y: float(y),
                "svg_x": float(sx),
                "svg_y": float(sy),
            }
            if lower is not None and upper is not None:
                point["yMin"] = float(lower[i])
                point["yMax"] = float(upper[i])
            points.append(point)
        return [points]

    def _confidence_band_at(self, x_data, y_data):
        """
        Read the interval ``regplot`` shades around its fit, at the given x.

        ``ci=95`` is seaborn's default, and the band is the reason a regression
        is drawn rather than a bare line: it says how much of the trend the
        data supports. It reached the schema as nothing at all -- the fitted
        line was announced alone, so a reader was told the trend without being
        told how well determined it is.

        The reading lives in :mod:`maidr.util.confidence_band`, which a plain
        line now shares (#562); every measurement behind it is recorded there.

        Parameters
        ----------
        x_data : numpy.ndarray
            The x positions the curve is emitted at.
        y_data : numpy.ndarray
            The fitted values at those positions, which a candidate region
            has to bracket to be this fit's band.

        Returns
        -------
        tuple
            Lower and upper bounds at each x, or ``(None, None)`` when the
            chart draws no band (``ci=None``).
        """
        lower, upper, _ = band_edges_at(self.ax, x_data, y_data)
        return lower, upper
