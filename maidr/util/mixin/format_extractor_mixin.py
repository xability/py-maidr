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
    The returned mapping is intended to be **nested into each per-axis
    ``AxisConfig``** object under its ``format`` key. It must NOT be placed as
    a sibling of ``x``/``y`` inside ``axes`` (that legacy shape has been
    removed).

    >>> class MyPlot(MaidrPlot, FormatExtractorMixin):
    ...     def render(self):
    ...         schema = super().render()
    ...         format_config = self.extract_format(self.ax)
    ...         if format_config:
    ...             # Nest per-axis: axes["x"]["format"] = format_config["x"]
    ...             for axis_key, fmt in format_config.items():
    ...                 schema["axes"][axis_key]["format"] = fmt
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
            Dictionary with 'x' and/or 'y' keys containing ``AxisFormat``
            configurations, or None if no formats could be detected. The caller
            is responsible for nesting these into the corresponding
            ``axes[x|y|z].format`` fields of the MAIDR schema.

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
