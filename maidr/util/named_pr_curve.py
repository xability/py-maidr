"""Whether a line layer is a precision-recall curve by its own axis titles.

Shared by the matplotlib and Plotly line paths, which emit the same data
shape for a line as maidr.js's ``pr_curve`` reads.
"""

from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey


def named_pr_curve(schema: dict) -> bool:
    """
    Whether a line schema is a precision-recall curve by its axis titles.

    Parameters
    ----------
    schema : dict
        A rendered line or step layer.

    Returns
    -------
    bool
        True when the x axis is titled ``Recall`` and the y axis
        ``Precision`` (any case, surrounding space ignored) and every point
        is a pair of numbers from 0 to 1.
    """
    axes = schema.get(MaidrKey.AXES) or {}

    def title(axis: MaidrKey) -> str:
        label = (axes.get(axis) or {}).get(MaidrKey.LABEL)
        return label.strip().lower() if isinstance(label, str) else ""

    if title(MaidrKey.X) != "recall" or title(MaidrKey.Y) != "precision":
        return False
    data = schema.get(MaidrKey.DATA)
    if not isinstance(data, list) or not data:
        return False
    for series in data:
        if not isinstance(series, list) or not series:
            return False
        for point in series:
            for key in (MaidrKey.X, MaidrKey.Y):
                value = point.get(key) if isinstance(point, dict) else None
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False
                if not 0 <= value <= 1:
                    return False
    return True
