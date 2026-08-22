"""Name a chart's groups from the legend that names their colours."""

from __future__ import annotations

from matplotlib.axes import Axes

from maidr.core.plot.scatterplot import _handle_colour


def legend_of(ax: Axes | None):
    """
    The legend that names this axes' groups, wherever it was put.

    ``ax.get_legend()`` is where seaborn leaves one for a single chart, and it
    is what every caller here read. A ``PairGrid`` moves it: `add_legend()`
    builds one **figure-level** legend for the whole grid, and the panels then
    have none of their own.

    Only when the figure carries exactly one. Two figure legends cannot say
    which of them names this axes' colours, and a wrong name is worse than
    none -- the rule every decline in this module already follows.

    **The axes' own legend always wins**, and that is the mitigation rather
    than a preference. One figure legend is read as naming *every* axes, and
    nothing in the artists can say otherwise: several panels with independent
    hues draw the same default colour cycle, so a legend built for one of
    them matches all of them. Measured, two `kdeplot(hue=...)` panels drawn
    `legend=False` with one `fig.legend()` for the first come out with the
    first panel's names on both.

    That case needs a figure built by hand with every panel's own legend
    suppressed, which is not what any seaborn call does on its own -- a
    panel that keeps its legend is named by it and never consults the
    figure's. The trade is a wrong name in that shape against no name at all
    on every `pairplot`, whose whole grid does share one hue mapping. It is
    written down here rather than left to be discovered, and pinned in
    `tests/core/plot/test_pairplot_group_names.py`.

    Parameters
    ----------
    ax : Axes or None
        The axes drawn on.

    Returns
    -------
    Legend or None
        The legend to read swatches from, or ``None``.
    """
    if ax is None:
        return None
    own = ax.get_legend()
    if own is not None:
        return own
    figure = getattr(ax, "figure", None)
    legends = list(getattr(figure, "legends", ()) or ())
    return legends[0] if len(legends) == 1 else None


def names_for(ax: Axes, colours: list) -> list:
    """
    Match a list of drawn colours against the legend that names them.

    Two passes, and the second is not a convenience. Measured on seaborn
    0.13.2, ``histplot(kde=True, hue=...)`` draws its overlay curves **opaque**
    while the legend swatches carry the bars' translucency::

        line   (1.0, 0.498, 0.055, 1.0)
        swatch (1.0, 0.498, 0.055, 0.5)

    Identical hue, different alpha, so an RGBA comparison names nothing at all
    -- the chart would announce two named histograms and two anonymous curves
    over one axis. What identifies a group is the hue, so a second pass
    compares the three colour channels alone.

    That pass is guarded: it runs only where the drawn colours are already
    distinct without their alpha. Two artists separated *by* their opacity
    would otherwise both take whichever name matched, and a confident wrong
    name is worse than none.

    Every other reason to decline stands: no legend, an artist no swatch
    claims, a swatch that names two things, and a lone artist -- which needs
    nothing to be told apart from.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    colours : list
        One rounded RGBA per artist, or ``None`` where it has no single one.

    Returns
    -------
    list
        One name per entry, or ``None``.
    """
    if len(colours) < 2:
        return [None] * len(colours)

    legend = legend_of(ax)
    if legend is None:
        return [None] * len(colours)

    swatches = [
        (_handle_colour(handle), text.get_text())
        for handle, text in zip(legend.legend_handles, legend.get_texts())
    ]

    keys = [lambda colour: colour]
    hues = [colour[:3] for colour in colours if colour is not None]
    if len(set(hues)) == len(hues):
        keys.append(lambda colour: colour[:3])

    for key in keys:
        named = _match_swatches(colours, swatches, key)
        if named:
            return [
                None if colour is None else named.get(key(colour))
                for colour in colours
            ]
    return [None] * len(colours)


def name_for(ax: Axes, colour) -> str | None:
    """
    The legend's name for one drawn colour.

    :func:`names_for` declines a lone artist -- "a lone artist needs nothing
    to be told apart from" -- which is right where the artists of one layer
    are named against each other, and wrong where a *layer* is the artist.
    A ``catplot(kind="box", hue=...)`` panel draws one call per hue level, so
    a layer holds one colour and that colour is exactly what says which level
    it is; declining it leaves two layers a reader cannot tell apart (#595).

    Both passes :func:`names_for` makes are made here too, in the same order
    and for the same reason: the RGBA match first, and the three-channel one
    after it for an artist drawn at a different opacity from its swatch. The
    guard that pass needs there -- that the drawn colours are distinct without
    their alpha -- is unnecessary with one colour, and
    :func:`_match_swatches` still declines a colour two swatches claim.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    colour : tuple of float or None
        One rounded RGBA.

    Returns
    -------
    str or None
        The name, or ``None`` when no legend names that colour.
    """
    if colour is None:
        return None

    legend = legend_of(ax)
    if legend is None:
        return None

    swatches = [
        (_handle_colour(handle), text.get_text())
        for handle, text in zip(legend.legend_handles, legend.get_texts())
    ]
    for key in (lambda one: one, lambda one: one[:3]):
        named = _match_swatches([colour], swatches, key)
        if named:
            return named.get(key(colour))
    return None


def _match_swatches(colours: list, swatches: list, key) -> dict | None:
    """
    Map each swatch that a drawn artist shares a colour with to its name.

    Parameters
    ----------
    colours : list
        The drawn colours.
    swatches : list
        ``(colour, name)`` per legend entry, colour ``None`` where the handle
        names no single one.
    key : callable
        What counts as "the same colour" for this pass.

    Returns
    -------
    dict or None
        Key to name, or ``None`` when one colour is claimed by two names --
        a ``style=`` legend does that, and a swatch meaning two things cannot
        name the group an artist belongs to.
    """
    drawn = {key(colour) for colour in colours if colour is not None}
    named: dict = {}
    for colour, name in swatches:
        if colour is None:
            continue
        matched = key(colour)
        if matched not in drawn:
            continue
        if named.get(matched, name) != name:
            return None
        named[matched] = name
    return named


def title_of(ax: Axes) -> str:
    """
    The grouping variable's name, off the legend that named the groups.

    :meth:`maidr.core.plot.maidr_plot.MaidrPlot._legend_title` answers the
    same question from ``ax.get_legend()`` alone. That is the legend a
    single chart carries, and for the layers that predate :func:`legend_of`
    the two are the same object.

    They come apart wherever a group was named through the figure-level
    fallback: the panel has no legend of its own, so ``_legend_title``
    returns ``""`` and the ``z`` label is dropped, while the *names* were
    read off the figure's legend and are on the layers. Measured -- a rug
    drawn ``legend=False`` beside one ``fig.legend(title="g")`` naming the
    same palette split into ``a`` and ``b`` with no ``z`` at all, so the
    chart said which side of a grouping each layer was without ever saying
    what the grouping was.

    Reading the title off whichever legend :func:`legend_of` chose keeps the
    two halves of one decision on one source.

    Parameters
    ----------
    ax : Axes
        The axes drawn on.

    Returns
    -------
    str
        The title, or an empty string when there is no legend to read or no
        title on it.
    """
    legend = legend_of(ax)
    if legend is None:
        return ""
    title = legend.get_title()
    if title is None:
        return ""
    return title.get_text().strip()
