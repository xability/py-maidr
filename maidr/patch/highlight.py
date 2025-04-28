from __future__ import annotations

import uuid

import wrapt
from matplotlib.backends.backend_svg import XMLWriter
from matplotlib.collections import PathCollection, QuadMesh
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
wrapt.wrap_function_wrapper(PathCollection, "draw", tag_elements)
