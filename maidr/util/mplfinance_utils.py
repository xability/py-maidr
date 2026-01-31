"""
Utility functions for handling mplfinance-specific data extraction and processing.
"""

import re
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from typing import List, Optional


class MplfinanceDataExtractor:
    """
    Utility class for extracting and processing mplfinance-specific data.

    This class handles the conversion of mplfinance plot elements (patches, collections)
    into standardized data formats that can be used by the core plot classes.
    """

    @staticmethod
    def extract_volume_data(
        volume_patches: List[Rectangle], date_nums: Optional[List[float]] = None
    ) -> List[dict]:
        """
        Extract volume data from mplfinance Rectangle patches.

        Parameters
        ----------
        volume_patches : List[Rectangle]
            List of Rectangle patches representing volume bars
        date_nums : Optional[List[float]], default=None
            List of matplotlib date numbers corresponding to the patches

        Returns
        -------
        List[dict]
            List of dictionaries with 'x' and 'y' keys for volume data
        """
        if not volume_patches:
            return []

        formatted_data = []

        # Sort patches by x-coordinate to maintain order
        sorted_patches = sorted(volume_patches, key=lambda p: p.get_x())

        for i, patch in enumerate(sorted_patches):
            height = patch.get_height()

            # Use date mapping if available, otherwise use index
            if date_nums is not None and i < len(date_nums):
                date_num = date_nums[i]
                x_label = MplfinanceDataExtractor._convert_date_num_to_string(date_num)
            else:
                x_label = f"date_{i:03d}"

            formatted_data.append({"x": str(x_label), "y": float(height)})

        return formatted_data

    @staticmethod
    def clean_axis_label(label: str) -> str:
        """
        Clean up axis labels by removing LaTeX formatting.

        Parameters
        ----------
        label : str
            The original axis label

        Returns
        -------
        str
            Cleaned axis label
        """
        if not label or not isinstance(label, str):
            return label

        # Removes LaTeX-like scientific notation, e.g., "$10^{6}$"
        cleaned_label = re.sub(r"\s*\$.*?\$", "", label).strip()
        return cleaned_label if cleaned_label else label

    @staticmethod
    def _convert_date_num_to_string(date_num: float) -> str:
        """
        Convert matplotlib date number to date string.

        Parameters
        ----------
        date_num : float
            Matplotlib date number

        Returns
        -------
        str
            Date string in YYYY-MM-DD format or fallback index
        """
        try:
            # Check if this looks like a matplotlib date number (typically > 700000)
            if date_num > 700000:
                date_dt = mdates.num2date(date_num)
                if hasattr(date_dt, "replace"):
                    date_dt = date_dt.replace(tzinfo=None)
                return str(date_dt)
            elif date_num > 1000:
                # Try converting as if it's a pandas timestamp
                try:
                    import pandas as pd

                    date_dt = pd.to_datetime(date_num, unit="D")
                    return str(date_dt)
                except (ValueError, TypeError):
                    pass
        except (ValueError, TypeError, OverflowError):
            pass

        # Fallback to index-based date string
        return f"date_{int(date_num):03d}"
