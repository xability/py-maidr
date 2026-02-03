"""
Mixin for extracting format configuration from matplotlib axes.

This module provides a mixin class that can be used by plot classes
to extract axis formatting information for the MAIDR schema.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from matplotlib.axes import Axes

from maidr.util.format_config import extract_axis_format


class FormatExtractorMixin:
    """
    Mixin class for extracting format configuration from axes.

    This mixin provides methods to detect and extract formatting
    configurations from matplotlib axis formatters, which can then
    be included in the MAIDR schema.

    Examples
    --------
    >>> class MyPlot(MaidrPlot, FormatExtractorMixin):
    ...     def render(self):
    ...         schema = super().render()
    ...         format_config = self.extract_format(self.ax)
    ...         if format_config:
    ...             schema["format"] = format_config
    ...         return schema
    """

    @staticmethod
    def extract_format(ax: Axes) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        Extract format configuration from an axes object.

        This method detects matplotlib formatters applied to the x and y axes
        and converts them to MAIDR-compatible format configurations.

        Parameters
        ----------
        ax : Axes
            The matplotlib Axes object to extract formats from.

        Returns
        -------
        Dict[str, Dict[str, Any]] or None
            Dictionary with 'x' and/or 'y' keys containing format configurations,
            or None if no formats could be detected.

        Notes
        -----
        Supported formatter types:
        - StrMethodFormatter: Detected by parsing format string
        - PercentFormatter: Detected as percent type
        - ScalarFormatter: Detected for scientific notation
        - FormatStrFormatter: Detected by parsing old-style format string

        Format detection examples:
        - "${x:,.2f}" -> {"type": "currency", "currency": "USD", "decimals": 2}
        - "{x:.1%}" -> {"type": "percent", "decimals": 1}
        - "{x:.2e}" -> {"type": "scientific", "decimals": 2}

        Examples
        --------
        >>> from matplotlib import pyplot as plt
        >>> fig, ax = plt.subplots()
        >>> ax.yaxis.set_major_formatter('${x:,.2f}')
        >>> format_config = FormatExtractorMixin.extract_format(ax)
        >>> format_config
        {'y': {'type': 'currency', 'decimals': 2, 'currency': 'USD'}}
        """
        if ax is None:
            return None

        format_config = extract_axis_format(ax)

        # Return None if no formats were detected
        return format_config if format_config else None
