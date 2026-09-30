"""plotnine support: ``maidr.show(p)`` for a ``ggplot``.

``PlotnineMaidr`` imports plotnine, so it is resolved on first use rather than
here: :mod:`maidr.api` imports this package's probe for every figure it is
handed, and a matplotlib user must not pay for a plotnine import to be told
their figure is not a ``ggplot``.
"""

from __future__ import annotations

from typing import Any

from maidr.plotnine.utils import is_plotnine_plot

__all__ = ["PlotnineMaidr", "is_plotnine_plot"]


def __getattr__(name: str) -> Any:
    """
    Import :class:`PlotnineMaidr` on first use, so ``maidr.plotnine`` stays light.

    Parameters
    ----------
    name : str
        The attribute asked for.

    Returns
    -------
    Any
        The ``PlotnineMaidr`` class.

    Raises
    ------
    AttributeError
        For any other name.
    """
    if name == "PlotnineMaidr":
        from maidr.plotnine.plotnine_maidr import PlotnineMaidr

        return PlotnineMaidr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
