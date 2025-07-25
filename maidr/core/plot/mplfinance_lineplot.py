from typing import List, Union

from matplotlib.axes import Axes
import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.exception.extraction_error import ExtractionError
from maidr.util.mixin.extractor_mixin import LineExtractorMixin
from maidr.util.mplfinance_utils import MplfinanceDataExtractor
import uuid


class MplfinanceLinePlot(MaidrPlot, LineExtractorMixin):
    """
    Specialized line plot class for mplfinance moving averages.

    This class handles the extraction and processing of moving average data from mplfinance
    plots, including proper date conversion, NaN filtering, and moving average period detection.
    """

    def __init__(self, ax: Axes, **kwargs):
        super().__init__(ax, PlotType.LINE)

    def _get_selector(self) -> Union[str, List[str]]:
        """Return selectors for all lines that have data."""
        all_lines = self.ax.get_lines()
        if not all_lines:
            return ["g[maidr='true'] > path"]

        selectors = []
        for line in all_lines:
            # Only create selectors for lines that have data
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
        """Extract data from mplfinance moving average lines."""
        data = self._extract_line_data()

        if data is None:
            raise ExtractionError(self.type, None)

        return data

    def _extract_line_data(self) -> Union[List[List[dict]], None]:
        """
        Extract data from all line objects and return as separate arrays.

        This method handles mplfinance-specific logic including:
        - Date conversion from matplotlib date numbers
        - NaN filtering for moving averages
        - Moving average period detection
        - Proper data validation

        Returns
        -------
        list[list[dict]] | None
            List of lists, where each inner list contains dictionaries with x,y coordinates
            and line identifiers for one line, or None if the plot data is invalid.
        """
        all_lines = self.ax.get_lines()
        if not all_lines:
            return None

        all_lines_data = []

        for line_idx, line in enumerate(all_lines):
            xydata = line.get_xydata()
            if xydata is None or not xydata.size:  # type: ignore
                continue

            self._elements.append(line)

            # Assign unique GID to each line if not already set
            if line.get_gid() is None:
                unique_gid = f"maidr-{uuid.uuid4()}"
                line.set_gid(unique_gid)

            label: str = line.get_label()  # type: ignore
            line_data = []

            # Check if this line has date numbers from mplfinance
            date_nums = getattr(line, "_maidr_date_nums", None)

            # Convert xydata to list of points
            for i, (x, y) in enumerate(line.get_xydata()):  # type: ignore
                # Skip points with NaN or inf values to prevent JSON parsing errors
                if np.isnan(x) or np.isnan(y) or np.isinf(x) or np.isinf(y):
                    continue

                # Handle x-value conversion - could be string (date) or numeric
                if isinstance(x, str):
                    x_value = x  # Keep string as-is (for dates)
                else:
                    # Check if we have date numbers from mplfinance
                    if date_nums is not None and i < len(date_nums):
                        # Use the date number to convert to date string
                        date_num = float(date_nums[i])
                        x_value = self._convert_x_to_date(date_num)
                    else:
                        x_value = float(x)  # Convert numeric to float

                point_data = {
                    MaidrKey.X: x_value,
                    MaidrKey.Y: float(y),
                    MaidrKey.FILL: (label if not label.startswith("_child") else ""),
                }
                line_data.append(point_data)

            if line_data:
                all_lines_data.append(line_data)

        return all_lines_data if all_lines_data else None

    def _convert_x_to_date(self, x_value: float) -> str:
        """
        Convert x-coordinate to date string for mplfinance plots.

        This method uses the MplfinanceDataExtractor utility to convert
        matplotlib date numbers to proper date strings.

        Parameters
        ----------
        x_value : float
            The x-coordinate value (matplotlib date number)

        Returns
        -------
        str
            Date string in YYYY-MM-DD format
        """
        return MplfinanceDataExtractor._convert_date_num_to_string(x_value)

    def _extract_moving_average_periods(self) -> List[str]:
        """
        Extract all moving average periods from the _maidr_ma_period attributes set by the mplfinance patch.

        Returns
        -------
        List[str]
            List of moving average periods (e.g., ["3", "6", "30"]).
        """
        all_lines = self.ax.get_lines()
        periods = []
        for line in all_lines:
            # Get the period that was stored by the mplfinance patch
            ma_period = getattr(line, "_maidr_ma_period", None)
            if ma_period is not None:
                periods.append(str(ma_period))

        # Remove duplicates and sort
        periods = sorted(list(set(periods)))

        return periods

    def _extract_moving_average_period(self) -> str:
        """
        Extract the moving average period from the _maidr_ma_period attribute set by the mplfinance patch.

        Returns
        -------
        str
            The moving average period (e.g., "3", "6", "30") or empty string if no period found.
        """
        periods = self._extract_moving_average_periods()
        return periods[0] if periods else ""

    def render(self) -> dict:
        base_schema = super().render()
        base_schema[MaidrKey.TITLE] = "Moving Average Line Plot"
        base_schema[MaidrKey.AXES] = self._extract_axes_data()
        base_schema[MaidrKey.DATA] = self._extract_plot_data()
        if self._support_highlighting:
            base_schema[MaidrKey.SELECTOR] = self._get_selector()
        return base_schema
