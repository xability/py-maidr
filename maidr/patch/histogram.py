from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import wrapt

import numpy as np
from matplotlib.axes import Axes
from matplotlib.container import BarContainer
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D
import uuid

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly, common, wrap_seaborn


@wrapt.patch_function_wrapper(Axes, "hist")
def mpl_hist(
    wrapped, _, args, kwargs
) -> tuple[
    np.ndarray | list[np.ndarray],
    np.ndarray,
    BarContainer | Polygon | list[BarContainer | Polygon],
]:
    """
    Patch matplotlib Axes.hist to register HIST layer for MAIDR.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch `ax.hist()`.
        n, bins, plot = _draw_quietly(wrapped, args, kwargs)

    # Extract the histogram data points for MAIDR from the plots.
    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(ax, PlotType.HIST)

    # Return to the caller.
    return n, bins, plot


def _prospective_axes(kwargs: dict) -> Axes | None:
    """
    The axes ``histplot`` is about to draw on, resolved before it draws.

    Named without drawing anything: an explicit ``ax=`` is the answer when
    given, and otherwise seaborn will take ``plt.gca()``, which is only asked
    for when a figure already exists so that a call on a clean slate does not
    conjure one early.

    Parameters
    ----------
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    Axes or None
        The axes to snapshot, or None when there is nothing drawn yet.
    """
    ax = kwargs.get("ax")
    if ax is not None:
        return ax
    return plt.gcf().gca() if plt.get_fignums() else None


def _container_ids(ax: Axes | None) -> set[int]:
    """The identities of the containers an axes holds right now."""
    return {id(container) for container in getattr(ax, "containers", ()) or ()}


def _drew_bars(plot: Any, before: set[int]) -> bool:
    """
    Whether *this call* drew a histogram made of bars.

    `sns.histplot(x=..., y=...)` is a **2D** histogram: seaborn draws it as a
    ``QuadMesh`` of joint counts, not as bars. `hist` promises one bin per bar
    with a count, which such a layer has neither of -- so registering it
    promises a reading nothing can produce, and extraction then took the whole
    figure down with it. `sns.jointplot(kind="hist")` produced no HTML at all,
    and so did any supported chart that happened to share the axes (#388).

    Asked of the artists rather than of the arguments, because "did this draw
    bars" is the question the extractor actually needs answered, and a `y=`
    keyword is seaborn's spelling of it rather than the thing itself.

    Asked of the containers *this call added* rather than of everything on the
    axes, which is the difference between declining and lying. An axes that
    already holds bars -- `sns.barplot(ax=ax)` first, then a bivariate
    `histplot(ax=ax)` -- would otherwise answer True for someone else's
    artists, and `extract_container` returns the first container on the axes,
    so the `hist` layer would describe the *barplot's* bars with bin edges
    invented for them:

        registered: ['bar', 'hist']
          bar   [{'x': 'a', 'y': 8.67}, ...]
          hist  [{'y': 8.67, 'xMin': -0.4, 'xMax': 0.4}, ...]

    Right numbers, wrong chart, and nothing raised -- which is worse than the
    crash this function was added to prevent.

    Parameters
    ----------
    plot : Any
        Whatever the patched call returned.
    before : set of int
        Identities of the containers the axes held before the call.

    Returns
    -------
    bool
        True when this call added at least one ``BarContainer``.
    """
    try:
        ax = FigureManager.get_axes(plot)
    except Exception:  # pragma: no cover - `common` already resolved this once
        return False
    if ax is None or not ax.containers:
        return False
    return any(
        isinstance(container, BarContainer) and id(container) not in before
        for container in ax.containers
    )


def sns_hist(wrapped, instance, args, kwargs) -> Axes:
    """
    Patch seaborn.histplot to register HIST and (if kde=True) SMOOTH layers for MAIDR.

    A bivariate histogram is left unregistered rather than read wrongly; see
    `_drew_bars`.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    before = _container_ids(_prospective_axes(kwargs))

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    if not _drew_bars(drawn, before):
        return drawn

    # Register the histogram as HIST as before
    ax = common(PlotType.HIST, lambda *a, **k: drawn, instance, args, kwargs)
    # Only register KDE overlay as SMOOTH if kde=True was set
    kde_enabled = kwargs.get("kde", False)
    if kde_enabled:
        # Find the KDE line(s) and register as SMOOTH
        axes = ax if isinstance(ax, Axes) else getattr(ax, "axes", None)
        if axes is not None:
            for line in axes.get_lines():
                if isinstance(line, Line2D):
                    if line.get_gid() is None:
                        gid = f"maidr-{uuid.uuid4()}"
                        line.set_gid(gid)
                    common(
                        PlotType.SMOOTH,
                        lambda *a, **k: axes,
                        instance,
                        args,
                        dict(kwargs, regression_line=line),
                    )
    return ax


# Patch seaborn function at both names it answers to; see `wrap_seaborn`.
wrap_seaborn("histplot", sns_hist)
