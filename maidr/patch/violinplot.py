"""Monkey-patches for ``seaborn.violinplot`` and ``Axes.violinplot``.

Registers two MAIDR layers per violin plot:

* **VIOLIN_BOX** — box-plot summary statistics computed from the raw data,
  with CSS selectors pointing at the existing inner-box artists.
* **VIOLIN_KDE** — the KDE density curves (PolyCollection outlines).

The seaborn half registers at ``_CategoricalPlotter.plot_violins`` rather than
at ``seaborn.violinplot``, so that what is read is what seaborn *resolved*
rather than how the caller happened to spell it; see
:func:`sns_categorical_violins`.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Collection

import numpy as np
import pandas as pd
import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.violinplot import ViolinDataExtractor
from maidr.patch.common import (
    _argument,
    _draw_quietly,
    plotter_axes,
    plotter_panels,
    resolve_orientation,
    wrap_seaborn,
)
from maidr.util.mixin.extractor_mixin import LevelExtractorMixin


# ======================================================================
# Seaborn
# ======================================================================
def patch_violinplot(
    wrapped: Callable, instance: Any, args: tuple, kwargs: dict
) -> Any:
    """
    Draw ``seaborn.violinplot`` quietly and leave the reading to the plotter.

    Registration used to happen here and no longer does: this call cannot see
    what seaborn decided, only what it was handed, and reading the second as
    though it were the first is what #449 and the violin half of #448 were.
    :func:`sns_categorical_violins` wraps the method that draws, which both
    ``violinplot`` and ``catplot`` reach, and registers there instead.

    What remains is the part that still belongs at this level.
    ``_draw_quietly`` covers the whole seaborn call rather than only its
    drawing step, so a deprecation warning raised while ``violinplot``
    resolves its arguments -- ``scale``, ``bw`` and ``scale_hue`` are all
    still shimmed -- does not reach a screen-reader user who did not write
    the call and cannot act on it. And ``wrap_seaborn`` keeps both bindings
    of the name wrapped, which ``tests/core/test_seaborn_patch_reach.py``
    asserts directly.

    Nothing here sets the internal context, and that is deliberate: the
    context is what makes a patch decline, so setting it here would silence
    the plotter patch below. The two things it used to suppress are covered
    elsewhere -- ``maidr/patch/seaborn_probe.py`` handles the colour probe
    seaborn runs before it draws (#373), and everything drawn *inside*
    ``plot_violins`` is inside the context that patch sets.

    Parameters
    ----------
    wrapped : Callable
        ``seaborn.violinplot``.
    instance : Any
        Unused; seaborn's plotting functions are module level.
    args, kwargs
        The caller's arguments, passed through untouched.

    Returns
    -------
    Any
        Whatever seaborn returned.
    """
    return _draw_quietly(wrapped, args, kwargs)


# Patch seaborn function.
wrap_seaborn("violinplot", patch_violinplot)


def _levels(declared: Any, column: pd.Series) -> list:
    """
    The categories of one variable, in the order seaborn drew them.

    ``var_levels`` is seaborn's own record of that order, and it is the one to
    prefer: a caller's ``order=``, a pandas ``Categorical``'s declared
    categories and plain first-appearance order all arrive here already
    resolved. It is asked per figure rather than per panel, so a facet that
    holds only some of the categories still names them in the figure's order.

    Falls back to the values present when seaborn recorded no levels for the
    variable, which is the case for a numeric axis under ``native_scale=True``.

    Parameters
    ----------
    declared : Any
        ``plotter.var_levels[...]`` for this variable, or None.
    column : pandas.Series
        The column those levels describe, used only as the fallback.

    Returns
    -------
    list
        The category values, in draw order.
    """
    if declared is not None and len(declared):
        return list(declared)
    return list(pd.unique(column.dropna()))


def _panel_groups(
    panel: pd.DataFrame, plotter: Any
) -> tuple[list[str], list[np.ndarray]]:
    """
    The named groups one panel summarises, read from seaborn's own frame.

    ``plot_data`` holds the values in *resolved* roles: seaborn has already
    decided which variable is the category and which is the measurement, and
    ``plotter.orient`` says which way round. That is the whole point of
    reading here. Deciding it from the caller's keywords instead is what
    turned an inferred-horizontal violin into a crash -- ``orient`` is None
    when seaborn worked the orientation out for itself, so the category names
    were read as the measurements and ``np.isnan`` was handed an array of
    strings (#449).

    Group labels follow the axes-level convention exactly, including the
    ``"Violin"`` placeholder for a single ungrouped distribution and the
    ``f"{category}_{hue}"`` join -- collapsed to the category alone when the
    hue *is* the category, which is seaborn's own idiom for colouring a plain
    violin and would otherwise announce "a_a".

    An empty combination is skipped rather than announced as a group with no
    data in it, which matters on a facet grid: a panel typically holds a
    subset of the figure's categories.

    Parameters
    ----------
    panel : pandas.DataFrame
        One panel's rows of ``plot_data``.
    plotter : Any
        The ``_CategoricalPlotter``, for its orientation and levels.

    Returns
    -------
    tuple[list[str], list[numpy.ndarray]]
        ``(groups, values)``, both empty when the panel holds no measurement.
    """
    orient = getattr(plotter, "orient", "x")
    category_column = "y" if orient == "y" else "x"
    value_column = "x" if orient == "y" else "y"

    columns = set(panel.columns)
    if value_column not in columns:
        return [], []

    levels = getattr(plotter, "var_levels", None) or {}
    variables = getattr(plotter, "variables", None) or {}
    categories = (
        _levels(levels.get(category_column), panel[category_column])
        if category_column in columns
        else []
    )

    # `sns.violinplot(x=values)` has no categorical variable at all, and
    # seaborn does not leave the column out: `scale_categorical` invents the
    # axis and fills it with the empty string, so the frame looks grouped and
    # the group is called "". Recognised by both halves together -- an unnamed
    # variable *and* nothing but the placeholder in it -- because an unnamed
    # variable on its own is just a bare list of real categories,
    # `sns.violinplot(x=["a", "b", ...], y=[...])`, which does have groups to
    # name. "Violin" is the placeholder the axes-level path has always used.
    invented = variables.get(category_column) is None and categories == [""]
    if category_column not in columns or invented:
        return ["Violin"], [panel[value_column].dropna().to_numpy()]

    if "hue" not in columns:
        pairs: list[tuple[Any, Any]] = [(name, None) for name in categories]
        hue_is_category = False
    else:
        # Same *named* column, which is what "the hue is the category" means.
        # `variables` records the column name that filled each role and is
        # None for a bare array, so comparing the two directly makes two
        # unnamed variables look like one:
        #
        #     sns.violinplot(x=["a", ...], y=[...], hue=["p", ...])
        #       groups: ['a', 'a', 'b', 'b']
        #
        # Four violins, two pairs sharing a name and nothing telling them
        # apart -- which is the defect this file is about, reintroduced one
        # spelling along. An unnamed variable is not the same variable as
        # another unnamed one, so `None` on either side answers False.
        hue_variable = variables.get("hue")
        hue_is_category = (
            hue_variable is not None
            and hue_variable == variables.get(category_column)
        )
        # Hoisted rather than evaluated inside the comprehension, where it
        # would be recomputed -- `pd.unique` and all -- once per category.
        hue_levels = _levels(levels.get("hue"), panel["hue"])
        pairs = [(name, hue) for name in categories for hue in hue_levels]

    groups: list[str] = []
    values: list[np.ndarray] = []
    for name, hue in pairs:
        rows = panel[category_column] == name
        if hue is not None:
            rows &= panel["hue"] == hue
        measured = panel.loc[rows, value_column].dropna()
        if measured.empty:
            continue
        groups.append(
            str(name) if hue is None or hue_is_category else f"{name}_{hue}"
        )
        values.append(measured.to_numpy())
    return groups, values


def sns_categorical_violins(
    wrapped: Callable, instance: Any, args: tuple, kwargs: dict
) -> Any:
    """
    Register every violin panel seaborn draws, whichever interface drew it.

    One registrar for both, which is the point. ``seaborn.violinplot`` and
    ``sns.catplot(kind="violin")`` share no code above this method --
    ``catplot`` drives ``_CategoricalPlotter`` directly and imports nothing --
    so a patch on the function reached one of them and a patch here reaches
    both. Three separate readings were wrong for that reason, and all three
    are the same mistake: the old patch worked out what had been drawn by
    re-reading the caller's keywords, rather than asking seaborn what it had
    decided.

    * ``catplot(kind="violin")`` reached no patch at all, so its panel was
      seen only by the matplotlib-level patches and arrived as **``line``** --
      a distribution announced as a two-point series (#448);
    * an inferred-horizontal violin -- ``sns.violinplot(y="g", x="v")``, the
      spelling seaborn documents -- **raised** ``TypeError`` out of
      ``maidr.render()`` and produced no HTML for the figure, because
      ``orient`` is None in the kwargs when seaborn inferred it, so the
      category names were read as the measurements (#449);
    * a frame passed *positionally* -- ``sns.violinplot(df, x=..., y=...)`` --
      silently lost its **VIOLIN_BOX** layer, because the extractor looked for
      ``data`` in the keywords only. The chart loaded, the density curve read
      correctly, and the five summary statistics a violin exists to carry were
      not there, with nothing saying so (#449).

    ``plotter.orient``, ``plotter.plot_data`` and ``plotter.var_levels``
    answer all three, because seaborn has resolved every one of those
    questions before it draws a single artist.

    The inner-box artists are still matched by a before/after snapshot, now
    taken **per panel**. That is not only for facets: the old snapshot was
    empty whenever the caller omitted ``ax=``, so a violin drawn onto axes
    that already held lines would have taken those lines for its own inner
    box.

    Parameters
    ----------
    wrapped : Callable
        ``_CategoricalPlotter.plot_violins``.
    instance : Any
        The plotter the method is bound to.
    args, kwargs
        The method's own arguments, passed through untouched.

    Returns
    -------
    Any
        Whatever seaborn returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Which lines each panel held before this call, so the inner-box
    # classification below sees only the ones seaborn is about to add.
    # By identity: every line counted stays referenced by `ax.lines` for the
    # whole window, so none can be freed and have another take its address.
    panels = plotter_axes(instance)
    before = {id(ax): set(ax.lines) for ax in panels}
    # The same snapshot for the density polygons; see `_register_kde_layer`.
    before_polys = {id(ax): set(ax.collections) for ax in panels}

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    orientation = "horz" if getattr(instance, "orient", "x") == "y" else "vert"

    # `inner` is read through `_argument` rather than from `kwargs` alone
    # because it is declared positional-or-keyword on the method, unlike the
    # keyword-only arguments of seaborn's public functions. `None` is a value
    # a caller can pass, and means seaborn drew no inner box -- so there is
    # nothing for the box layer's selectors to point at.
    inner = _argument("inner", wrapped, args, kwargs)

    for panel_ax, panel in plotter_panels(instance):
        groups, values = _panel_groups(panel, instance)

        if inner in ("box", "boxplot"):
            added = [
                line
                for line in panel_ax.lines
                if line not in before.get(id(panel_ax), set())
            ]
            _register_box_layer(
                panel_ax,
                groups,
                values,
                orientation,
                use_full_range=False,
                violin_options=None,
                sns_box_lines=_classify_sns_box_lines(added, orientation),
            )

        _register_kde_layer(
            panel_ax,
            orientation,
            [
                collection
                for collection in panel_ax.collections
                if collection not in before_polys.get(id(panel_ax), set())
            ],
        )

    return drawn


# And the plotter method beneath `seaborn.violinplot`, which is the only thing
# `catplot` drives. Wrapped by module path rather than by importing the private
# class, matching how `maidr/patch/boxplot.py` reaches `_CategoricalPlotter`.
wrapt.wrap_function_wrapper(
    "seaborn.categorical",
    "_CategoricalPlotter.plot_violins",
    sns_categorical_violins,
)


# ======================================================================
# Matplotlib
# ======================================================================
@wrapt.patch_function_wrapper(Axes, "violinplot")
def mpl_violinplot(wrapped: Callable, instance: Axes, args: tuple, kwargs: dict) -> Any:
    """Intercept ``Axes.violinplot`` and register box + KDE layers."""
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)

    plot_ax: Axes = instance
    orientation = resolve_orientation(wrapped, args, kwargs)

    violin_options = {
        "showMean": bool(kwargs.get("showmeans", False)),
        "showMedian": bool(kwargs.get("showmedians", False)),
        "showExtrema": bool(kwargs.get("showextrema", True)),
    }

    # Collect LineCollection artists from the return dict.
    mpl_artists: dict = {}
    for key in ("cmins", "cmaxes", "cbars", "cmedians", "cmeans"):
        if key in plot:
            mpl_artists[key] = plot[key]

    # Matplotlib takes its data positionally and has no plotter to ask, so
    # this side still reads the call's own arguments; `ViolinDataExtractor`
    # is only reached from here now.
    groups, values = ViolinDataExtractor.extract(args, kwargs)

    _register_box_layer(
        plot_ax,
        groups,
        values,
        orientation,
        use_full_range=True,
        violin_options=violin_options,
        mpl_artists=mpl_artists,
    )

    # `bodies` is matplotlib's own name for the density polygons this call
    # drew, so the mpl side needs no snapshot to know its own artists.
    _register_kde_layer(plot_ax, orientation, plot.get("bodies", []) or [])

    return plot


# ======================================================================
# Layer registration helpers
# ======================================================================
def _register_kde_layer(
    plot_ax: Axes, orientation: str, drawn: Collection[Any]
) -> None:
    """
    Register the density curves *this call* drew as a VIOLIN_KDE layer.

    Which collections the call drew, rather than which the axes holds. A
    ``PolyCollection`` is not a violin-specific artist -- ``fill_between``,
    ``stackplot`` and a filled ``kdeplot`` all produce one -- and sweeping the
    axes took whichever came first as the density::

        ax.fill_between([0, 1], [0, 0], [1, 1])
        sns.violinplot(data=df, x="g", y="v", ax=ax)
          violin_box(2), violin_kde(4)

    Four samples where the density has thirty: the layer described the band's
    four vertices under the violin's name, and the curve the violin actually
    drew was not in the reading at all. Not a partial answer -- a different
    artist's geometry announced as this chart's distribution.

    Filtered out of ``plot_ax.collections`` rather than iterated directly, so
    the order stays the axes' own: the ``x_levels`` below are paired with the
    curves positionally, and a violin named for its neighbour's category is
    the same defect one column along.

    Parameters
    ----------
    plot_ax : Axes
        The axes the violins were drawn on.
    orientation : str
        ``"vert"`` or ``"horz"``.
    drawn : Collection
        The collections this call added, by identity.
    """
    own = {id(collection) for collection in drawn}
    kde_polys = [
        collection
        for collection in plot_ax.collections
        if isinstance(collection, PolyCollection) and id(collection) in own
    ]
    if not kde_polys:
        return

    kde_lines: list[Line2D] = []
    poly_gids: list[str] = []

    for poly in kde_polys:
        paths = poly.get_paths()
        if not paths:
            continue
        boundary = np.asarray(paths[0].vertices)
        line = Line2D(boundary[:, 0], boundary[:, 1])
        line.axes = plot_ax

        gid = f"maidr-{uuid.uuid4()}"
        line.set_gid(gid)
        poly.set_gid(gid)

        kde_lines.append(line)
        poly_gids.append(gid)

    if not kde_lines:
        return

    level_key = MaidrKey.Y if orientation == "horz" else MaidrKey.X
    x_levels = LevelExtractorMixin.extract_level(plot_ax, level_key)

    FigureManager.create_maidr(
        plot_ax,
        PlotType.VIOLIN_KDE,
        poly_collections=kde_polys,
        kde_lines=kde_lines,
        poly_gids=poly_gids,
        x_levels=x_levels,
        orientation=orientation,
    )


def _register_box_layer(
    plot_ax: Axes,
    groups: list[str],
    values: list[np.ndarray],
    orientation: str,
    *,
    use_full_range: bool,
    violin_options: dict | None,
    mpl_artists: dict | None = None,
    sns_box_lines: list[dict] | None = None,
) -> None:
    """
    Register a VIOLIN_BOX layer from already-extracted groups and values.

    Takes the data rather than the call that produced it, because the two
    sides now find it differently: matplotlib's ``violinplot`` is handed its
    values positionally and has nothing else to ask, while seaborn's plotter
    has already resolved orientation, roles and category order by the time it
    draws, and re-deriving those from the caller's keywords is what #449 was.
    """
    if not groups or not values:
        return

    FigureManager.create_maidr(
        plot_ax,
        PlotType.VIOLIN_BOX,
        groups=groups,
        values=values,
        orientation=orientation,
        violin_options=violin_options,
        use_full_range=use_full_range,
        mpl_artists=mpl_artists,
        sns_box_lines=sns_box_lines,
    )


# ======================================================================
# Seaborn inner-box line classification
# ======================================================================
def _classify_sns_box_lines(new_lines: list[Line2D], orientation: str) -> list[dict]:
    """
    Group and classify seaborn's inner-box Line2D objects.

    Seaborn creates 3 Line2D per violin when ``inner="box"``:
      * whisker — thin line from min to max (longest data range)
      * iq      — thick line from Q1 to Q3 (medium data range)
      * median  — single-point marker (no range)

    Returns a list of dicts, one per violin, each with keys
    ``{"whisker": Line2D, "iq": Line2D, "median": Line2D}``.
    """
    if not new_lines:
        return []

    is_vert = orientation == "vert"

    # Group lines by their position (x for vertical, y for horizontal).
    groups: dict[float, list[Line2D]] = {}
    for line in new_lines:
        pos_data = line.get_xdata() if is_vert else line.get_ydata()
        pos = round(float(np.mean(pos_data)), 6)
        groups.setdefault(pos, []).append(line)

    result: list[dict] = []
    for pos in sorted(groups.keys()):
        lines = groups[pos]
        classified: dict[str, Line2D | None] = {
            "whisker": None,
            "iq": None,
            "median": None,
        }

        if len(lines) >= 3:
            # Sort by data range on the value axis (y for vert, x for horz).
            def _data_range(line: Line2D) -> float:
                vals = line.get_ydata() if is_vert else line.get_xdata()
                if len(vals) < 2:
                    return 0.0
                return float(np.ptp(vals))

            lines.sort(key=_data_range)
            classified["median"] = lines[0]  # smallest range (single point)
            classified["iq"] = lines[1]  # medium range
            classified["whisker"] = lines[2]  # largest range
        elif len(lines) == 2:

            def _data_range(line: Line2D) -> float:
                vals = line.get_ydata() if is_vert else line.get_xdata()
                if len(vals) < 2:
                    return 0.0
                return float(np.ptp(vals))

            lines.sort(key=_data_range)
            classified["median"] = lines[0]
            classified["whisker"] = lines[1]
        elif len(lines) == 1:
            classified["whisker"] = lines[0]

        result.append(classified)

    return result
