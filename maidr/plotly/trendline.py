"""Recognising the fitted trend lines ``plotly.express`` adds to a figure.

``px.scatter(..., trendline="ols")`` appends a second ``scatter`` trace
carrying the fit. Structurally it is indistinguishable from a line the user
drew themselves -- same ``type``, same ``mode``, no ``name``, same marker
colour -- so it was read as an ordinary line and a reader was told a model's
prediction was data (#343).

The one thing that separates it is ``hovertemplate``, which is a display
string rather than a structural attribute. That is a weaker signal than
``stackgroup`` on the area path, and it is the reason this module exists
separately: the rule is written down in one place, with what it will and will
not match stated, rather than being a condition buried in the extraction.

It is also the convention this package already uses for the same question.
``maidr/core/enum/smooth_keywords.py`` matches a matplotlib artist's ``label``
-- equally a display string, equally user-settable -- to find seaborn's
regression lines, and has since long before the plotly path existed. Reading
plotly's own generated template is the same trade in the same place.
"""

from __future__ import annotations

import re

#: Plotly's generated opening for a trendline's hover box.
#:
#: Every ``trendline`` mode ``px`` offers writes the fit's name in bold as the
#: first thing in the template -- measured across all five: ``<b>OLS
#: trendline</b>``, ``<b>LOWESS trendline</b>``, ``<b>Rolling mean
#: trendline</b>``, ``<b>Exponentially Weighted mean trendline</b>`` and
#: ``<b>Expanding mean trendline</b>``.
#:
#: Anchored at the start and required to be the whole of that first bold
#: segment, rather than a keyword scan anywhere in the string. A user who
#: writes "line of best fit" into a hovertemplate of their own is describing
#: their chart, not asking for one to be reclassified, and a loose match would
#: reclassify it. What this matches is the shape plotly emits and a person
#: writing prose does not.
_TRENDLINE_HOVERTEMPLATE = re.compile(r"^<b>[^<>]*\btrendline\b[^<>]*</b>", re.I)


def is_trendline_trace(trace: dict) -> bool:
    """
    Report whether a trace is a fitted trend line rather than drawn data.

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    bool
        True when the trace carries the hover template ``plotly.express``
        generates for a trendline.

    Notes
    -----
    Deliberately says nothing about ``mode`` or ``type``. Callers reach this
    only for traces they have already established are connected lines, and
    duplicating that test here would let the two drift apart -- the failure
    :func:`~maidr.plotly.step_shape.is_connected_line_trace` was written to
    end.
    """
    template = trace.get("hovertemplate")
    if not isinstance(template, str):
        return False
    return _TRENDLINE_HOVERTEMPLATE.search(template) is not None
