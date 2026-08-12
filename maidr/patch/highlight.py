from __future__ import annotations

import uuid

import wrapt
from matplotlib.backends.backend_svg import XMLWriter
from matplotlib.collections import (
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
    id = str(instance.get_gid())
    if not id.startswith("maidr-"):
        id = "maidr-" + str(uuid.uuid4())
        instance.set_gid(id)
    with HighlightContextManager.set_maidr_element(instance, id):
        return wrapped(*args, **kwargs)


wrapt.wrap_function_wrapper(Patch, "draw", tag_elements)
wrapt.wrap_function_wrapper(QuadMesh, "draw", tag_elements)
wrapt.wrap_function_wrapper(Line2D, "draw", tag_elements)
wrapt.wrap_function_wrapper(LineCollection, "draw", tag_elements)
wrapt.wrap_function_wrapper(PathCollection, "draw", tag_elements)

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
