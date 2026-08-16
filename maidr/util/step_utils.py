"""Helpers for recognising matplotlib step lines and their step convention.

``matplotlib.axes.Axes.step`` is not a distinct renderer: it sets
``kwargs["drawstyle"] = "steps-" + where`` and delegates to ``Axes.plot``,
returning ordinary ``Line2D`` artists. The only durable record that a step
chart was requested is therefore the ``drawstyle`` of the resulting artists,
which is what these helpers read.

Reading the artists rather than the call kwargs means ``ax.step()``,
``plt.step()``, ``ax.plot(drawstyle=...)`` and ``sns.lineplot(drawstyle=...)``
are all recognised by one rule, and matplotlib's ``ds`` kwarg alias needs no
special handling because it has already been normalised onto the ``Line2D``
by the time these functions run.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from matplotlib.lines import Line2D

#: matplotlib ``drawstyle`` -> MAIDR ``stepDirection``.
#:
#: The MAIDR directions follow the ggplot2 naming: ``hv`` holds the value then
#: jumps, ``vh`` jumps then holds, ``mid`` jumps midway between samples. Bare
#: ``"steps"`` is matplotlib's legacy alias for ``"steps-pre"``.
STEP_DRAWSTYLE_TO_DIRECTION: Dict[str, str] = {
    "steps-post": "hv",
    "steps-pre": "vh",
    "steps": "vh",
    "steps-mid": "mid",
}


def is_step_drawstyle(drawstyle: object) -> bool:
    """
    Report whether a matplotlib ``drawstyle`` denotes a step line.

    Parameters
    ----------
    drawstyle : object
        The value returned by ``Line2D.get_drawstyle()``.

    Returns
    -------
    bool
        ``True`` for ``"steps"`` and every ``"steps-*"`` variant.
    """
    return str(drawstyle).startswith("steps")


def data_bearing_lines(lines: Iterable[Line2D]) -> List[Line2D]:
    """
    Return the given ``Line2D`` artists that actually carry data.

    Mirrors the empty-data filter used by
    :meth:`maidr.core.plot.lineplot.MultiLinePlot._extract_line_data` so that
    classification and extraction always agree on which lines count.

    Parameters
    ----------
    lines : iterable of Line2D
        The lines a layer owns. Never the axes: see :func:`is_step_layer`.

    Returns
    -------
    list of Line2D
        Possibly empty list of non-empty lines.
    """
    try:
        candidates = list(lines)
    except TypeError:
        # Defensive: the patch layer may hand us a non-iterable (e.g. a Mock).
        return []

    data_lines = []
    for line in candidates:
        try:
            xydata = line.get_xydata()
        except (AttributeError, TypeError):
            continue
        if xydata is None or not getattr(xydata, "size", 0):
            continue
        data_lines.append(line)
    return data_lines


def is_step_layer(lines: Iterable[Line2D]) -> bool:
    """
    Report whether a layer's own lines should be classified as a step plot.

    The rule for a mixed layer: it is a step plot only when *every*
    data-bearing line in it is a step line. One ordinary line mixed in means
    the layer as a whole is not piecewise-constant, and MAIDR emits a single
    layer per axes, so the conservative ``line`` classification wins.

    Asked of the layer's lines rather than the axes'. Sweeping ``ax.get_lines()``
    was the same defect #440 closed one level up: a box plot, violin or boxen
    renders its whiskers, caps and medians as ordinary data-space ``Line2D``
    objects, so a step chart sharing an axes with one saw those in the mix and
    concluded the axes was not piecewise-constant. Measured, drawing the
    companion first so it is on the axes when classification runs::

        sns.boxplot(...); ax.step(...)     -> type "line"    (should be "step")
        sns.violinplot(...); ax.step(...)  -> type "line"

    Which is not a cosmetic mislabel: ``line`` means :class:`MultiLinePlot`
    rather than :class:`~maidr.core.plot.stepplot.StepPlot`, so the ordinal
    level names go too -- a hypnogram announces ``3`` where it should say
    ``REM``.

    The predicate is evaluated once, when the layer is registered — that is,
    on the first plotting call for the axes, which is the same moment the
    existing ``_maidr_plot_created`` guard fires. Lines drawn onto the axes
    *after* that call do not re-open the decision, exactly as they do not
    create a second layer today. A step layer that later acquires an ordinary
    line keeps announcing its level names (the accessibility payload that
    matters most) but stops claiming a ``stepDirection``, because
    :func:`resolve_step_direction` re-reads the artists at render time and
    finds them inconsistent.

    Parameters
    ----------
    lines : iterable of Line2D
        The lines the layer owns.

    Returns
    -------
    bool
        ``True`` when the layer holds at least one line and all of them are
        step lines.
    """
    data_lines = data_bearing_lines(lines)
    if not data_lines:
        return False
    return all(is_step_drawstyle(line.get_drawstyle()) for line in data_lines)


def resolve_step_direction(lines: Iterable[Line2D]) -> Optional[str]:
    """
    Resolve the single ``stepDirection`` a layer authors, if there is one.

    Returns ``None`` — meaning "omit the field" — whenever the layer does not
    unambiguously author one direction: no lines, a non-step drawstyle, an
    unrecognised ``steps-*`` variant, or several series disagreeing. MAIDR's
    description only names a direction when the data actually reported one,
    so guessing here would put a claim in the audio that nothing supports.

    Asked of the layer's lines for the reason :func:`is_step_layer` gives, and
    the failure here was the quieter of the two: read at *render* time, so a
    companion chart drawn after the step line was enough. Measured::

        ax.step(...); sns.boxplot(...)   -> stepDirection absent

    The step line itself was unambiguous. What disagreed with it was box
    geometry, and the reader simply never heard which side of each sample the
    value is held on.

    Parameters
    ----------
    lines : iterable of Line2D
        The lines the layer owns.

    Returns
    -------
    str or None
        One of ``"hv"``, ``"vh"``, ``"mid"``, or ``None``.
    """
    data_lines = data_bearing_lines(lines)
    if not data_lines:
        return None

    directions = {
        STEP_DRAWSTYLE_TO_DIRECTION.get(str(line.get_drawstyle())) for line in lines
    }
    if len(directions) != 1:
        return None

    # A lone ``None`` here means every line shares an unrecognised drawstyle.
    return directions.pop()
