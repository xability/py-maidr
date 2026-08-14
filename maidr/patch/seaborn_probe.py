"""Keep seaborn's colour probe from registering as a chart.

``seaborn.utils._default_color`` resolves a default colour by *drawing* a
throwaway artist, reading its face colour, and removing it again. Every
branch ends in ``scout.remove()``::

    elif method.__name__ == "fill_between":
        kws = normalize_kwargs(kws, mpl.collections.PolyCollection)
        scout = method([], [], **kws)
        facecolor = scout.get_facecolor()
        color = to_rgb(facecolor[0])
        scout.remove()

It is a probe, never a chart. But it draws through ``Axes.fill_between``,
``Axes.plot``, ``Axes.scatter`` and ``Axes.bar`` -- all of which MAIDR
patches -- and it runs *before* any seaborn-level patch has set a recursion
context, so nothing suppressed it (#373).
"""

from __future__ import annotations

import sys
import warnings
from typing import Any

import wrapt

from maidr.core.context_manager import ContextManager


def _suppress_registration(wrapped, _, args, kwargs) -> Any:
    """
    Resolve a default colour without registering the artist it drew.

    A layer from the probe describes a fill of two empty arrays. It has no
    elements on the chart, so it announces a region that is not drawn and
    highlights nothing -- the same shape of defect as #369, where a colorbar
    registered as a second heatmap.

    Suppressing the whole function rather than teaching each patch to decline
    an empty call is the honest scope. ``fill_between`` could be taught to
    refuse ``([], [])``, and that would fix the one branch and leave the
    hazard: the probe also drives ``plot``, ``scatter`` and ``bar``, and the
    next patch added to any of them reintroduces it somewhere new. The probe
    is the thing that should be quiet, not each artist it happens to draw.

    Parameters
    ----------
    wrapped : Callable
        The original ``seaborn.utils._default_color``.
    _ : Any
        Unused -- the function is module-level, so wrapt binds nothing.
    args : tuple
        Positional arguments seaborn passed.
    kwargs : dict
        Keyword arguments seaborn passed.

    Returns
    -------
    Any
        The resolved colour, unchanged.
    """
    with ContextManager.set_internal_context():
        return wrapped(*args, **kwargs)


def _patch_default_color() -> None:
    """
    Wrap the probe at every seaborn module that holds a reference to it.

    ``_default_color`` is not a re-export like the plotting functions
    ``wrap_seaborn`` handles -- it is a private helper pulled into three
    modules by name::

        from .utils import _default_color   # categorical, distributions,
                                            # relational

    so its ``__module__`` names one binding out of four and the call sites
    take the other three. Sweeping the loaded ``seaborn`` modules covers
    every binding without a hard-coded table, and stays correct if seaborn
    switches to a qualified ``utils._default_color(...)`` call, since
    ``seaborn.utils`` is in the sweep too.

    The identity check is what makes the sweep safe: a name that no longer
    resolves to the same object is left alone rather than wrapped by guess.
    Importing ``seaborn.utils`` runs ``seaborn/__init__.py``, which imports
    every module that binds the probe, so they are all in ``sys.modules`` by
    the time the sweep runs.
    """
    import seaborn.utils

    original = getattr(seaborn.utils, "_default_color", None)
    if original is None:  # pragma: no cover - seaborn renamed the helper
        warnings.warn(
            "maidr: seaborn.utils._default_color is gone, so the colour probe "
            "is no longer suppressed. If seaborn still resolves default "
            "colours by drawing a throwaway artist, that artist will be "
            "registered as a chart of its own.",
            stacklevel=2,
        )
        return

    for module in list(sys.modules.values()):
        name = getattr(module, "__name__", "")
        if name != "seaborn" and not name.startswith("seaborn."):
            continue
        if getattr(module, "_default_color", None) is original:
            wrapt.wrap_function_wrapper(
                module, "_default_color", _suppress_registration
            )


_patch_default_color()
