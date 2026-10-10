"""The chart's starting hover mode, carried as the schema's ``hoverMode``.

maidr.js reads a top-level ``hoverMode`` as the starting value of the
reader's Hover Mode setting (xability/maidr#1382):

* ``"pointermove"`` -- the pointer moves the reader's position and
  highlights as it passes over the chart (maidr.js's default);
* ``"click"`` -- the position moves only on a click;
* ``"off"`` -- the pointer is ignored, and the chart is keyboard only.

A reader who has changed the setting keeps their own choice. A maidr.js
older than the field ignores it, so emitting it is safe; one that does not
know a value ignores that value with a console warning, which is why this
module refuses an unknown one here, where the author can see it, rather than
let it reach the page.

Every renderer that builds a schema in Python -- matplotlib and seaborn,
plotnine, Plotly and Bokeh -- puts the field on through
:func:`with_hover_mode`, so it is decided in one place. The Altair path
builds no schema here (the upstream Vega-Lite adapter does, in the browser,
and takes no option for this), so it warns instead; see
:func:`maidr.api._warn_altair_ignores_hover_mode`.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

from maidr.core.enum.maidr_key import MaidrKey

#: What ``hover_mode`` accepts; ``None`` leaves the field out.
HoverMode = Literal["pointermove", "click", "off"]

#: The values maidr.js understands, in the order the docs give them.
HOVER_MODES: tuple[str, ...] = get_args(HoverMode)


def check_hover_mode(value: Any) -> HoverMode | None:
    """Return ``value`` if it is a hover mode or ``None``, else raise.

    Parameters
    ----------
    value : Any
        The caller's ``hover_mode``.

    Returns
    -------
    {"pointermove", "click", "off"} or None
        ``value`` unchanged.

    Raises
    ------
    ValueError
        If ``value`` is anything else, naming the values that are accepted.
    """
    if value is None or (isinstance(value, str) and value in HOVER_MODES):
        return value
    allowed = ", ".join(repr(mode) for mode in HOVER_MODES)
    raise ValueError(f"hover_mode must be one of {allowed} or None, got {value!r}")


def with_hover_mode(schema: dict, hover_mode: HoverMode | None) -> dict:
    """Put ``hover_mode`` on a top-level MAIDR schema, when one is given.

    Parameters
    ----------
    schema : dict
        The top-level schema (the object carrying ``id`` and ``subplots``).
        Changed in place.
    hover_mode : {"pointermove", "click", "off"} or None
        The chart's starting hover mode. ``None`` leaves the schema without
        ``hoverMode``, so maidr.js uses its own default.

    Returns
    -------
    dict
        ``schema``, for chaining.

    Raises
    ------
    ValueError
        If ``hover_mode`` is not one of the accepted values.
    """
    hover_mode = check_hover_mode(hover_mode)
    if hover_mode is not None:
        schema[MaidrKey.HOVER_MODE.value] = hover_mode
    return schema
