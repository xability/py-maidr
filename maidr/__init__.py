from __future__ import annotations

__version__ = "1.14.0"

# --- Matplotlib backend activation -----------------------------------------
# Auto-activate the maidr backend so ``plt.show()`` renders accessible HTML.
#
# We skip activation when the user has explicitly set a **non-inline** backend
# via the ``MPLBACKEND`` environment variable (e.g. ``MPLBACKEND=TkAgg``) to
# avoid overriding interactive GUI backends.  In that case ``plt.show()`` uses
# their chosen backend and users can still call ``maidr.show()`` for accessible
# output.
#
# In Jupyter, ipykernel sets ``MPLBACKEND=module://matplotlib_inline.backend_inline``
# at kernel startup — this is *not* a user choice, so we override it.
#
# Additionally, ipykernel's ``configure_inline_support()`` re-overrides the
# backend when pyplot is first imported.  Since maidr's own modules import
# pyplot (via ``maidr.core.maidr``), the override happens *during*
# ``import maidr``.  To handle this we call ``_activate_backend()`` **twice**:
# once before our imports (covers non-Jupyter) and once after (reclaims the
# backend after ipykernel's override).
#
# Alternatives considered:
#   - IPython post-import hook: Would avoid the dual-call pattern but couples
#     maidr to IPython internals and does not work outside IPython.
#   - Lazy activation on first plot call: Would delay the cost but risks
#     missing figures created before the first patched call.
#   - Patching plt.show() via wrapt: Consistent with other patches but the
#     backend protocol is the canonical matplotlib extension point.
# The dual-call approach is the simplest that works across Jupyter, IPython,
# and plain Python without depending on IPython internals.
import logging
import os
import sys

_logger = logging.getLogger(__name__)

# Backend strings that ipykernel sets by default — not a user choice.
_INLINE_BACKENDS: tuple[str, ...] = (
    "module://matplotlib_inline.backend_inline",
    "module://ipykernel.pylab.backend_inline",  # legacy (pre-2021)
)


def _activate_backend() -> None:
    """Set the maidr backend, handling Jupyter's inline backend override.

    When the user has explicitly chosen a non-inline backend (e.g.
    ``MPLBACKEND=TkAgg``), we respect that and skip activation.  When
    ``MPLBACKEND`` is set to ``matplotlib_inline`` (ipykernel's default),
    we treat it as unset and override it.

    When pyplot is already in ``sys.modules`` (e.g. after ipykernel's
    ``configure_inline_support()`` has fired), ``matplotlib.use()`` is a
    no-op, so we go straight to ``plt.switch_backend()`` which actually
    changes the active backend.
    """
    try:
        import matplotlib
    except ImportError:
        # matplotlib is not installed — nothing to activate.
        return

    mplbackend = os.environ.get("MPLBACKEND", "")
    # Skip only when the user explicitly chose a non-inline backend.
    # ipykernel sets MPLBACKEND to matplotlib_inline by default — override that.
    if mplbackend and mplbackend not in _INLINE_BACKENDS:
        return

    # Also respect a backend set programmatically via matplotlib.use() (no env
    # var).  "agg" is the default non-interactive backend and is safe to
    # override; anything else is a deliberate user choice.
    current_backend = matplotlib.get_backend().lower()
    if (
        current_backend
        and current_backend not in ("agg", "module://maidr.backend")
        and current_backend not in (b.lower() for b in _INLINE_BACKENDS)
    ):
        return

    if "matplotlib.pyplot" in sys.modules:
        # pyplot already loaded — matplotlib.use() would only warn and do
        # nothing.  switch_backend() is the correct API post-pyplot-import.
        import matplotlib.pyplot as plt

        try:
            plt.switch_backend("module://maidr.backend")
        except ImportError:
            _logger.debug(
                "Failed to switch matplotlib backend to maidr; "
                "maidr.backend module could not be imported.",
                exc_info=True,
            )
    else:
        # pyplot not yet loaded — matplotlib.use() is the safe pre-import API.
        try:
            matplotlib.use("module://maidr.backend")
        except ImportError:
            _logger.debug(
                "Failed to set matplotlib backend to maidr; "
                "maidr.backend module could not be imported.",
                exc_info=True,
            )


# First call: sets the backend config before pyplot is imported.
# In non-Jupyter environments this is sufficient.
_activate_backend()

from .api import close, render, save_html, show, stacked  # noqa: E402
from .core import Maidr  # noqa: E402, F401
from .core.enum import PlotType  # noqa: E402, F401
from .patch import (  # noqa: E402, F401
    barplot,
    boxplot,
    clear,
    heatmap,
    highlight,
    histogram,
    lineplot,
    scatterplot,
    regplot,
    kdeplot,
    candlestick,
    mplfinance,
    violinplot,
)

# Second call: reclaim the backend after maidr's own imports.
# maidr.core.maidr imports matplotlib.pyplot, which in Jupyter triggers
# ipykernel's configure_inline_support() and overrides our backend with
# matplotlib_inline.  This call sees pyplot in sys.modules and uses
# plt.switch_backend() to restore the maidr backend.
_activate_backend()

__all__ = [
    "close",
    "render",
    "save_html",
    "show",
    "stacked",
]
