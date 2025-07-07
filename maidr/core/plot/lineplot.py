from typing import List, Union

from matplotlib.axes import Axes

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.exception.extraction_error import ExtractionError
from maidr.util.mixin.extractor_mixin import LineExtractorMixin
import uuid


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

    def _get_selector(self) -> Union[str, List[str]]:
        # Return selectors for all lines that have data
        all_lines = self.ax.get_lines()
        if not all_lines:
            return ["g[maidr='true'] > path"]

        selectors = []
        for line in all_lines:
            # Only create selectors for lines that have data (same logic as _extract_line_data)
            xydata = line.get_xydata()
            if xydata is None or not xydata.size:  # type: ignore
                continue
            gid = line.get_gid()
            if gid:
                selectors.append(f"g[id='{gid}'] path")
            else:
                selectors.append("g[maidr='true'] > path")

        if not selectors:
            return ["g[maidr='true'] > path"]

        return selectors

    def _extract_plot_data(self) -> Union[List[List[dict]], None]:
        data = self._extract_line_data()

        if data is None:
            raise ExtractionError(self.type, None)

        return data

    def _extract_line_data(self) -> Union[List[List[dict]], None]:
        """
        Extract data from all line objects and return as separate arrays.

        Returns
        -------
        list[list[dict]] | None
            List of lists, where each inner list contains dictionaries with x,y coordinates
            and line identifiers for one line, or None if the plot data is invalid.
        """
        all_lines = self.ax.get_lines()
        if not all_lines:
            return None

        # Try to get series names from legend
        legend_labels = []
        if self.ax.legend_ is not None:
            legend_labels = [text.get_text() for text in self.ax.legend_.get_texts()]

        all_lines_data = []

        for i, line in enumerate(all_lines):
            xydata = line.get_xydata()
            if xydata is None or not xydata.size:  # type: ignore
                continue

            self._elements.append(line)

            # Assign unique GID to each line if not already set
            if line.get_gid() is None:
                unique_gid = f"maidr-{uuid.uuid4()}"
                line.set_gid(unique_gid)

            label: str = line.get_label()  # type: ignore

            # Try to get the series name from legend labels
            line_type = ""
            if legend_labels and i < len(legend_labels):
                line_type = legend_labels[i]
            elif not label.startswith("_child"):
                line_type = label

            line_data = [
                {
                    MaidrKey.X: float(x),
                    MaidrKey.Y: float(y),
                    **({MaidrKey.FILL: line_type} if line_type else {}),
                }
                for x, y in line.get_xydata()  # type: ignore
            ]

            if line_data:
                all_lines_data.append(line_data)

        return all_lines_data if all_lines_data else None
