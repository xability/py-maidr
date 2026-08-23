"""
An ``lmplot`` hue split its layers correctly and named none of them (#612).

`lmplot(hue=...)` is one `regplot` call per level, and each call registers a
scatter and a fitted curve. The split was right -- the two point layers hold
disjoint halves of the frame -- and all four layers came out anonymous, so a
reader was handed point, curve, point, curve over one axes with nothing
saying which pair was which. The same data through `scatterplot(hue=...)`
names both of its layers.

Measured before the fix, two levels of thirty rows each::

    lmplot(x=, y=, hue=)          point None (30)  smooth None
                                  point None (30)  smooth None
    scatterplot(x=, y=, hue=)     point 'p'  (30)
                                  point 'q'  (30)

The name was there for the asking: `legend_of` resolves the `FacetGrid`'s
figure legend from the panel.

Two things were needed, and neither works alone.

**The colour has to name one layer, not one artist among several.** This is
#595's shape -- "wrong where a *layer* is the artist" -- so `name_for`
rather than `names_for`: a `regplot` call draws one group, and the colour of
its curve and its collection is what says which level.

**The match has to be deferred.** `FacetGrid.add_legend()` runs after every
panel is drawn, so at registration there is no legend anywhere -- the timing
#561 hit with `pairplot`, and the reason `GROUP_NAME` accepts a callable.
Resolving eagerly leaves every layer `None` again, which is what the
mutation sweep on this file shows.

`ScatterPlot` reads `GROUP_NAME` as part of this. It took its name only from
`HUE_GROUP`, which also carries *which points* belong to the group, because
the scatter patch splits one collection between levels. A `regplot`'s
scatter is its level entire, so there is nothing to filter and only the name
is in question -- which is exactly what `GROUP_NAME` is for, and what every
other opting-in class already reads.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn as sns

import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    # `p` sits low on x and `q` high, with no overlap, so which layer holds
    # which group is a fact about the numbers rather than about draw order.
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "x": list(rng.uniform(0, 1, 30)) + list(rng.uniform(10, 11, 30)),
            "y": list(rng.normal(20, 1, 60)),
            "g": ["p"] * 30 + ["q"] * 30,
        }
    )


def _layers(fig) -> list:
    """Every layer as ``(type, name)``, after a real render."""
    maidr.render(fig)._repr_html_()
    return [
        (plot.type.value, plot.schema.get("name"))
        for plot in FigureManager.get_maidr(fig).plots
    ]


def _points(fig) -> list:
    """Each point layer as ``(name, whether it holds the low group)``."""
    maidr.render(fig)._repr_html_()
    out = []
    for plot in FigureManager.get_maidr(fig).plots:
        if plot.type.value != "point":
            continue
        xs = [float(point["x"]) for point in plot.schema["data"]]
        out.append((plot.schema.get("name"), max(xs) < 5))
    return out


def test_every_layer_of_a_hue_split_lmplot_is_named():
    """Four layers, four names, and the pairs are right."""
    named = _layers(sns.lmplot(data=_frame(), x="x", y="y", hue="g").figure)

    assert sorted(named) == [
        ("point", "p"),
        ("point", "q"),
        ("smooth", "p"),
        ("smooth", "q"),
    ]


def test_each_name_is_on_the_layer_holding_that_groups_data():
    """The half that a count of names would not catch.

    `p` is the low half of x and `q` the high half, with no overlap, so a
    reading that named the layers in the wrong order still gives four names
    and fails here.
    """
    assert sorted(_points(sns.lmplot(data=_frame(), x="x", y="y", hue="g").figure)) == [
        ("p", True),
        ("q", False),
    ]


def test_a_regplot_without_a_hue_is_unnamed():
    """One group against no legend. `name_for` declines, and the layer reads
    exactly as it did before -- which is what makes this change additive."""
    _, ax = plt.subplots()
    sns.regplot(data=_frame(), x="x", y="y", ax=ax)

    assert _layers(ax.get_figure()) == [("point", None), ("smooth", None)]


def test_an_lmplot_without_a_hue_is_unnamed():
    """A `FacetGrid` with nothing to build a legend from."""
    named = _layers(sns.lmplot(data=_frame(), x="x", y="y").figure)

    assert named == [("point", None), ("smooth", None)]


def test_a_hue_split_lmplot_drawn_without_its_fit_is_still_named():
    """`fit_reg=False` draws points and no curve at all, so the colour has to
    come off the collection instead. Two branches, and a fix that only read
    the curve would leave this chart exactly as it was."""
    named = _layers(
        sns.lmplot(data=_frame(), x="x", y="y", hue="g", fit_reg=False).figure
    )

    assert sorted(named) == [("point", "p"), ("point", "q")]


def test_a_binned_lmplot_names_its_estimates_and_its_fit_alike():
    """`x_estimator=` collapses each x to an estimate and draws an interval
    around it, which takes the `ERRORBAR` branch instead of the scatter one.

    Both layers of a group are named or neither is. Measured before
    `ErrorBarPlot` opted into `GROUP_NAME`, the curve was named and the band
    beside it was not:

        error_bar None (4)   smooth 'p'
        error_bar None (4)   smooth 'q'

    which announced a group and its own uncertainty as unrelated layers --
    the same reading #451 was about from the other side, where the intervals
    were their own fitted curves.
    """
    frame = _frame().assign(dose=lambda f: np.round(f["x"]))
    named = _layers(
        sns.lmplot(data=frame, x="dose", y="y", hue="g", x_estimator=np.mean).figure
    )

    assert sorted(named) == [
        ("error_bar", "p"),
        ("error_bar", "q"),
        ("smooth", "p"),
        ("smooth", "q"),
    ]


def test_a_binned_regplot_without_a_hue_is_unnamed():
    """The same additive guarantee on the interval branch."""
    _, ax = plt.subplots()
    frame = _frame().assign(dose=lambda f: np.round(f["x"]))
    sns.regplot(data=frame, x="dose", y="y", x_estimator=np.mean, ax=ax)

    assert _layers(ax.get_figure()) == [("error_bar", None), ("smooth", None)]


def test_a_faceted_lmplot_names_each_panels_own_groups():
    """A panel holding one level is named too.

    `col` here splits on a variable that puts `p` alone in one panel and `q`
    alone in the other, so each panel holds a single group -- the case that
    needs the name most, since nothing else in the panel says which level it
    is drawn from.
    """
    frame = _frame().assign(panel=lambda f: f["g"])
    named = _layers(sns.lmplot(data=frame, x="x", y="y", hue="g", col="panel").figure)

    assert sorted(named) == [
        ("point", "p"),
        ("point", "q"),
        ("smooth", "p"),
        ("smooth", "q"),
    ]
