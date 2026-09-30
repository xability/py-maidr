"""A warning that names the line of the caller's code, not a line of maidr's.

The Bokeh and plotnine adapters reach their warnings several frames inside the
package, and a fixed ``stacklevel`` would point the reader at one of those
frames. A leaf module: nothing here imports another ``maidr`` module, so either
adapter can import it without pulling in the other.
"""

from __future__ import annotations

import os
import sys
import warnings

#: The ``maidr`` package directory, whose frames are walked out of.
_PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def warn_at_caller(message: str) -> None:
    """
    Raise a ``UserWarning`` attributed to the caller's own code.

    Walks out of the package, so the warning names the line that called
    ``maidr.show``, ``maidr.render`` or ``maidr.save_html``.

    Parameters
    ----------
    message : str
        The warning text.
    """
    # `stacklevel=2` is the frame calling this function; count outwards from
    # there until the frame is no longer maidr's.
    level = 2
    frame = sys._getframe(1)
    while frame is not None and os.path.abspath(frame.f_code.co_filename).startswith(
        _PACKAGE
    ):
        frame = frame.f_back
        level += 1
    warnings.warn(message, UserWarning, stacklevel=level)
