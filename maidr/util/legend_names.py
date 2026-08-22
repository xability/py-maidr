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

    A ``JointGrid`` puts the same one legend somewhere neither of those finds
    it: on ``ax_joint``, an *axes* legend, leaving the two marginals with none
    of their own and the figure with none either. Measured on a
    ``jointplot(hue=...)``, the joint panel's two point layers are named and
    each marginal's two density curves are not -- two identical
    announcements, which is the defect #558 named (#610).

    So a third place is read, and it is **narrower** than the figure fallback
    rather than wider: an axes an axis is *shared* with. A ``JointGrid``
    builds its marginals sharing one with the joint axes, because that is how
    a marginal lines up with the scatter beside it, and matplotlib records
    it. Two panels of a hand-built figure do not share by default, so the
    hazard measured above -- ``plt.subplots(1, 2)`` with one ``fig.legend()``
    -- is untouched and still answers ``None``. What is newly in scope is
    ``plt.subplots(1, 2, sharex=True)`` with a legend on one panel only,
    which is a figure whose panels were declared to be on one scale.

    Exactly one sharer, for the reason the figure fallback gives: two of them
    cannot say which names this axes' colours. And **only** where the figure
    carries none: two figure legends are ambiguous already, and a neighbour
    having one of its own does not resolve them -- it would name the axes off
    a third legend while two candidates for it stood unexamined.

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
    if legends:
        # Two of them decline here rather than falling through to a sharer:
        # a figure legend this axes could not be matched to does not stop
        # being ambiguous because a neighbour has one of its own.
        return legends[0] if len(legends) == 1 else None
    shared = [
        legend
        for sibling in _sharing_an_axis_with(ax)
        if (legend := sibling.get_legend()) is not None
    ]
    return shared[0] if len(shared) == 1 else None


def _sharing_an_axis_with(ax: Axes) -> list:
    """
    Every other axes this one shares an x or a y axis with.

    Asked of matplotlib's own groupers rather than inferred from position or
    from the figure's axes list, because sharing is the thing being tested and
    it is a fact the axes carries.

    Parameters
    ----------
    ax : Axes
        The axes drawn on.

    Returns
    -------
    list
        The sharers, ``ax`` itself excluded. Empty when it shares nothing --
        which is the default for a figure built with ``plt.subplots``.
    """
    sharers: list = []
    for grouper in (ax.get_shared_x_axes(), ax.get_shared_y_axes()):
        for sibling in grouper.get_siblings(ax):
            if sibling is not ax and not any(one is sibling for one in sharers):
                sharers.append(sibling)
    return sharers


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
                None if colour is None else named.get(key(colour)) for colour in colours
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

    Read **live**, at render, while a layer's group *names* are captured once
    as the plotting call is patched -- the same split
    :meth:`~maidr.core.plot.maidr_plot.MaidrPlot._legend_title` documents,
    kept deliberately rather than inherited. A caller who retitles the legend
    between two renders makes the two disagree, and the alternative is worse:
    freezing the title at registration would have a layer announce a title
    the figure no longer carries, which cannot be corrected by redrawing.

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


def names_for_panel(ax: Axes, colours: list, faceted: bool) -> list:
    """
    :func:`names_for`, plus the lone artist a faceted grid can still name.

    The single-artist floor asks whether an artist is alone **on its axes**:
    "a lone artist needs nothing to be told apart from". That is right about
    one chart and wrong about one panel of a grid, because the two questions
    come apart there -- the figure holds several distributions and the panel
    holds one of them. A reader walking the layers of
    ``displot(hue=..., col=...)`` heard two named ones and then one that would
    not say which group it was, on a chart whose legend names it plainly
    (#608).

    So the panel count decides it, not where the legend was hung. A figure
    legend is not the signal: seaborn's ``FacetGrid`` builds one for a single
    panel too, and reading that as licence to name would leave
    ``displot(one_level, hue=...)`` named and ``histplot(one_level, hue=...)``
    unnamed -- the same chart, two spellings, two answers, which is the
    asymmetry #522, #446 and #590 were each about. Both emit ``None`` today
    and both keep doing so.

    The panel count is a **proxy** for "the figure holds more than this
    panel does", and the two can come apart: a `col=` grid whose `hue=`
    happens to have a single level across the whole frame draws one artist
    per panel, all of them the same group, and every one is now named.
    Measured, `displot(x=, hue=, col=)` with one hue level gives
    `['only', 'only']` where it gave `[None, None]`.

    Kept rather than guarded against, because the name is **true**: the
    legend says which group these are, a sighted reader sees it, and the
    panels are told apart by their `col` level rather than by hue, so
    nothing is lost to the redundancy. The case the floor is right about is
    the other one -- a single-panel chart, where a name implies a companion
    layer that does not exist. Pinned in
    `tests/core/test_displot_distribution.py`.

    Only the floor moves. Every other decline is :func:`name_for`'s and
    unchanged: no legend, a colour no swatch claims, a colour two swatches
    claim.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    colours : list
        One rounded RGBA per artist, or ``None`` where it has no single one.
    faceted : bool
        Whether this panel is one of several. False leaves
        :func:`names_for` answering exactly as it did.

    Returns
    -------
    list
        One name per entry, or ``None``.
    """
    if faceted and len(colours) == 1:
        return [name_for(ax, colours[0])]
    return names_for(ax, colours)
