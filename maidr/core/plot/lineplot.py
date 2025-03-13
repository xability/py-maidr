from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.exception.extraction_error import ExtractionError
from maidr.util.environment import Environment
from maidr.util.mixin.extractor_mixin import LineExtractorMixin


class MultiLinePlot(MaidrPlot, LineExtractorMixin):
    """
    A class for extracting and processing data from line plots.

    This class can handle both single-line and multi-line plots, extracting
    coordinate data and line identifiers. It processes matplotlib Line2D objects
    and converts them into structured data for further processing or visualization.

    Parameters
    ----------
    ax : Axes
        The matplotlib axes object containing the line plot(s).
    **kwargs : dict
        Additional keyword arguments to pass to the parent class.

    Attributes
    ----------
    type : PlotType
        Set to PlotType.LINE to identify this as a line plot.

    Notes
    -----
    - When using the JavaScript engine, only single-line plots are supported.
    - For multi-line plots, use the TypeScript engine.
    - The extracted data structure includes x, y coordinates and line identifiers
      (fill values) for each point.
    """

    def __init__(self, ax: Axes, **kwargs):
        super().__init__(ax, PlotType.LINE)

    def _get_selector(self) -> str:
        return "g[maidr='true'] > path"

    def _extract_plot_data(self) -> list[dict]:
        plot = self.extract_lines(self.ax)
        data = self._extract_line_data(plot)
        engine = Environment.get_engine()
        if engine == "js":
            if len(data) > 1:
                raise Exception(
                    "MultiLine Plot not supported in JS. Use TypeScript Engine for this plot!"
                )
            data = data[0]

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_line_data(self, plot: list[Line2D] | None) -> list[dict] | None:
        """
        Extract data from multiple line objects.

        Parameters
        ----------
        plot : list[Line2D] | None
            List of Line2D objects to extract data from.

        Returns
        -------
        list[dict] | None
            List of dictionaries containing x,y coordinates and line identifiers,
            or None if the plot data is invalid.
        """
        if plot is None or len(plot) == 0:
            return None

        all_line_data = []

        # Process each line in the plot
        for i, line in enumerate(plot):
            if line.get_xydata() is None:
                continue

            # Tag the element for highlighting
            self._elements.append(line)

            # Extract data from this line
            line_data = [
                {
                    MaidrKey.X: float(x),
                    MaidrKey.Y: float(y),
                    MaidrKey.FILL: line.get_label(),
                }
                for x, y in line.get_xydata()  # type: ignore
            ]
            if len(line_data) > 0:
                all_line_data.append(line_data)

        return all_line_data if all_line_data else None
