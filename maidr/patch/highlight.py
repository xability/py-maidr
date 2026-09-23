from __future__ import annotations

import uuid
from typing import Any, Callable

import wrapt
from matplotlib.backends.backend_svg import XMLWriter
from matplotlib.collections import (
    Collection,
    LineCollection,
    PathCollection,
    PolyQuadMesh,
    QuadMesh,
)
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from maidr.core.context_manager import HighlightContextManager


@wrapt.patch_function_wrapper(XMLWriter, "start")
def inject_maidr_attribute(wrapped, instance, args, kwargs):
    if HighlightContextManager.is_maidr_element(kwargs.get("id")):
        kwargs["maidr"] = HighlightContextManager.get_selector_id(kwargs.get("id"))
    return wrapped(*args, **kwargs)


def tag_elements(wrapped, instance, args, kwargs):
    # The draw patches below are class-wide, so outside a render this must
    # be a no-op: a plain `savefig` used to rewrite every artist's gid in the
    # process, including ones the user set to target from their own CSS or
    # JS, and on figures `FigureManager` never saw (#753). Nothing reads a
    # gid minted outside a render.
    if not HighlightContextManager.is_rendering():
        return wrapped(*args, **kwargs)

    # Inside a render an existing gid is kept: matplotlib writes it as the
    # `<g id>` that `XMLWriter.start` keys on, so a user's gid resolves to
    # its selector exactly as a minted one does. The mapping is set and
    # deleted around each artist's own draw, so two artists sharing a gid
    # do not collide in `elements`.
    gid = instance.get_gid()
    if gid is None:
        gid = "maidr-" + str(uuid.uuid4())
        instance.set_gid(gid)
    with HighlightContextManager.set_maidr_element(instance, str(gid)):
        return wrapped(*args, **kwargs)


def tag_path_collections(
    wrapped: Callable, instance: Collection, args: tuple, kwargs: dict
) -> Any:
    """Tag a ``PathCollection`` from ``Collection.draw``, and nothing else.

    A scatter's markers used to be tagged by wrapping ``PathCollection.draw``.
    That is the entry point only for a collection that keeps its class's
    ``draw``. ``sns.swarmplot`` does not: it packs the points at draw time,
    so ``plot_swarms`` binds a ``draw`` of its own onto each collection, which
    runs the packing and then calls ``super(PathCollection, points).draw``.
    Both routes skip the class attribute, so a swarm's markers were drawn
    untagged -- no ``maidr`` attribute on their group -- and the selector
    every one of its layers carries resolved to nothing: each point was
    announced and none was outlined.

    ``Collection.draw`` is where every one of those routes ends, and where
    the group is opened with the collection's gid, so the tag goes there.
    The type test keeps it to the collection this used to cover: a
    ``PolyCollection`` or ``LineCollection`` reaches this method too, and
    those are tagged, or deliberately left alone, by their own wrappers.

    Parameters
    ----------
    wrapped : Callable
        ``Collection.draw``, bound to ``instance``.
    instance : Collection
        The collection being drawn.
    args : tuple
        Positional arguments to the draw -- the renderer.
    kwargs : dict
        Keyword arguments to the draw.

    Returns
    -------
    Any
        Whatever the draw returns.
    """
    if not isinstance(instance, PathCollection):
        return wrapped(*args, **kwargs)
    return tag_elements(wrapped, instance, args, kwargs)


wrapt.wrap_function_wrapper(Patch, "draw", tag_elements)
wrapt.wrap_function_wrapper(QuadMesh, "draw", tag_elements)
wrapt.wrap_function_wrapper(Line2D, "draw", tag_elements)
wrapt.wrap_function_wrapper(LineCollection, "draw", tag_elements)
wrapt.wrap_function_wrapper(Collection, "draw", tag_path_collections)

# `Axes.pcolor` renders a PolyQuadMesh rather than the QuadMesh `pcolormesh`
# gives, so a pcolor heatmap read but carried no visual highlight.
#
# The wrapper goes on PolyQuadMesh and deliberately NOT on its PolyCollection
# base. PolyCollection also backs violin bodies and `fill_between`, and tagging
# it would hand every one of those a maidr gid and a highlight context they
# were never extracted for. PolyQuadMesh inherits `draw` rather than defining
# one, so wrapping it here installs a subclass-only override: the base class
# and its other subclasses keep the unwrapped method.
wrapt.wrap_function_wrapper(PolyQuadMesh, "draw", tag_elements)

# `Axes.stackplot` and `Axes.fill_between` render their bands as
# `FillBetweenPolyCollection`, which matplotlib 3.10 split out of
# `PolyCollection` -- so wrapping it is a subclass-only override in exactly the
# way `PolyQuadMesh` is, and leaves violin bodies and every other
# `PolyCollection` untouched.
#
# Guarded because the class is 3.10 and later, while this package supports
# 3.8. On an older matplotlib a band keeps the plain `PolyCollection` it always
# had, and an area layer degrades to no highlight rather than failing to
# import -- the announcement, which is the reading, is unaffected.
try:
    from matplotlib.collections import FillBetweenPolyCollection
except ImportError:  # pragma: no cover - matplotlib < 3.10
    pass
else:
    wrapt.wrap_function_wrapper(FillBetweenPolyCollection, "draw", tag_elements)
