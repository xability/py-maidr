"""The warnings a patched plot suppresses stay inside that plot's call.

Every patched plotting function is drawn through
``maidr.patch.common._draw_quietly``, which silences matplotlib's own warnings
so they do not reach a screen-reader user mid-render. That suppression used to
be installed process-wide and never removed, so the first plot of a session
muted every ``warnings.warn`` raised afterwards — anywhere, arbitrarily far
from any figure, including MAIDR's own diagnostics, which are raised while the
schema is built rather than while the figure is drawn.

Scoping it to the call exposed the other half of the same problem: only
``common`` and the pie patch went through the helper, and the nine modules
that called ``wrapped()`` directly had been inheriting the process-wide filter
by accident — so whether a violin plot was quiet depended on whether a bar
chart had been drawn first. Those modules now draw through the helper too, and
the parametrisation below therefore covers one draw per patch module rather
than only the ``common``-routed ones.

Two properties are pinned for every kind:

* a warning raised *during* the draw does not reach the caller — the
  suppression the helper exists for, and what #328 changed;
* a warning raised *after* it still does — the leak the scoping fixed.

The during-the-draw warning is raised from temporarily wrapped
``Axes.add_line``/``add_patch``/``add_collection``/``add_image``. Every one of
these draws passes through one of them, so the same injection works for all
kinds, and it does not depend on any particular library version choosing to
warn about the data it was handed.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import contextlib  # noqa: E402
import warnings  # noqa: E402
from typing import Iterator  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import mplfinance as mpf  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from mplfinance.original_flavor import candlestick_ohlc  # noqa: E402

import maidr  # noqa: E402, F401  # imported for its side effect: activates the patches

DURING_THE_DRAW = "raised while the figure was being drawn"

# One kind per patch module, so a module left calling `wrapped()` directly
# fails on its own row rather than hiding behind another module's coverage.
KINDS = [
    "bar",  # common
    "barh",  # common
    "scatter",  # common
    "plot",  # lineplot
    "hist",  # histogram
    "hist_step",  # histogram
    "pie",  # pieplot
    "imshow",  # heatmap
    "boxplot",  # boxplot
    "violinplot",  # violinplot
    "candlestick",  # candlestick
    "mplfinance",  # mplfinance
    "sns_boxplot",  # boxplot
    "sns_catplot_box",  # boxplot
    "sns_violinplot",  # violinplot
    "sns_heatmap",  # heatmap
    "sns_histplot",  # histogram
    "sns_kdeplot",  # kdeplot
    "sns_lineplot",  # lineplot
    "sns_regplot",  # regplot
    "sns_regplot_line_only",  # regplot
]


def _ohlc_frame() -> pd.DataFrame:
    """Build the smallest frame ``mplfinance.plot`` accepts."""
    return pd.DataFrame(
        {
            "Open": [1.0, 2.0, 3.0],
            "High": [3.0, 4.0, 5.0],
            "Low": [0.5, 1.5, 2.5],
            "Close": [2.0, 3.0, 4.0],
            "Volume": [10, 20, 30],
        },
        index=pd.date_range("2024-01-01", periods=3),
    )


def _draw(kind: str, ax) -> None:
    """Draw one patched plot of the named kind on ``ax``."""
    if kind == "bar":
        ax.bar(["a", "b"], [1, 2])
    elif kind == "barh":
        ax.barh(["a", "b"], [1, 2])
    elif kind == "scatter":
        ax.scatter([1, 2, 3], [4, 5, 6])
    elif kind == "plot":
        ax.plot([1, 2, 3], [4, 5, 6])
    elif kind == "hist":
        ax.hist([1, 1, 2, 3, 3, 3])
    elif kind == "hist_step":
        # A stepped histogram is outlined rather than filled with the patched
        # `Axes.bar`, so nothing else suppresses `Axes.hist` for it.
        ax.hist([1, 1, 2, 3, 3, 3], histtype="step")
    elif kind == "pie":
        ax.pie([30, 50, 20])
    elif kind == "imshow":
        ax.imshow([[1, 2], [3, 4]])
    elif kind == "boxplot":
        ax.boxplot([[1, 2, 3, 4, 5]])
    elif kind == "violinplot":
        ax.violinplot([[1, 2, 3, 4, 5]])
    elif kind == "candlestick":
        candlestick_ohlc(ax, [(1.0, 1.0, 3.0, 0.5, 2.0), (2.0, 2.0, 4.0, 1.5, 3.0)])
    elif kind == "mplfinance":
        # `mpf.plot` lays out its own figure, so `ax` is unused for this kind
        # and the test closes every figure rather than only the one it made.
        mpf.plot(_ohlc_frame(), type="candle", volume=True)
    elif kind == "sns_boxplot":
        sns.boxplot(x=[1, 2, 3, 4, 5], ax=ax)
    elif kind == "sns_catplot_box":
        # Reaches `_CategoricalPlotter.plot_boxes` without going through
        # `seaborn.boxplot`, which is the only path for which wrapping
        # `plot_boxes` buys anything. This row does not on its own prove that
        # wrap works -- the injected warning lands inside `Axes.bxp`, which is
        # suppressed in its own right, so it passes either way. It covers the
        # path; `test_catplot_suppresses_what_plot_boxes_raises_around_the_draw`
        # covers the wrap. Like `mpf.plot`, it lays out its own figure, so
        # `ax` is unused.
        sns.catplot(x=[1, 2, 3, 4, 5], kind="box")
    elif kind == "sns_violinplot":
        sns.violinplot(x=[1, 2, 3, 4, 5], ax=ax)
    elif kind == "sns_heatmap":
        sns.heatmap([[1.0, 2.0], [3.0, 4.0]], ax=ax)
    elif kind == "sns_histplot":
        sns.histplot(x=[1, 1, 2, 3, 3, 3], ax=ax)
    elif kind == "sns_kdeplot":
        sns.kdeplot(x=[1.0, 2.0, 3.0, 4.0, 5.0], ax=ax)
    elif kind == "sns_lineplot":
        sns.lineplot(x=[1, 2, 3], y=[4, 5, 6], ax=ax)
    elif kind == "sns_regplot":
        sns.regplot(x=[1.0, 2.0, 3.0, 4.0], y=[1.0, 3.0, 2.0, 5.0], ax=ax)
    elif kind == "sns_regplot_line_only":
        # `scatter=False` is the branch that draws without going through
        # `common`, so it is the one the regplot patch had to route itself.
        sns.regplot(
            x=[1.0, 2.0, 3.0, 4.0], y=[1.0, 3.0, 2.0, 5.0], scatter=False, ax=ax
        )
    else:  # pragma: no cover - guards a typo in the parametrisation
        raise AssertionError(f"unknown plot kind: {kind}")


@contextlib.contextmanager
def _warning_from_inside_the_draw() -> Iterator[None]:
    """
    Make the first artist any draw adds raise one warning.

    Adding an artist happens inside the plotting call the patch wrapped, which
    is the only place `_draw_quietly` can scope anything, and every kind above
    reaches one of these four methods. Warning from here therefore stands in
    for whatever matplotlib itself would have warned about, without depending
    on a particular version choosing to warn.
    """
    adders = ("add_line", "add_patch", "add_collection", "add_image")
    # These are defined on a base of `Axes`, so patch and restore them where
    # they live rather than shadowing them on `Axes` itself.
    owners = {
        name: next(cls for cls in Axes.__mro__ if name in cls.__dict__)
        for name in adders
    }
    originals = {name: owners[name].__dict__[name] for name in adders}
    fired = False

    def _noisy(original):
        def add(self, *args, **kwargs):
            nonlocal fired
            if not fired:
                fired = True
                warnings.warn(DURING_THE_DRAW, UserWarning)
            return original(self, *args, **kwargs)

        return add

    for name, original in originals.items():
        setattr(owners[name], name, _noisy(original))
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(owners[name], name, original)

    assert fired, "no artist was added, so nothing warned during the draw"


@pytest.mark.parametrize("kind", KINDS)
def test_a_warning_raised_during_the_plot_does_not_reach_the_caller(kind):
    _, ax = plt.subplots()
    try:
        # "always" here so the recorder cannot silently drop a repeat of a
        # warning an earlier parametrisation already reported from the same
        # line. It does not mask what is under test: `_draw_quietly` installs
        # its "ignore" *inside* this scope, and an inner filter wins.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with _warning_from_inside_the_draw():
                _draw(kind, ax)

        assert DURING_THE_DRAW not in [str(w.message) for w in caught]
    finally:
        plt.close("all")


@pytest.mark.parametrize("kind", KINDS)
def test_a_warning_raised_after_the_plot_still_reaches_the_caller(kind):
    _, ax = plt.subplots()
    try:
        _draw(kind, ax)

        # Deliberately no `simplefilter` here: the recorder inherits whatever
        # filters are installed, which is the whole point. Forcing "always"
        # would override a leaked "ignore" and the test would pass either way.
        with warnings.catch_warnings(record=True) as caught:
            warnings.warn(f"heard after the {kind}", UserWarning)

        assert [str(w.message) for w in caught] == [f"heard after the {kind}"]
    finally:
        plt.close("all")


def test_catplot_suppresses_what_plot_boxes_raises_around_the_draw():
    """
    The one path for which wrapping ``_CategoricalPlotter.plot_boxes`` buys
    anything, and it needs its own injection point.

    Reached through ``seaborn.boxplot`` the wrap is a no-op — ``plot_boxes``
    is already nested inside a suppressed call. ``seaborn.catplot`` reaches it
    without going through ``seaborn.boxplot``, so that is the path under test.

    ``_warning_from_inside_the_draw`` cannot see the difference: the first
    artist a box draw adds is added *inside* ``Axes.bxp``, which is patched
    and suppressed in its own right, so the warning never reaches the region
    the ``plot_boxes`` wrap covers and the assertion holds either way. What
    the wrap covers is what ``plot_boxes`` itself raises around its call to
    ``bxp`` — so the warning is raised from a wrapper installed *over*
    maidr's ``Axes.bxp``, which runs inside ``plot_boxes`` and outside the
    suppression ``bxp`` installs for itself.
    """
    raised = 'raised by plot_boxes, outside the bxp it calls'
    outer = Axes.bxp

    def noisy_bxp(self, *args, **kwargs):
        warnings.warn(raised, UserWarning)
        return outer(self, *args, **kwargs)

    Axes.bxp = noisy_bxp
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            sns.catplot(x=[1, 2, 3, 4, 5], kind="box")

        assert raised not in [str(w.message) for w in caught]
    finally:
        Axes.bxp = outer
        plt.close("all")


def test_the_plot_call_leaves_the_filter_list_as_it_found_it():
    # `catch_warnings` restores what it saved, so drawing must be neutral --
    # the leak this guards against was a filter that outlived the call.
    fig, ax = plt.subplots()
    try:
        before = list(warnings.filters)
        ax.bar(["a", "b"], [1, 2])

        assert warnings.filters == before
    finally:
        plt.close(fig)


def test_repeated_plots_do_not_accumulate_filters():
    # Not a growth guard -- CPython's `warnings._add_filter` de-duplicates, so
    # even the old process-wide call could not accumulate. This pins that
    # drawing is neutral however many times it happens.
    fig, ax = plt.subplots()
    try:
        before = len(warnings.filters)
        for _ in range(25):
            ax.bar(["a", "b"], [1, 2])

        assert len(warnings.filters) == before
    finally:
        plt.close(fig)
