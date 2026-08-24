"""
Generated titles for the panels of a seaborn grid.

A layer's title is the axes title (``MaidrPlot._schema``), and it is what the
core reads back when a reader arrows across a multi-panel figure's lobby:

    Subplot 2 of 9, bill_length_mm vs bill_depth_mm: This is a point plot.

seaborn's ``PairGrid`` and ``JointGrid`` set no titles on their cells -- they
label the grid's outer edge with axis labels instead -- so every panel of a
pairplot announced as ``Subplot N`` and nothing more, on a chart whose whole
purpose is that its panels are comparable (#660).

**The panel's identity is declared, not inferred.** ``PairGrid`` knows its
``x_vars``, ``y_vars`` and ``diag_vars``; ``JointGrid`` names its three axes
structurally. So a title is read off what the grid was *told*, never off
where a panel sits or what its neighbours look like -- which is the
distinction #516 drew when it removed the axis-label-from-position heuristic,
and the reason this is a lookup rather than a guess.

Two things follow from titles being generated:

* They are a **fallback**, never an override. A caller's own ``set_title``
  wins, because that is the panel's name and this is only a name for a panel
  that has none.
* They are generated the **same way every time**, so a reader who learns what
  ``"bill_length_mm vs bill_depth_mm"`` means on one panel knows it on all of
  them.
"""

from __future__ import annotations

import weakref

from matplotlib.axes import Axes

#: Generated title per panel axes.
#:
#: Weakly keyed so a closed figure's panels are collected with it, and holding
#: **plain strings** rather than the grid they were read from: a
#: ``WeakKeyDictionary`` whose values reach their own keys never collects
#: anything, which is the trap ``FigureManager`` records for its own map. A
#: resolved string reaches nothing.
_TITLES: weakref.WeakKeyDictionary[Axes, str] = weakref.WeakKeyDictionary()


def remember_panel_title(ax: Axes | None, title: str) -> None:
    """
    Record the title generated for one panel.

    Parameters
    ----------
    ax : Axes or None
        The panel. ``None`` is accepted and ignored -- a ``corner=True``
        ``PairGrid`` leaves the upper triangle's cells unfilled, and the
        caller should not have to say so twice.
    title : str
        The generated title. A blank one is recorded and read back as blank,
        which is the same answer as never recording it: a panel with nothing
        to say falls back to its position, which is what it did before and is
        honest about knowing no name.
    """
    if ax is None:
        return
    _TITLES[ax] = title


def panel_title(ax: Axes) -> str:
    """
    The generated title for a panel, or the empty string.

    Parameters
    ----------
    ax : Axes
        The axes a layer was drawn on.

    Returns
    -------
    str
        The title generated for this panel, or ``""`` when it is not a
        seaborn grid panel -- every ordinary chart, which is unaffected.
    """
    try:
        return _TITLES.get(ax, "")
    except TypeError:
        # An axes stand-in that cannot be weakly referenced (a test double,
        # a mock). Not having a generated title is the correct answer for it.
        return ""
