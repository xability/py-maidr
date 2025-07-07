"""
Utility functions for detecting plot types and determining appropriate plot classes.
"""

from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from typing import List, Union


class PlotDetectionUtils:
    """
    Utility class for detecting plot characteristics and determining appropriate plot classes.
    """

    @staticmethod
    def is_mplfinance_bar_plot(**kwargs) -> bool:
        """
        Detect if this is an mplfinance bar plot based on kwargs.

        Parameters
        ----------
        **kwargs : dict
            Keyword arguments passed to the plot factory

        Returns
        -------
        bool
            True if this is an mplfinance bar plot
        """
        return "_maidr_patches" in kwargs or "_maidr_date_nums" in kwargs

    @staticmethod
    def is_mplfinance_line_plot(ax: Axes, **kwargs) -> bool:
        """
        Detect if this is an mplfinance line plot based on kwargs or Line2D attributes.

        Parameters
        ----------
        ax : Axes
            The matplotlib axes object
        **kwargs : dict
            Keyword arguments passed to the plot factory

        Returns
        -------
        bool
            True if this is an mplfinance line plot
        """
        # Check kwargs first (more efficient)
        if "_maidr_date_nums" in kwargs:
            return True

        # Check Line2D objects for mplfinance attributes
        try:
            for line in ax.get_lines():
                if isinstance(line, Line2D) and hasattr(line, "_maidr_date_nums"):
                    return True
        except (AttributeError, TypeError):
            # Handle cases where ax doesn't have get_lines() method (e.g., Mock objects)
            pass

        return False

    @staticmethod
    def is_mplfinance_candlestick_plot(**kwargs) -> bool:
        """
        Detect if this is an mplfinance candlestick plot based on kwargs.

        Parameters
        ----------
        **kwargs : dict
            Keyword arguments passed to the plot factory

        Returns
        -------
        bool
            True if this is an mplfinance candlestick plot
        """
        return any(key.startswith("_maidr_") for key in kwargs.keys())

    @staticmethod
    def should_use_candlestick_plot(
        ax: Union[Axes, List[Axes], List[List[Axes]]], **kwargs
    ) -> bool:
        """
        Determine if a candlestick plot should be used based on axes structure.

        Parameters
        ----------
        ax : Union[Axes, List[Axes], List[List[Axes]]]
            The matplotlib axes object(s)
        **kwargs : dict
            Keyword arguments passed to the plot factory

        Returns
        -------
        bool
            True if candlestick plot should be used
        """
        # Check if we have mplfinance-specific kwargs
        if PlotDetectionUtils.is_mplfinance_candlestick_plot(**kwargs):
            return True

        # Check if we have a list of axes (typical for candlestick plots)
        if isinstance(ax, list):
            return True

        return False

    @staticmethod
    def get_candlestick_axes(
        ax: Union[Axes, List[Axes], List[List[Axes]]],
    ) -> List[Axes]:
        """
        Extract and normalize axes for candlestick plots.

        Parameters
        ----------
        ax : Union[Axes, List[Axes], List[List[Axes]]]
            The matplotlib axes object(s)

        Returns
        -------
        List[Axes]
            Normalized list of axes for candlestick plotting
        """
        if isinstance(ax, list):
            if ax and isinstance(ax[0], list):
                # Handle nested list case: [[ax1, ax2]]
                return ax[0]
            else:
                # Handle simple list case: [ax1, ax2]
                return ax
        else:
            # Handle single axis case
            return [ax]
