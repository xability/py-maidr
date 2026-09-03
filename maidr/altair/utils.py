from __future__ import annotations

import sys
from typing import Any


def is_altair_chart(obj: Any) -> bool:
    """Check if an object is an Altair chart without requiring altair import."""
    # An instance of alt.Chart / alt.LayerChart cannot exist unless the
    # package is loaded: importing any altair submodule binds the parent
    # entry, and unpickling imports before it builds the object.  Importing
    # altair here would cost ~1.6 s of lark grammar compilation on every
    # process's first render of a matplotlib figure, so ask sys.modules
    # first -- which is what the docstring has promised all along.
    # ``.get() is None`` also short-circuits a blocked import, where the
    # entry is a None sentinel.
    if sys.modules.get("altair") is None:
        return False
    try:
        import altair as alt

        # Only single-view (Chart) and layered (LayerChart) specs are
        # supported by the Vega-Lite adapter. Facet, repeat, and concat
        # composite specs are intentionally rejected.
        return isinstance(obj, (alt.Chart, alt.LayerChart))
    except ImportError:
        return False
