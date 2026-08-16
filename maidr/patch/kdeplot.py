from __future__ import annotations

import uuid

import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
from maidr.core.enum import PlotType
from maidr.patch.common import _draw_quietly, common, wrap_seaborn
from maidr.patch.histogram import _plotter_axes
from maidr.core.context_manager import ContextManager
from maidr.util.svg_utils import unique_lines_by_xy


def _register_smooth(ax: Axes | None, instance, args, kwargs) -> None:
    """
    Register every KDE curve on one axes as a SMOOTH layer.

    Split out of :func:`kde` so ``seaborn.displot(kind="kde")`` can reuse it.
    ``displot`` does not import ``kdeplot`` -- it drives
    ``_DistributionPlotter`` directly -- so its panels reached neither name
    ``wrap_seaborn`` patches and were left to the line patch, which typed them
    ``line`` where the axes-level function gives ``smooth`` (#446). A fitted
    curve is not a series of observations, and `smooth` is the type that says
    so.

    Parameters
    ----------
    ax : Axes or None
        The axes to read. ``None`` is a no-op, so a caller that could not
        resolve one does nothing rather than guessing.
    instance, args, kwargs
        Forwarded to :func:`maidr.patch.common.common` unchanged.
    """
    if ax is not None:
        # Register all unique Line2D objects
        lines = [line for line in ax.get_lines() if isinstance(line, Line2D)]
        for kde_line in unique_lines_by_xy(lines):
            if kde_line.get_gid() is None:
                gid = f"maidr-{uuid.uuid4()}"
                kde_line.set_gid(gid)
            common(
                PlotType.SMOOTH,
                lambda *a, **k: ax,
                instance,
                args,
                dict(kwargs, regression_line=kde_line),
            )
        # Register all PolyCollection boundaries as SMOOTH
        for poly in [c for c in ax.collections if isinstance(c, PolyCollection)]:
            if poly.get_paths():
                path = poly.get_paths()[0]
                boundary = path.vertices
                # Defensive: ensure boundary is a numpy array
                boundary = np.asarray(boundary)
                kde_line = Line2D(boundary[:, 0], boundary[:, 1])
                gid = f"maidr-{uuid.uuid4()}"
                kde_line.set_gid(gid)
                poly.set_gid(gid)  # Assign gid to PolyCollection group
                common(
                    PlotType.SMOOTH,
                    lambda *a, **k: ax,
                    instance,
                    args,
                    dict(
                        kwargs,
                        regression_line=kde_line,
                        poly_gid=gid,
                        is_polycollection=True,
                    ),
                )


def kde(wrapped, instance, args, kwargs) -> Axes | Line2D | PolyCollection:
    """
    Patch for seaborn.kdeplot: register all unique lines and/or filled boundaries as SMOOTH.
    """
    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)
    ax = plot if isinstance(plot, Axes) else getattr(plot, "axes", None)
    _register_smooth(ax, instance, args, kwargs)
    return plot


def sns_distribution_density(wrapped, instance, args, kwargs):
    """
    Register the KDE panels ``seaborn.displot(kind="kde")`` draws.

    The same gap the histogram half of #446 describes, one method along:
    ``displot`` drives ``_DistributionPlotter`` rather than importing
    ``kdeplot``, so its curves were seen only by the line patch and typed
    ``line``. Measured against the axes-level function on the same data::

        sns.kdeplot(df, x="v")              -> smooth
        sns.displot(df, x="v", kind="kde")  -> line

    ``kdeplot`` sets the internal context around its own call, so this
    declines when it is the one driving and no panel registers twice.

    One call covers the whole grid, so every panel is registered rather than
    only ``plotter.ax`` -- see ``_plotter_axes`` in
    :mod:`maidr.patch.histogram` for why that matters.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    for ax in _plotter_axes(instance):
        _register_smooth(ax, instance, args, kwargs)

    return drawn


# Patch seaborn kdeplot
wrap_seaborn("kdeplot", kde)

# And the plotter method beneath it, which is the only thing `displot`
# drives; see `sns_distribution_density`.
wrapt.wrap_function_wrapper(
    "seaborn.distributions",
    "_DistributionPlotter.plot_univariate_density",
    sns_distribution_density,
)
