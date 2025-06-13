import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from typing import List, Tuple


def data_to_svg_coords(
    ax: Axes, x_data: np.ndarray, y_data: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Convert data coordinates to SVG coordinates using matplotlib transforms.
    Returns x_svg, y_svg arrays in SVG points.
    """
    fig = getattr(ax, "figure", None)
    if fig is None:
        import matplotlib.pyplot as plt

        fig = plt.gcf()
    try:
        fig.tight_layout()
    except Exception:
        pass
    xy_disp = ax.transData.transform(np.column_stack([x_data, y_data]))
    xy_figpix = fig.transFigure.inverted().transform(xy_disp)
    fig_width_pts = fig.get_size_inches()[0] * 72
    fig_height_pts = fig.get_size_inches()[1] * 72
    x_svg = xy_figpix[:, 0] * fig_width_pts
    y_svg = (1 - xy_figpix[:, 1]) * fig_height_pts
    return x_svg, y_svg


def unique_lines_by_xy(lines: List[Line2D]) -> List[Line2D]:
    """
    Deduplicate lines by rounded xy data (8 decimals). Only lines with >0 points are kept.
    """
    seen_xy = set()
    unique_lines = []
    for line in lines:
        xy = np.asarray(line.get_xydata())
        if xy.shape[0] == 0:
            continue
        xy_rounded = tuple(map(tuple, np.round(xy, 8)))
        if xy_rounded not in seen_xy:
            seen_xy.add(xy_rounded)
            unique_lines.append(line)
    return unique_lines
