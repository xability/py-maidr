import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from typing import List, Optional, Tuple


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


def to_scaled_coords(
    ax: Axes, x_data: np.ndarray, y_data: np.ndarray
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Map data coordinates into the axes' scale space.

    What remains between scale space and the display is an affine map, so
    ratios of distances there are the ratios on screen — which is what makes
    reasoning about drawn distance in scale space valid at all.  Because an
    affine map cannot change those ratios, the answer holds whatever the
    figure layout turns out to be, so this neither needs nor waits for the
    axes' position and limits to settle.  A linear axis passes through
    unchanged; a log axis becomes its logarithm.

    One unmappable point rejects the whole batch rather than being dropped:
    a curve mapped point by point would mix two coordinate spaces, leaving
    the spacing it is thinned by — and any interpolation across it —
    meaningless.

    Parameters
    ----------
    ax : Axes
        The axes whose x and y scales apply.
    x_data, y_data : np.ndarray
        Data coordinates to map.

    Returns
    -------
    tuple of np.ndarray, or None
        The mapped coordinates, or ``None`` when a scale cannot represent this
        data faithfully — a log axis reaching zero or below, which matplotlib
        clips rather than maps.  Callers should stay on data coordinates then.
    """
    x_transform = ax.xaxis.get_transform()
    y_transform = ax.yaxis.get_transform()
    x_scaled = x_transform.transform(x_data)
    y_scaled = y_transform.transform(y_data)

    if not (np.all(np.isfinite(x_scaled)) and np.all(np.isfinite(y_scaled))):
        return None

    # The check above catches only a scale that answers with infinity or NaN.
    # A log scale clips instead, mapping an unrepresentable value to a sentinel
    # that reads as a perfectly ordinary coordinate, so the round trip is the
    # only thing standing between that value and a curve thinned against it.
    if not (
        np.allclose(
            x_transform.inverted().transform(x_scaled), x_data, rtol=1e-9, atol=0
        )
        and np.allclose(
            y_transform.inverted().transform(y_scaled), y_data, rtol=1e-9, atol=0
        )
    ):
        return None

    return x_scaled, y_scaled


def from_scaled_coords(
    ax: Axes, x_scaled: np.ndarray, y_scaled: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Invert :func:`to_scaled_coords`, returning data coordinates.

    Parameters
    ----------
    ax : Axes
        The axes whose x and y scales apply.
    x_scaled, y_scaled : np.ndarray
        Coordinates in the axes' scale space.

    Returns
    -------
    tuple of np.ndarray
        The same points in data coordinates.
    """
    return (
        ax.xaxis.get_transform().inverted().transform(x_scaled),
        ax.yaxis.get_transform().inverted().transform(y_scaled),
    )
