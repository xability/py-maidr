import io

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.layout_engine import PlaceHolderLayoutEngine
from matplotlib.transforms import Transform
from matplotlib.lines import Line2D
from typing import List, Optional, Tuple


def settle_layout(fig: Figure) -> None:
    """
    Settle the figure's layout so the axes sit where the SVG will draw them.

    :func:`data_to_svg_coords` reads the axes position, and that position is
    only final once the figure has been drawn: a draw runs the figure's own
    layout engine, if it has one (``layout="constrained"``, ``"tight"``,
    ``figure.autolayout``), applies each axes' aspect and places an axes
    that has a locator. It imposes no layout of its own. It used to run
    ``tight_layout``, which re-laid-out a figure that had none, so the chart
    no longer looked like the same figure shown without maidr, and replaced
    a constrained layout with a tight one.

    A figure without a layout engine is drawn without rendering anything,
    which places its axes as the SVG will. One with an engine is saved as an
    SVG, which is then thrown away: the engine places the axes around the
    text it measures, and the SVG's renderer measures text otherwise than
    the raster one a plain draw uses -- by as much as half a point once
    ``text.hinting`` is on, as it is by default. And an engine's pass starts
    from where the last one left the axes: a tight layout moves them again
    on its next pass, by an eighth of what it moved them on this one (0.8
    of a point, then 0.1, on a 3x3 inch figure). So the SVG is saved until
    the axes stop moving, at most :data:`_ENGINE_PASSES` times, and the
    chart's SVG, saved the same way, draws them where they then are.

    A draw measures the text extent of every artist on the figure, so an
    extraction converting its points one at a time paid for the whole
    figure once per point: 124 passes for four seaborn violins, nearly all
    of the render time (#704). Settle once per extraction, before the first
    conversion, and let the conversions be pure.

    Failures are swallowed: a figure that cannot be drawn here is still
    worth reading.

    Parameters
    ----------
    fig : Figure
        The figure whose layout to settle.
    """
    try:
        engine = fig.get_layout_engine()
        if engine is not None and not isinstance(engine, PlaceHolderLayoutEngine):
            _settle_engine(fig)
            return
        draw = getattr(fig, "draw_without_rendering", None)
        if draw is None:  # pragma: no cover - a matplotlib without it
            draw = fig.canvas.draw
        draw()
    except Exception:
        pass


#: The most SVG saves :func:`settle_layout` makes of a figure with a layout
#: engine. A tight layout's moves shrink about eightfold a pass, so the
#: fourth is a few thousandths of a point.
_ENGINE_PASSES = 4

#: How far, in points, the axes may move between two passes for the layout
#: to count as settled.
_SETTLED_POINTS = 0.01


def _settle_engine(fig: Figure) -> None:
    """Save ``fig`` as an SVG until its layout engine stops moving the axes."""
    width, height = (float(v) * 72 for v in fig.get_size_inches())
    scale = np.array([width, height, width, height])

    def positions() -> np.ndarray:
        return np.array([ax.get_position().bounds for ax in fig.axes]).reshape(-1, 4)

    before = positions()
    for _ in range(_ENGINE_PASSES):
        fig.savefig(io.StringIO(), format="svg")
        now = positions()
        if now.shape == before.shape and np.all(
            np.abs(now - before) * scale < _SETTLED_POINTS
        ):
            return
        before = now


def data_to_svg_coords(
    ax: Axes, x_data: np.ndarray, y_data: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Convert data coordinates to SVG coordinates using matplotlib transforms.
    Returns x_svg, y_svg arrays in SVG points.

    A pure transform: it reads the axes position as it stands, so call
    :func:`settle_layout` on the figure once before the first conversion of
    an extraction.
    """
    fig = getattr(ax, "figure", None)
    if fig is None:
        import matplotlib.pyplot as plt

        fig = plt.gcf()
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


def _clip_sentinel(transform: Transform) -> Optional[float]:
    """
    Return the coordinate a scale parks unrepresentable values on, if it clips.

    A clipping scale sends everything it cannot represent to one coordinate,
    so it stops being injective there; probing with values only such a scale
    would reject finds that coordinate without naming a scale or its constant.
    The probe looks downward only, since a lower bound is the one a scale
    parks values below; a scale rejecting on an upper bound, as logit does at
    1, answers with infinity rather than a sentinel.  That and a masking
    scale's NaN both fall to the finiteness check in :func:`to_scaled_coords`,
    which is why the guards there cover a mode each.

    This reads matplotlib's behavior rather than a promise, and would fail
    quietly: a release that stopped collapsing rejected values would leave the
    sentinel never found, and a curve touching zero on a log axis thinned
    against it again and drifting off the canvas.

    Parameters
    ----------
    transform : Transform
        A scale transform, as returned by ``Axis.get_transform()``.

    Returns
    -------
    float or None
        The sentinel coordinate, or ``None`` for a scale that never clips.
    """
    probe = transform.transform(np.array([-1.0, -2.0, -4.0]))
    if probe[0] == probe[1] == probe[2]:
        return float(probe[0])
    return None


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

    # Zero is the one clipped value the round trip below cannot see: a log
    # scale parks it on the sentinel, and inverting that underflows back to
    # zero, so the value appears to have survived the journey intact.  Ask the
    # scale where it parks what it rejects, and refuse anything sitting there.
    for transform, scaled in ((x_transform, x_scaled), (y_transform, y_scaled)):
        sentinel = _clip_sentinel(transform)
        if sentinel is not None and np.any(scaled == sentinel):
            return None

    # The finiteness check above catches only a scale that answers with
    # infinity or NaN.  A log scale clips instead, mapping an unrepresentable
    # value to a coordinate that reads as perfectly ordinary, so the round trip
    # is what stands between that value and a curve thinned against it.
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
