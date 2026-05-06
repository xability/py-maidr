from __future__ import annotations

__version__ = "1.18.0"

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
import warnings

_logger = logging.getLogger(__name__)

# Backend strings that ipykernel sets by default — not a user choice.
_INLINE_BACKENDS: tuple[str, ...] = (
    "module://matplotlib_inline.backend_inline",
    "module://ipykernel.pylab.backend_inline",  # legacy (pre-2021)
)


# The platform's original backend (e.g. "macosx", "TkAgg") saved before
# maidr overrides it, so that ``maidr.set_backend(use_maidr=False)`` can
# restore it.
# NOTE: No lock is needed — this is only written at import time (single-
# threaded by the GIL and Python's import lock).  Concurrent threads that
# later call set_backend() only *read* this value.
_original_backend: str | None = None
_backend_message_shown: bool = False


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
    global _original_backend, _backend_message_shown

    try:
        import matplotlib
    except ImportError:
        # matplotlib is not installed — nothing to activate.
        return

    # Save the original backend once, before we override it.
    # Guard against saving our own backend (could happen if _activate_backend
    # is called after maidr is already active).
    if _original_backend is None:
        current = matplotlib.get_backend()
        if current != "module://maidr.backend":
            _original_backend = current

    mplbackend = os.environ.get("MPLBACKEND", "")
    # Skip only when the user explicitly chose a non-inline backend.
    # ipykernel sets MPLBACKEND to matplotlib_inline by default — override that.
    if mplbackend and mplbackend not in _INLINE_BACKENDS:
        return

    if "matplotlib.pyplot" in sys.modules:
        # pyplot already loaded — matplotlib.use() would only warn and do
        # nothing.  switch_backend() is the correct API post-pyplot-import.
        import matplotlib.pyplot as plt

        try:
            plt.switch_backend("module://maidr.backend")
            if not _backend_message_shown:
                warnings.warn(
                    "maidr: Setting matplotlib backend to maidr. "
                    "To revert, use: maidr.set_backend(use_maidr=False)",
                    stacklevel=2,
                )
                _backend_message_shown = True
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
            if not _backend_message_shown:
                warnings.warn(
                    "maidr: Setting matplotlib backend to maidr. "
                    "To revert, use: maidr.set_backend(use_maidr=False)",
                    stacklevel=2,
                )
                _backend_message_shown = True
        except ImportError:
            _logger.debug(
                "Failed to set matplotlib backend to maidr; "
                "maidr.backend module could not be imported.",
                exc_info=True,
            )


def set_backend(use_maidr: bool = True) -> None:
    """Switch the matplotlib backend between maidr and the platform default.

    When ``use_maidr=True``, the maidr backend is activated so that
    ``plt.show()`` renders accessible HTML output.  When
    ``use_maidr=False``, the original platform backend is restored
    (e.g. ``macosx``, ``TkAgg``, or ``inline`` in Jupyter).

    In Jupyter notebooks, restoring the inline backend requires special
    handling to re-register the ``post_execute`` hooks that auto-display
    figures.  This is handled automatically.

    Parameters
    ----------
    use_maidr : bool, optional
        If ``True`` (default), activate the maidr accessible backend.
        If ``False``, restore the original matplotlib backend that was
        active before maidr was imported.

    Examples
    --------
    >>> import maidr
    >>> maidr.set_backend(use_maidr=False)   # use platform default backend
    >>> maidr.set_backend(use_maidr=True)    # back to maidr

    Notes
    -----
    ``maidr.show()`` always renders accessible output regardless of the
    active backend.  ``set_backend`` only controls the behavior of
    ``plt.show()``.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        _logger.debug("matplotlib is not installed; cannot set backend.")
        return

    if use_maidr:
        plt.switch_backend("module://maidr.backend")
        return

    backend = _original_backend or "agg"

    # In Jupyter, the inline backend needs special re-initialization
    # to restore the post_execute hooks that auto-display figures.
    if backend.lower() in (b.lower() for b in _INLINE_BACKENDS):
        try:
            from IPython import get_ipython

            ip = get_ipython()
            if ip is not None:
                ip.run_line_magic("matplotlib", "inline")
                return
        except (ImportError, AttributeError):
            pass

    plt.switch_backend(backend)


# First call: sets the backend config before pyplot is imported.
# In non-Jupyter environments this is sufficient.
_activate_backend()

from .api import (  # noqa: E402
    close,
    get_use_cdn,
    init_notebook,
    render,
    save_html,
    set_use_cdn,
    show,
    stacked,
)
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
from .util.dependencies import (  # noqa: E402
    bundled_css_path,
    bundled_js_path,
    maidr_js_version,
    read_bundled_js,
)

# Second call: reclaim the backend after maidr's own imports.
# NOTE: See the "Matplotlib backend activation" block at the top of this
# file for why two calls are needed (Jupyter's configure_inline_support).
_activate_backend()


# Auto-inject the bundle into the notebook DOM once on import.
# This is the Plotly / Bokeh "load-once" pattern: calling
# ``init_notebook()`` from user code is optional because we do it
# implicitly here.  In non-notebook contexts (``Environment.is_notebook()``
# returns False) ``init_notebook()`` is a no-op, so this has zero cost
# for scripts.  Users who prefer to defer the injection can set
# ``MAIDR_USE_CDN=1`` so the bundle is never embedded.
try:
    init_notebook()
except Exception:  # pragma: no cover - never block import on notebook setup
    _logger.debug("init_notebook() raised during import", exc_info=True)


__all__ = [
    "bundled_css_path",
    "bundled_js_path",
    "close",
    "get_use_cdn",
    "init_notebook",
    "maidr_js_version",
    "read_bundled_js",
    "render",
    "save_html",
    "set_backend",
    "set_use_cdn",
    "show",
    "stacked",
]
