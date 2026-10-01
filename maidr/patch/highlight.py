from __future__ import annotations

import uuid
from typing import Any, Callable

import wrapt
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

# The class to patch is the one ``RendererSVG`` writes with. Matplotlib 3.11
# moved it onto a private ``_XMLWriter`` and kept ``XMLWriter`` only as a
# deprecated subclass that nothing instantiates, so patching ``XMLWriter`` there
# tagged no group: every chart was written without its ``maidr`` attributes, and
# every selector resolved to nothing.
try:
    from matplotlib.backends.backend_svg import _XMLWriter as XMLWriter
except ImportError:  # matplotlib < 3.11
    from matplotlib.backends.backend_svg import XMLWriter


#: Matplotlib's own ``XMLWriter.start``, which :func:`inject_maidr_attribute`
#: replaces and calls.
_xml_start = XMLWriter.start

#: What the per-render ``gid -> selector`` mapping reads as outside a render.
#: Only ever read, never written.
_NO_GIDS: dict = {}


def inject_maidr_attribute(
    self: XMLWriter, tag: str, attrib: dict = {}, **extra: Any
) -> int:
    """
    ``XMLWriter.start``, with ``maidr="<selector>"`` added to a tagged group.

    Matplotlib calls this once for every element of every SVG written in the
    process -- a 50,000-point scatter is 50,000 ``<use>`` elements -- so it
    replaces the method outright rather than going through a ``wrapt``
    wrapper. The wrapper bound a proxy and re-packed the arguments on each
    call, and made two classmethod calls each allocating a default dict: 0.7
    to 0.85 us per element, 50 to 100 ms of the ``savefig`` in a render of
    50k-100k marks, and the same tax on a plain ``savefig`` of any figure in a
    process that imported maidr.

    The rule is the one the wrapper applied. Only a keyword ``id`` can name a
    tagged group -- ``RendererSVG.open_group`` passes the artist's gid that
    way -- and it does while that artist's own draw has it mapped (see
    ``HighlightContextManager.set_maidr_element``). A call with no keywords
    has no ``id`` to look up, and the mapping is keyed by ``str(gid)``, so it
    never holds the ``None`` the wrapper looked up for one: such a call goes
    straight through. The attribute is added after the caller's own, as the
    wrapper added it.

    Parameters
    ----------
    self : XMLWriter
        The writer.
    tag : str
        The element's tag.
    attrib : dict, optional
        Its attributes, as matplotlib passes them positionally.
    **extra
        Its keyword attributes; ``id`` is the one looked up.

    Returns
    -------
    int
        What ``XMLWriter.start`` returns: the element's depth.
    """
    if extra:
        elements = HighlightContextManager._elements.get(_NO_GIDS)
        gid = extra.get("id")
        if gid in elements:
            extra["maidr"] = elements[gid]
    return _xml_start(self, tag, attrib, **extra)


inject_maidr_attribute.__wrapped__ = _xml_start  # type: ignore[attr-defined]
XMLWriter.start = inject_maidr_attribute  # type: ignore[method-assign]


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
