from __future__ import annotations

import sys
from typing import Any

# Re-exported under the name the Bokeh modules import it by; the walk out of
# the package is shared with the plotnine adapter.
from maidr.util.caller_warning import warn_at_caller as warn  # noqa: F401


def is_bokeh_model(obj: Any) -> bool:
    """
    Whether ``obj`` is a Bokeh plot or layout, without importing Bokeh.

    An instance of a Bokeh model cannot exist unless the package is loaded,
    so ``sys.modules`` settles the negative case for free -- the same probe
    :func:`maidr.altair.utils.is_altair_chart` uses, and for the same
    reason: ``maidr.render`` asks this of every figure, and importing Bokeh
    to answer "no" for a matplotlib one would cost every user the import.
    ``.get() is None`` also covers an import blocked with a ``None`` entry.
    ``bokeh.models`` as well as ``bokeh``: a session that ran only
    ``import bokeh`` holds no model either, and asking the top-level package
    would import the models on every ``maidr.render`` to learn that.

    Parameters
    ----------
    obj : Any
        The object to check.

    Returns
    -------
    bool
        True for a ``LayoutDOM`` -- a ``figure``/``Plot``, ``gridplot``,
        ``row``/``column``, ``GridBox`` or ``Tabs``.
    """
    if sys.modules.get("bokeh") is None or sys.modules.get("bokeh.models") is None:
        return False
    try:
        from bokeh.models import LayoutDOM
    except ImportError:
        return False
    return isinstance(obj, LayoutDOM)
