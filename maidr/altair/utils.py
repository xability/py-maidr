from __future__ import annotations

from typing import Any

import pandas as pd


def is_altair_chart(obj: Any) -> bool:
    """Check if an object is an Altair chart without requiring altair import."""
    try:
        import altair as alt

        return isinstance(
            obj,
            (
                alt.Chart,
                alt.LayerChart,
                alt.HConcatChart,
                alt.VConcatChart,
                alt.FacetChart,
                alt.ConcatChart,
                alt.RepeatChart,
            ),
        )
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


def resolve_data(spec: dict) -> pd.DataFrame:
    """Extract inline data from a Vega-Lite spec as a DataFrame.

    Handles both ``data.values`` and ``datasets`` formats.
    """
    data_section = spec.get("data", {})

    # Direct inline values
    if "values" in data_section:
        return pd.DataFrame(data_section["values"])

    # Named dataset reference
    if "name" in data_section:
        dataset_name = data_section["name"]
        datasets = spec.get("datasets", {})
        if dataset_name in datasets:
            return pd.DataFrame(datasets[dataset_name])

    # URL data source — not supported for now
    if "url" in data_section:
        raise ValueError(
            "Altair charts with URL data sources are not yet supported by maidr. "
            "Please use inline data (pass a DataFrame directly to alt.Chart)."
        )

    return pd.DataFrame()


def get_encoding_field(encoding: dict, channel: str) -> str | None:
    """Get the field name from an encoding channel."""
    ch = encoding.get(channel, {})
    return ch.get("field")


def get_encoding_type(encoding: dict, channel: str) -> str | None:
    """Get the type from an encoding channel."""
    ch = encoding.get(channel, {})
    return ch.get("type")


def get_encoding_aggregate(encoding: dict, channel: str) -> str | None:
    """Get the aggregate function from an encoding channel."""
    ch = encoding.get(channel, {})
    return ch.get("aggregate")


def get_encoding_bin(encoding: dict, channel: str) -> dict | bool | None:
    """Get the bin specification from an encoding channel."""
    ch = encoding.get(channel, {})
    return ch.get("bin")


def get_encoding_stack(encoding: dict, channel: str) -> str | bool | None:
    """Get the stack specification from an encoding channel."""
    ch = encoding.get(channel, {})
    return ch.get("stack")


def get_axis_title(encoding: dict, channel: str) -> str:
    """Get the axis title from an encoding channel, falling back to field name."""
    ch = encoding.get(channel, {})
    # Check for explicit title
    if "title" in ch:
        return ch["title"]
    # Check axis.title
    axis = ch.get("axis", {})
    if isinstance(axis, dict) and "title" in axis:
        return axis["title"]
    # Fall back to field name
    return ch.get("field", channel.upper())
