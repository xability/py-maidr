"""Bokeh support: ``maidr.show(p)`` for a Bokeh figure or layout.

``BokehMaidr`` imports Bokeh, so it is resolved on first use rather than
here: :mod:`maidr.api` imports this package's probe for every figure it is
handed, and a matplotlib user must not pay for a Bokeh import to be told
their figure is not a Bokeh one.
"""

from __future__ import annotations

from typing import Any

from maidr.bokeh.utils import is_bokeh_model

__all__ = ["BokehMaidr", "is_bokeh_model"]


def __getattr__(name: str) -> Any:
    """
    Import :class:`BokehMaidr` on first use, so ``maidr.bokeh`` stays light.

    Parameters
    ----------
    name : str
        The attribute asked for.

    Returns
    -------
    Any
        The ``BokehMaidr`` class.

    Raises
    ------
    AttributeError
        For any other name.
    """
    if name == "BokehMaidr":
        from maidr.bokeh.bokeh_maidr import BokehMaidr

        return BokehMaidr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
