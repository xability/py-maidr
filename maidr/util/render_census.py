"""Noticing that a figure was drawn into while it was being rendered.

A render reads the schema from the artists and writes the SVG from them
afterwards. Anything that draws into the figure between those two points
lands in one and not the other: a chart that shows something it never
announces, or announces something it does not show. The per-figure lock
in :mod:`maidr.util.figure_lock` stops another *render* from doing that;
it cannot stop the application itself, on a figure it still holds (#530).

Reported rather than repaired. Re-reading the schema would race the same
way, and only the caller knows whether the figure was supposed to be
still -- so the warning names both remedies instead of guessing one.

**Importing this module mutates global interpreter state.** It registers
an always-filter for its own warning category, permanently, for the life
of the process -- see the note on that call below for why the alternative
is worse. Every other filter change in this package is scoped to a
``catch_warnings`` block; this one cannot be, because it has to be in
force at a moment none of this code controls.
"""

from __future__ import annotations

import warnings
from typing import Any

from matplotlib.figure import Figure


class MaidrRenderRaceWarning(UserWarning):
    """Raised when a figure changed while maidr was rendering it.

    Its own category rather than a bare ``UserWarning`` for the usual
    reason -- a consumer running under ``-W error`` can silence this
    advisory alone::

        warnings.filterwarnings("ignore", category=maidr.MaidrRenderRaceWarning)

    -- and for one specific to it, below.
    """


# Every occurrence is a *different* wrong chart, so every occurrence is
# worth saying. Python's default rule is once per (message, category,
# module, line), and this warning is raised from one fixed line, so the
# default would report the first collision in a process's lifetime and
# silently drop every later one -- in a long-running server, for every
# other session and every other figure, for the life of the process.
# That is the failure this module exists to prevent, arriving one
# occurrence later.
#
# Measured before this line existed: three collisions in one process
# produced two warnings, the missing one swallowed by that rule. (Two
# rather than one only because maidr's own plot patches mutate the filter
# state as a side effect, which invalidates the registry sometimes -- an
# accident, and not something to rely on.)
#
# Inserted at the front of the filter list, so a user's own
# ``filterwarnings`` call -- which also inserts at the front, later --
# still wins.
#
# Not sufficient on its own, which is why the message below also names
# the figure: anything that *rebuilds* the filter list drops this
# registration, and pytest does exactly that between tests. A process
# that has had its filters reset falls back to the default rule, and the
# per-figure detail is what keeps distinct figures from collapsing into
# one report there.
warnings.simplefilter("always", MaidrRenderRaceWarning)


def artist_census(figure: Figure) -> tuple[Any, ...]:
    """A cheap description of what is currently drawn on ``figure``.

    Compared either side of a render to notice a figure being drawn into
    while it is read. Counts and labels rather than the artists
    themselves: it has to be cheap enough to take twice per render, and it
    only has to answer "did this change", not what.

    **What it does not see.** Everything here is O(1) per axes, which buys
    the cheapness and costs the guarantee: a mutation that changes an
    *existing* artist in place -- ``patch.set_height``, ``line.set_ydata``,
    ``collection.set_offsets`` -- moves no count and no label, and passes
    unnoticed. So this is a detector for artists appearing, disappearing,
    or being relabelled, not for the data inside them, and silence from it
    is not a promise that a figure was still. Nor is this read itself
    atomic against the application: it walks ``figure.axes`` while another
    thread may be part-way through changing it, so the "before" it
    captures can be a figure mid-mutation rather than a clean one. Both
    are the same trade -- a detector that locked the application out would
    be a repair, and repairing this is what the module deliberately does
    not do. Catching a data change would
    mean hashing the data on every render, which is the cost this is
    shaped to avoid. Both mutations measured on #530 -- a title set and a
    bar added -- are the kind it sees.

    What it reads is what the schema reads, which is the point: the
    figure-level ``suptitle``/``supxlabel``/``supylabel`` feed the emitted
    ``title`` and ``axes`` just as the per-axes ones do, so leaving them
    out left a suptitle changed mid-render silently unreported -- the
    exact failure, one level up (review of #541).

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        The figure about to be, or just, rendered.

    Returns
    -------
    tuple
        Opaque. Only ever compared with another census of the same figure.
    """
    return (
        len(figure.axes),
        figure.get_suptitle(),
        figure.get_supxlabel(),
        figure.get_supylabel(),
        tuple(
            (
                len(ax.lines),
                len(ax.patches),
                len(ax.collections),
                len(ax.images),
                len(ax.texts),
                ax.get_legend() is not None,
                # Three titles, not one: `get_title()` reads the centre one
                # only, so a left- or right-placed title moved during a
                # render would otherwise be invisible here.
                ax.get_title(loc="center"),
                ax.get_title(loc="left"),
                ax.get_title(loc="right"),
                ax.get_xlabel(),
                ax.get_ylabel(),
            )
            for ax in figure.axes
        ),
    )


def warn_if_figure_changed(before: tuple[Any, ...], figure: Figure) -> None:
    """Warn when ``figure`` no longer matches the census taken ``before``.

    Parameters
    ----------
    before : tuple
        The census taken before the schema was read.
    figure : matplotlib.figure.Figure
        The figure whose SVG has just been written.

    Returns
    -------
    None
        Nothing: the warning is the whole output. A boolean "did it race"
        would be an API with no caller, and the one place that asks the
        question is the one place that raises the warning.
    """
    if artist_census(figure) == before:
        return

    # Named rather than described: the default warning rule keys on the
    # message text, so identifying the figure is what stops two different
    # figures racing in one process from being reported as one. `number`
    # is what a user sees in `plt.figure(3)` and in a traceback; a figure
    # made without pyplot has none, and its address is all there is.
    #
    # An address can be reused once a figure is collected, so two
    # unrelated pyplot-less figures could in principle be named the same
    # across a long process and the second's collision be read as a repeat
    # of the first's. Left as is: the always-filter below covers the
    # repeat case, and a counter would name the *report* rather than the
    # figure, which is not what a reader trying to find the chart needs.
    known_as = getattr(figure, "number", None)
    named = (
        f"figure {known_as}" if known_as is not None else f"figure at {id(figure):#x}"
    )

    # The same lock `maidr/patch/common.py` takes around its own
    # `catch_warnings` block. `warnings.filters` is process-global mutable
    # state, and a patched plot call on another thread saves, replaces and
    # restores the whole list -- so a warning raised while that is in
    # flight can be judged against filters that are not this process's,
    # including the ignore-everything one that call installs. Taking the
    # same lock is what makes "every collision is reported" true when a
    # render and a plot call overlap, rather than only when they do not.
    #
    # No deadlock against the render lock: a plot call holds this one and
    # never renders, so it never waits on `figure_lock` while a render
    # waits on this. Imported here rather than at module scope because
    # `maidr.patch` imports the renderer -- a module-level import would
    # reach `patch.common` while it is still executing its own imports,
    # before `_FILTER_LOCK` is assigned.
    #
    # `warnings.warn` calls `showwarning` synchronously, and that can be a
    # user's hook -- `logging.captureWarnings` installs one. So this holds
    # the filter lock for however long that hook takes. Accepted: the
    # alternative is releasing before the warning is delivered, which is
    # the window this lock exists to close.
    from maidr.patch.common import _FILTER_LOCK

    with _FILTER_LOCK:
        warnings.warn(
            f"maidr: {named} was drawn into while it was being rendered, "
            "so the chart's SVG and the data maidr announces for it may "
            "not match. Finish plotting before rendering, or render a "
            "figure no other thread is using.",
            MaidrRenderRaceWarning,
            # No stacklevel points at the caller here, and it is worth
            # saying so rather than implying otherwise: the depth from a
            # user's call varies by entry point -- `render`, `save_html`
            # and `show` reach this through different numbers of frames.
            # 4 names maidr's own render machinery, which is at least a
            # frame a reader recognises. What went wrong is in the
            # message, not the location.
            stacklevel=4,
        )


__all__ = ["MaidrRenderRaceWarning", "artist_census", "warn_if_figure_changed"]
