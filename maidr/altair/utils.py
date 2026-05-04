from __future__ import annotations

from typing import Any


def is_altair_chart(obj: Any) -> bool:
    """Check if an object is an Altair chart without requiring altair import."""
    try:
        import altair as alt

        # Only single-view (Chart) and layered (LayerChart) specs are
        # supported by the Vega-Lite adapter. Facet, repeat, and concat
        # composite specs are intentionally rejected.
        return isinstance(obj, (alt.Chart, alt.LayerChart))
    except ImportError:
        return False


def get_mark_type(spec: dict) -> str:
    """Extract the mark type string from a Vega-Lite spec.

    The mark field can be a string (e.g., ``"bar"``) or a dict
    (e.g., ``{"type": "bar", "color": "red"}``).
    """
    mark = spec.get("mark", "")
    if isinstance(mark, dict):
        return mark.get("type", "")
    return str(mark)
