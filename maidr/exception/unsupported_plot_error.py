"""The error a figure maidr never registered raises, and the words it uses."""

from __future__ import annotations

from matplotlib.figure import Figure

from maidr.core.enum import PlotType

#: The artist lists a drawn chart puts something in. A figure whose axes are
#: all empty of these has nothing on it, which is a different problem from
#: having something maidr cannot read -- and worth saying differently, since
#: "your chart type is unsupported" is misleading advice for someone who
#: called `maidr.render()` a moment too early.
#:
#: `texts` is included because `ax.text()` and `annotate()` land there, and
#: excluded from mattering elsewhere: an axes title or axis label does *not*,
#: which is what keeps a labelled-but-empty axes reading as empty.
_ARTIST_LISTS = (
    "lines",
    "collections",
    "patches",
    "images",
    "containers",
    "texts",
    "artists",
)


def supported_plot_types() -> str:
    """
    Every plot type maidr can read, as a user would name them.

    Derived from :class:`~maidr.core.enum.plot_type.PlotType` rather than
    hand-listed, because a hand-listed one drifted before -- it named "kde"
    and "violin", neither of which is a ``PlotType``, while omitting smooth and
    the violin variants.

    Returns
    -------
    str
        A comma-separated, alphabetically sorted list. ``display_name`` rather
        than ``value``: the values are wire identifiers, so someone who called
        ``ax.scatter()`` would otherwise be told about "point". The set folds
        the two violin layers, which share a display name, into one entry.
    """
    return ", ".join(sorted({plot_type.display_name for plot_type in PlotType}))


def has_drawn_artists(fig: Figure) -> bool:
    """
    Whether anything at all has been drawn onto ``fig``.

    Parameters
    ----------
    fig : Figure
        The figure to inspect.

    Returns
    -------
    bool
        True when any axes holds any artist. A figure with a title and axis
        labels but no marks counts as empty, which is the honest answer: the
        labels describe a chart that was never drawn.
    """
    return any(
        getattr(ax, name, None)
        for ax in getattr(fig, "axes", [])
        for name in _ARTIST_LISTS
    )


class UnsupportedPlotError(KeyError):
    """
    Raised when a figure carries nothing maidr knows how to read.

    Subclasses ``KeyError`` deliberately. The bare ``KeyError`` this replaces
    was the wrong *shape* -- it is the exception Python raises when you index a
    dict wrong, and surfacing it from a documented entry point told a user
    their own call did something illegal with a mapping when what actually
    happened is that their chart type is not supported yet (#443). But the
    matplotlib backend already catches ``KeyError`` around ``get_maidr`` to
    decide whether to fall back, and so may anyone else's code, so narrowing
    the type without keeping the base would break the working half of the
    behaviour while fixing the broken half.

    Parameters
    ----------
    fig : Figure
        The figure that has no MAIDR instance.

    Attributes
    ----------
    fig : Figure
        The figure, kept so a caller that decides to fall back can render it.
    is_empty : bool
        True when nothing was drawn at all, as opposed to something maidr
        cannot read. The two get different messages.
    """

    def __init__(self, fig: Figure) -> None:
        self.fig = fig
        self.is_empty = not has_drawn_artists(fig)
        super().__init__(self.message)

    def __str__(self) -> str:
        """
        The message, unquoted.

        ``KeyError.__str__`` special-cases a single argument and returns
        ``repr(args[0])``, because a key is usually a short value worth
        showing as a literal. Inheriting that would print the sentence
        wrapped in a stray quote::

            UnsupportedPlotError: 'This figure contains plot type(s) ...'

        Which is the shape this class exists to remove -- an uncaught one in a
        notebook traceback would look exactly like the dict-lookup failure the
        bare ``KeyError`` used to imply. The base class is kept for what
        catches it, not for how it reads.
        """
        return self.message

    @property
    def message(self) -> str:
        """The sentence a user should be shown, whether raised or warned."""
        if self.is_empty:
            return (
                "This figure has no plots on it yet, so there is nothing for "
                "maidr to describe. Draw a chart before calling maidr."
            )
        return (
            "This figure contains plot type(s) not yet supported by maidr. "
            f"Supported types: {supported_plot_types()}."
        )
