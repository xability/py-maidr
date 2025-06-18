from maidr.core.enum.plot_type import PlotType
from typing import List


def deduplicate_smooth_and_line(plots: List[object]) -> List[object]:
    """
    If any SMOOTH plots exist, remove all LINE plots from the list.
    """
    has_smooth = any(getattr(plot, "type", None) == PlotType.SMOOTH for plot in plots)
    if has_smooth:
        return [plot for plot in plots if getattr(plot, "type", None) != PlotType.LINE]
    return plots
