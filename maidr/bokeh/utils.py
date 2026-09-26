from __future__ import annotations

import os
import sys
import warnings
from typing import Any


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


def warn(message: str) -> None:
    """
    Raise a ``UserWarning`` attributed to the caller's own code.

    The Bokeh path reaches its warnings several frames inside maidr, and a
    fixed ``stacklevel`` would point the reader at one of those frames. This
    walks out of the package instead, so the warning names the line that
    called ``maidr.show`` or ``maidr.save_html``.

    Parameters
    ----------
    message : str
        The warning text.
    """
    import maidr

    package = os.path.dirname(os.path.abspath(maidr.__file__))
    # `stacklevel=2` is the frame calling this function; count outwards from
    # there until the frame is no longer maidr's.
    level = 2
    frame = sys._getframe(1)
    while frame is not None and os.path.abspath(frame.f_code.co_filename).startswith(
        package
    ):
        frame = frame.f_back
        level += 1
    warnings.warn(message, UserWarning, stacklevel=level)
