import copy
import gc
import html
import json
import pickle
import re
import threading
import weakref

import matplotlib.pyplot as plt
import pandas as pd
import pytest
import seaborn as sns
from htmltools import Tag

import maidr

from maidr.core import Maidr
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.enum.library import Library


# test cases for invalid inputs
def test_get_axes_from_none():
    assert FigureManager.get_axes(None) is None


def test_create_maidr_with_none_axes(mocker):
    with pytest.raises(ValueError) as e:
        FigureManager.create_maidr(None, mocker.Mock())  # type: ignore
    assert "No plot found." == str(e.value)


def test_create_maidr_with_none_plot_type(mocker):
    with pytest.raises(ValueError) as e:
        FigureManager.create_maidr(mocker.Mock(), None)  # type: ignore
    assert "No plot type found." == str(e.value)


# Parametrize the test to run with different libraries and plot types.
@pytest.mark.parametrize(
    "lib, plot_type",
    [
        # Parametrize matplotlib plots.
        (Library.MATPLOTLIB, PlotType.BAR),
        (Library.MATPLOTLIB, PlotType.BOX),
        # ``ax.step`` delegates to the already-patched ``Axes.plot``; this
        # guards against it registering a STEP *and* a LINE layer.
        (Library.MATPLOTLIB, PlotType.STEP),
        # ``Axes.pie`` returns a tuple of artist lists rather than an artist,
        # so its patch resolves the axes off the call instead of the return
        # value; this guards that it still registers exactly one layer.
        (Library.MATPLOTLIB, PlotType.PIE),
        # Parametrize seaborn plots.
        (Library.SEABORN, PlotType.BAR),
        (Library.SEABORN, PlotType.BOX),
        (Library.SEABORN, PlotType.COUNT),
    ],
)
def test_get_maidr_with_single_axes(plot_fixture, lib, plot_type):
    fig, ax = plot_fixture(lib, plot_type)
    maidr = FigureManager.get_maidr(fig)

    assert isinstance(maidr, Maidr)
    assert maidr.fig is fig

    assert len(maidr.plots) == len([plot_type]) == 1
    for m_data, p_type in zip(maidr.plots, [plot_type]):
        if p_type == PlotType.COUNT:
            assert m_data.type == PlotType.BAR
        else:
            assert m_data.type == p_type


# group tests related to matplotlib
class TestMatplotlibFigureManager:
    # test `get_figure()` for matplotlib plots
    def test_get_axes_from_subplot_axes(self, axes):
        assert FigureManager.get_axes(axes) == axes

    def test_get_figure_from_bar_container(self, axes):
        bar = plt.bar([1, 2, 3], [4, 5, 6])
        assert FigureManager.get_axes(bar) == axes


# group tests related to seaborn
class TestSeabornFigureManager:
    # test `get_figure()` for seaborn plots
    def test_get_figure_from_barplot_axes(self, axes):
        bar_ax = sns.barplot(x=[1, 2, 3], y=[4, 5, 6])
        assert FigureManager.get_axes(bar_ax) == axes

    def test_get_figure_from_countplot_axes(self, axes):
        count_ax = sns.countplot(x=[1, 2, 2, 3, 3, 3])
        assert FigureManager.get_axes(count_ax) == axes

    # seaborn's figure-level functions return a Grid, which is not an Artist.
    # Each resolved to None, so `maidr.render(sns.lmplot(...))` raised on the
    # very object the user was handed, though every layer was registered on
    # the grid's figure (#694).
    def test_get_axes_from_facet_grid(self):
        grid = sns.lmplot(data=_frame(), x="x", y="y")
        try:
            assert FigureManager.get_axes(grid) == grid.figure.axes
        finally:
            plt.close(grid.figure)

    def test_get_axes_from_joint_grid(self):
        grid = sns.jointplot(data=_frame(), x="x", y="y")
        try:
            assert FigureManager.get_axes(grid) == grid.figure.axes
        finally:
            plt.close(grid.figure)

    def test_get_axes_from_pair_grid(self):
        grid = sns.pairplot(_frame())
        try:
            assert FigureManager.get_axes(grid) == grid.figure.axes
        finally:
            plt.close(grid.figure)


def _frame():
    return pd.DataFrame(
        {"x": [1.0, 2.0, 3.0, 4.0, 5.0], "y": [2.0, 4.0, 5.0, 4.0, 6.0]}
    )


def _layer_types(rendered) -> list[str]:
    """The layer types in the schema on the emitted ``<svg>``."""
    markup = str(rendered)
    frame = re.search(r'srcdoc="([^"]*)"', markup)
    if frame is not None:
        markup = html.unescape(frame.group(1))
    match = re.search(r'maidr="([^"]*)"', markup)
    assert match, "no MAIDR schema in the emitted markup"
    schema = json.loads(html.unescape(match.group(1)))
    return [
        layer["type"]
        for row in schema["subplots"]
        for cell in row
        for layer in cell.get("layers", [])
    ]


class TestAGridGoesThroughTheFrontDoor:
    """A seaborn Grid is what `lmplot` returns, and `lmplot` is documented
    as stable, so the documented way to use it must reach every entry
    point -- not only `grid.figure`, which is what the tests had been
    handing over."""

    def test_render_reads_the_layers_registered_on_the_grids_figure(self):
        grid = sns.lmplot(data=_frame(), x="x", y="y")
        try:
            tag = maidr.render(grid, use_cdn=False)

            assert isinstance(tag, Tag)
            assert _layer_types(tag) == ["point", "smooth"]
        finally:
            plt.close(grid.figure)

    def test_close_forgets_the_grids_figure(self):
        grid = sns.lmplot(data=_frame(), x="x", y="y")
        try:
            assert grid.figure in FigureManager.figs

            maidr.close(grid)

            assert grid.figure not in FigureManager.figs
        finally:
            plt.close(grid.figure)


class TestCloseResolvesTheFigureItIsHanded:
    """`maidr.close()` and `maidr.close(fig)` raised `AttributeError`.

    A `Figure` is an `Artist`, so `get_axes` answered it with `fig.axes` --
    a list -- and `close` called `.get_figure()` on the list. Only the
    `close(ax)` form was ever exercised, and the documented default
    (`plot=None`, meaning `plt.gcf()`) was exactly the broken one (#694).
    """

    @pytest.fixture(autouse=True)
    def _fresh_figure(self):
        plt.close("all")
        fig, ax = plt.subplots()
        ax.bar(["a", "b"], [1, 2])
        assert fig in FigureManager.figs
        self.fig, self.ax = fig, ax
        yield
        FigureManager.figs.pop(fig, None)
        plt.close(fig)

    def test_close_with_no_argument_closes_the_current_figure(self):
        maidr.close()

        assert self.fig not in FigureManager.figs

    def test_close_with_the_figure(self):
        maidr.close(self.fig)

        assert self.fig not in FigureManager.figs

    def test_close_with_an_axes_still_works(self):
        maidr.close(self.ax)

        assert self.fig not in FigureManager.figs

    def test_a_list_of_axes_resolves_to_their_figure(self):
        # A raw list is resolved to its first entry; both axes here belong to
        # the one figure, so that is the figure rendered.
        other = self.fig.add_subplot(2, 1, 2)
        other.bar(["c", "d"], [3, 4])

        tag = maidr.render([self.ax, other], use_cdn=False)

        assert isinstance(tag, Tag)
        assert _layer_types(tag) == ["bar", "bar"]

    def test_close_on_something_that_is_not_a_plot_does_not_raise(self):
        # Closing is the one call that should not complain about what it was
        # handed: there is nothing to close, so nothing happens.
        maidr.close("not a plot")

        assert self.fig in FigureManager.figs


def test_one_figure_registered_concurrently_gets_one_maidr():
    """The check-then-act in ``_get_maidr`` runs under the lock.

    Two threads registering layers on the same figure both find it missing
    and both create a ``Maidr`` for it, unless the check and the insert are
    atomic. The loser's object is then dropped from ``figs`` while the
    layers registered against it are not -- a chart that renders with some
    of its layers silently missing.

    Not reachable through the Shiny path today, where registration stays on
    the event loop because plotting is the user's code and runs before the
    render is offloaded (#505 records that measurement). But that is a
    property of where callers live, not of this method, and #504 made the
    surrounding code genuinely multi-threaded for the first time.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    FigureManager.figs.pop(fig, None)

    seen = []
    # One constant for both, because they must agree: a barrier expecting
    # more arrivals than there are threads waits forever. A stray edit made
    # them disagree once and the suite hung rather than failed, which is
    # why the joins below are bounded.
    racers = 8
    start = threading.Barrier(racers)

    def register():
        start.wait()
        seen.append(FigureManager._get_maidr(fig, PlotType.BAR))

    workers = [threading.Thread(target=register) for _ in range(racers)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)
            assert not worker.is_alive(), "registration deadlocked"

        assert len({id(maidr) for maidr in seen}) == 1, (
            "concurrent registration created more than one Maidr for one "
            "figure; layers registered against the loser are lost"
        )
        assert seen[0] is FigureManager.figs[fig]
    finally:
        # `figs` is a plain dict, not weak-keyed, so closing the figure does
        # not drop the entry -- that is #456. Other tests in this suite leave
        # theirs behind; this one registered a figure purely to race on it,
        # so it cleans up rather than adding to the pile it was written
        # alongside.
        FigureManager.figs.pop(fig, None)
        plt.close(fig)


#: How long thread A parks between its two appends, waiting for B.
#:
#: Paid in full on every passing run -- see the test below -- so it is kept
#: as small as detection allows rather than as large as feels safe.
_HANDOFF_DEADLINE = 0.3


def test_a_layer_keeps_the_selector_id_minted_with_it(monkeypatch):
    """``plots`` and ``selector_ids`` are appended separately but paired.

    ``Maidr._flatten_maidr`` and ``_create_html_tag`` both zip them, and
    ``_drop_superseded_layers`` spells out the cost of drift: every
    surviving layer wears its neighbour's id, so the highlight lands on the
    wrong mark with nothing raised.

    Each ``append`` is atomic under the GIL; the *pair* is not.

    Driven by two threads with an explicit handoff rather than a crowd
    racing off a barrier. A crowd is a *probabilistic* detector -- measured
    against an unguarded build it caught the bug on 3 of 5 runs at eight
    threads, and raising the count to get 5 of 5 made the suite hang. This
    version forces the exact interleave, so it detects on every run and
    finishes in milliseconds.
    """
    from maidr.core.maidr import Maidr as MaidrClass
    from maidr.core.plot import MaidrPlotFactory

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    FigureManager.figs.pop(fig, None)

    who = threading.local()

    # Tagged as the layer is built, inside the call that mints its id.
    # Reading `plots[-1]` after `create_maidr` returns would be wrong:
    # the lock is released before the return, so another thread can append
    # in between and `plots[-1]` is then somebody else's layer.
    real_create = MaidrPlotFactory.create

    def tagging_create(*args, **kwargs):
        plot = real_create(*args, **kwargs)
        plot._registered_by = who.tag
        return plot

    monkeypatch.setattr(MaidrPlotFactory, "create", staticmethod(tagging_create))
    first_appended = threading.Event()
    second_done = threading.Event()

    def paced_unique_id():
        """Pause thread A between its two appends.

        `create_maidr` evaluates this *after* appending to `plots` and
        *before* appending to `selector_ids`, so it is the seam the race
        runs through -- a real call site rather than a hook nothing calls.

        The wait is a deadline, not a handshake, and both outcomes are
        meaningful. Note it is *always* paid on a passing run: the lock
        blocks B for A's whole critical section, so A parks here for the
        full deadline every time. That makes it suite time rather than a
        worst case, which is why it is 0.3s and not longer -- measured, an
        unguarded build is still caught 5/5 at 0.15s.

        Unguarded, B is free to complete both of its appends while A is
        parked here, and A's id then lands behind B's -- the misalignment.
        Guarded, B cannot enter the critical section at all, so this simply
        times out and the order is preserved. Either way the test finishes.
        """
        if getattr(who, "tag", None) == "A":
            first_appended.set()
            second_done.wait(_HANDOFF_DEADLINE)
        return f"id-{who.tag}"

    monkeypatch.setattr(MaidrClass, "_unique_id", staticmethod(paced_unique_id))

    def register_a():
        who.tag = "A"
        FigureManager.create_maidr(ax, PlotType.BAR)

    def register_b():
        who.tag = "B"
        first_appended.wait(5)
        FigureManager.create_maidr(ax, PlotType.BAR)
        second_done.set()

    threads = [
        threading.Thread(target=register_a),
        threading.Thread(target=register_b),
    ]
    try:
        for thread in threads:
            thread.start()
        # B waits on A, and A waits on B; the lock is what makes that
        # resolve rather than deadlock -- B cannot enter the critical
        # section until A leaves it, so A never blocks inside it.
        for thread in threads:
            thread.join(timeout=10)
            assert not thread.is_alive(), "registration deadlocked"

        maidr_obj = FigureManager.figs[fig]
        pairs = list(zip(maidr_obj.plots, maidr_obj.selector_ids))
        assert len(pairs) == 2

        misaligned = [
            (getattr(plot, "_registered_by", None), selector_id)
            for plot, selector_id in pairs
            if selector_id != f"id-{getattr(plot, '_registered_by', None)}"
        ]
        assert not misaligned, (
            f"{misaligned} -- a layer is sitting opposite another call's "
            "selector id; the highlight would land on the wrong mark"
        )
    finally:
        second_done.set()
        FigureManager.figs.pop(fig, None)
        plt.close(fig)


def test_a_closed_figure_is_not_kept_alive_by_having_been_registered():
    """Registering a chart must not outlive the application's own reference.

    Layers are registered when a chart is *plotted*, not when it is
    rendered, so before #456 every supported figure entered a class-level
    dict and stayed reachable for the life of the process -- long after the
    application dropped it and matplotlib closed it. The ``plt.show()`` path
    escaped it only because the backend calls ``destroy`` explicitly
    (``maidr/backend.py``); a Shiny or Streamlit render never goes through
    ``plt.show``, so a long-lived server accumulated one figure per render.

    The record lives on the figure now, which makes the whole graph an
    isolated cycle once the caller lets go.

    Driven through ``ax.bar`` rather than ``_get_maidr`` directly, so that
    the reference the extraction itself takes -- ``MaidrPlot.ax``,
    ``_elements``, and ``BarPlot._own_bars`` -- are all present. Those are
    what defeated the ``WeakKeyDictionary`` attempt recorded in #498: a
    value that reaches its own key keeps a weak key alive forever. They are
    harmless here precisely because they close a cycle rather than a chain.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    assert fig in FigureManager.figs, "the figure was never registered"

    ref = weakref.ref(fig)
    plt.close(fig)
    del fig, ax
    # Two passes: the first may only break the cycle, and matplotlib's
    # artists refer to each other in both directions throughout.
    gc.collect()
    gc.collect()

    assert ref() is None, (
        "a registered figure survived the application dropping it; the "
        "registry is holding it for the life of the process"
    )


def test_the_registry_reads_as_the_mapping_it_replaced():
    """Storage moved onto the figure; the shape callers see did not.

    ``figs`` is read directly across this suite and named in
    ``FigureManager``'s own docstring, so the operations it supports are
    part of what the move had to preserve -- including ``pop``'s two
    signatures, which ``destroy`` and this file's cleanup rely on
    differently.

    Deliberately **not** a detector for the move itself: a plain dict
    satisfies every assertion here, which is the whole point of preserving
    the interface. ``test_a_closed_figure_is_not_kept_alive_by_having_been_registered``
    is what tells the two apart. This one guards later edits to
    ``_FigureRecords``.

    Everything is asserted about *this* figure rather than about the
    registry's total contents. An earlier draft asserted ``len(figs) == 1``,
    which passed alone and failed in a full run -- other tests leave their
    figures registered -- and would have passed or failed by collection
    timing once they stopped doing so.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    try:
        maidr = FigureManager.figs[fig]

        assert fig in FigureManager.figs
        assert FigureManager.figs.get(fig) is maidr
        assert fig in list(FigureManager.figs)

        assert FigureManager.figs.pop(fig) is maidr
        assert fig not in FigureManager.figs
        assert fig not in list(FigureManager.figs)
        assert FigureManager.figs.get(fig) is None
        assert FigureManager.figs.get(fig, "fallback") == "fallback"

        # Absent: `pop` with no default raises, with one returns it. `destroy`
        # catches the KeyError to mean "never registered", so a `pop` that
        # answered `None` there would silently call `destroy` on nothing.
        assert FigureManager.figs.pop(fig, None) is None
        with pytest.raises(KeyError):
            FigureManager.figs.pop(fig)
        with pytest.raises(KeyError):
            FigureManager.figs[fig]
    finally:
        FigureManager.figs.pop(fig, None)
        plt.close(fig)


def test_a_shallow_copy_of_a_figure_is_not_its_original_s_chart():
    """Storing the record on the figure means copies inherit the attribute.

    ``copy.copy`` on a ``Figure`` copies the ``__dict__`` entries themselves,
    so without a check the copy answers as registered and hands back a
    ``Maidr`` bound to the *original* -- which would render the original's
    chart, with the original's data, under the copy. The module-level dict
    could not do that: only the object actually inserted was ever a key.

    So the copy is treated as unregistered, which is what it is. Whoever
    plots on it registers it.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    twin = copy.copy(fig)
    try:
        assert fig in FigureManager.figs
        assert twin not in FigureManager.figs
        assert FigureManager.figs.get(twin) is None
        with pytest.raises(KeyError):
            FigureManager.figs[twin]

        # And asking about the copy must not take the original's record away.
        assert FigureManager.figs.pop(twin, None) is None
        assert fig in FigureManager.figs
    finally:
        FigureManager.figs.pop(fig, None)
        plt.close(fig)


@pytest.mark.parametrize(
    "clone",
    [
        pytest.param(copy.deepcopy, id="deepcopy"),
        pytest.param(lambda fig: pickle.loads(pickle.dumps(fig)), id="pickle"),
    ],
)
def test_a_figure_that_is_copied_wholesale_keeps_its_chart(clone):
    """Unlike a shallow copy, these rebuild the record alongside the figure.

    Both are new couplings: a figure's pickle now carries the ``Maidr`` and
    every ``MaidrPlot`` under it, which it did not when the record lived in
    a module-level dict. Pinned in both directions -- that the round trip
    still *succeeds*, since anything unpicklable added to those classes
    would now break pickling a plain figure, and that the copy's record
    belongs to the copy rather than to the original, which is what
    distinguishes this from the shallow case above.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    twin = clone(fig)
    try:
        assert twin in FigureManager.figs
        assert FigureManager.figs[twin] is not FigureManager.figs[fig]
        assert FigureManager.figs[twin].fig is twin
    finally:
        FigureManager.figs.pop(fig, None)
        FigureManager.figs.pop(twin, None)
        plt.close(fig)


def test_del_and_pop_agree_about_what_is_registered():
    """Two spellings of one operation must not disagree.

    ``__delitem__`` originally deleted the attribute directly while ``pop``
    went through the ownership check, so ``del figs[copy]`` succeeded on a
    shallow copy that ``figs.pop(copy)`` refused. Nothing calls
    ``__delitem__`` today, which is exactly why it would have gone unnoticed
    until the first caller.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    twin = copy.copy(fig)
    try:
        with pytest.raises(KeyError):
            FigureManager.figs.pop(twin)
        with pytest.raises(KeyError):
            del FigureManager.figs[twin]

        del FigureManager.figs[fig]
        assert fig not in FigureManager.figs
        with pytest.raises(KeyError):
            del FigureManager.figs[fig]
    finally:
        FigureManager.figs.pop(fig, None)
        plt.close(fig)


def test_a_cached_figure_keeps_its_chart_across_renders():
    """#452's hazard, against #456's fix.

    A figure built lazily and cached -- ``@reactive.calc``, any memoised
    helper -- is closed by the render that opened it and is still the live
    chart. Dropping its record there is what made every later render fall
    back to a static image: an accessible chart quietly turning into a
    picture. That is why #456 could not be fixed by dropping on
    ``close_event``, and why a bounded cache would have carried the same
    hazard in miniature.

    Storing the record on the figure ties its lifetime to the caller's own
    reference instead, so the cache holding the figure is exactly what keeps
    the record. Both halves are asserted -- the record survives repeated
    render-and-close cycles, *and* letting go really does reclaim it --
    because a fix that never released anything would pass the first alone.

    **What this does not detect.** It is not a guard against the
    ``close_event`` design. Tried: dropping the record from a
    ``close_event`` handler leaves this test passing, because under ``Agg``
    ``plt.close()`` fires no ``close_event`` at all (measured: 0 callbacks).
    That is worth knowing for its own sake -- it means that option would
    also have been inert in a headless server, which is where the leak it
    was meant to fix actually happens -- but it means the reclaim half is
    the only part with a falsified detector behind it, against the plain
    dict this replaced.
    """
    cache = {}

    def cached_figure():
        if "fig" not in cache:
            fig, ax = plt.subplots()
            ax.bar(["a", "b", "c"], [1, 2, 3])
            cache["fig"] = fig
        return cache["fig"]

    for flush in range(3):
        fig = cached_figure()
        maidr.render(fig)
        plt.close(fig)
        gc.collect()
        assert fig in FigureManager.figs, (
            f"the cached figure lost its record on flush {flush}; every "
            "later render would fall back to a static image"
        )
        assert len(FigureManager.figs[fig].plots) == 1

    ref = weakref.ref(cache.pop("fig"))
    del fig
    gc.collect()
    gc.collect()
    assert ref() is None, "the cache let go but the figure was not reclaimed"


def test_a_stale_copy_of_a_destroyed_figure_answers_rather_than_raises():
    """``Maidr.destroy()`` deletes ``_fig``, and a copy can still hold it.

    ``FigureManager.destroy`` pops the record before tearing the ``Maidr``
    down, which is why a *destroyed* record is unreachable -- from the
    figure it was popped off. A shallow copy taken beforehand holds the same
    object, and reading ``record.fig`` on it raised ``AttributeError`` out
    of a membership test, which has to answer a bool.

    Found in review after I had reasoned the case away as impossible: the
    pop removes the record from the original, not from a copy that already
    exists.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    twin = copy.copy(fig)
    try:
        maidr.close(ax)  # FigureManager.destroy -> Maidr.destroy

        assert (twin in FigureManager.figs) is False
        assert FigureManager.figs.get(twin) is None
        with pytest.raises(KeyError):
            FigureManager.figs[twin]
        assert FigureManager.figs.pop(twin, None) is None
    finally:
        FigureManager.figs.pop(fig, None)
        plt.close(fig)


@pytest.mark.parametrize(
    "clone",
    [
        pytest.param(copy.deepcopy, id="deepcopy"),
        pytest.param(lambda fig: pickle.loads(pickle.dumps(fig)), id="pickle"),
    ],
)
def test_a_copied_figure_is_visible_to_enumeration_not_only_to_lookup(clone):
    """A record that never went through ``__setitem__`` still has to count.

    ``deepcopy`` and ``pickle`` rebuild ``__dict__`` directly, so nothing
    adds the copy to ``_seen`` -- and ``_seen`` is what backs iteration,
    ``len`` and ``clear``. The copy therefore answered ``in`` while being
    absent from ``list(figs)``, uncounted, and immune to ``clear()``: a
    mapping disagreeing with itself about what it holds.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    twin = clone(fig)
    try:
        assert twin in FigureManager.figs
        assert twin in list(FigureManager.figs)

        before = len(FigureManager.figs)
        FigureManager.figs.pop(twin)
        assert twin not in list(FigureManager.figs)
        assert len(FigureManager.figs) == before - 1
    finally:
        FigureManager.figs.pop(fig, None)
        FigureManager.figs.pop(twin, None)
        plt.close(fig)


def test_a_record_naming_another_figure_is_refused_not_quietly_kept():
    """The one write path has to uphold what every read path enforces.

    Storing a ``Maidr`` that names a different figure used to succeed, set
    the attribute, and then read back as unregistered -- a write that did
    not stick, leaving a stray attribute behind. The dict this replaced
    would have stored and returned it, so this is a behaviour change, and a
    deliberate one: the alternative is a silent disagreement discovered at
    some later lookup rather than an error at the mistake.
    """
    a, ax_a = plt.subplots()
    ax_a.bar(["a"], [1])
    b, ax_b = plt.subplots()
    ax_b.bar(["b"], [2])
    try:
        record_of_b = FigureManager.figs[b]
        with pytest.raises(ValueError, match="names a different one"):
            FigureManager.figs[a] = record_of_b

        # And a's own record is untouched by the refusal.
        assert FigureManager.figs[a].fig is a
    finally:
        for fig in (a, b):
            FigureManager.figs.pop(fig, None)
            plt.close(fig)


def test_clear_drops_every_registered_figure():
    """``clear`` is the suite's own isolation tool and nothing asserted it.

    Called from ``tests/widget/test_shiny.py``'s fixture and nowhere else,
    so a ``clear`` that silently dropped nothing would leak one test's
    figures into the next rather than fail here. It is also the method most
    exposed to the ``_seen`` bookkeeping, since it iterates and pops in the
    same pass while ``_record`` is adding to the set it walks.

    Includes a figure whose record arrived by ``deepcopy`` rather than
    through ``__setitem__``, which was invisible to ``clear`` until
    ``_record`` started keeping ``_seen`` current -- and, separately, one
    that is *never looked up*, which ``clear`` still cannot see. That gap
    is asserted rather than hidden: ``_seen`` learns of a figure only when
    its record is written or read, and a clone does neither. See
    ``_FigureRecords.clear`` for why closing it is not worth what it costs.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    other, other_ax = plt.subplots()
    other_ax.bar(["c"], [3])
    twin = copy.deepcopy(fig)
    untouched = copy.deepcopy(fig)
    try:
        # Reading `twin` is what puts it within `clear`'s reach; `untouched`
        # is deliberately not read, so the two differ only in that.
        for registered in (fig, other, twin):
            assert registered in FigureManager.figs

        FigureManager.figs.clear()

        for registered in (fig, other, twin):
            assert registered not in FigureManager.figs
        assert list(FigureManager.figs) == []
        assert len(FigureManager.figs) == 0

        assert untouched in FigureManager.figs, (
            "a clone that was never looked up is expected to survive "
            "`clear` -- if this now passes, the gap was closed and this "
            "assertion is the thing to delete"
        )
    finally:
        for f in (fig, other):
            FigureManager.figs.pop(f, None)
            plt.close(f)


def test_one_thread_cannot_enter_the_registry_while_another_is_inside(monkeypatch):
    """The registry's own lock actually excludes, rather than merely existing.

    ``figs`` is a public class attribute that reads like a dict, so
    ``if fig in FigureManager.figs`` is the natural line for a future
    contributor to write outside ``FigureManager``'s lock -- and since the
    record moved onto the figure, a lookup also updates the bookkeeping
    behind iteration, so that apparently-read-only line mutates shared
    state. ``_FigureRecords`` therefore guards itself.

    Asserted as **mutual exclusion**, which is what the lock promises, and
    with an explicit handoff rather than a crowd. The failure it prevents
    -- ``RuntimeError: Set changed size during iteration`` -- can only be
    provoked by sustained contention, and a bounded harness for it detected
    on roughly half its runs while a larger budget made it *worse*: 5 of 8
    at 0.75s against 3 of 8 at 1.0s. That is scheduler luck, not a test.

    Parking one thread inside the critical section and asking whether
    another can get in needs no luck at all.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    try:
        inside = threading.Event()
        b_finished = threading.Event()
        real_add = FigureManager.figs._seen.add
        who = threading.local()

        def parking_add(item):
            """Park the holder inside the guard -- and only the holder.

            Tagged per thread because `_seen.add` is on the enterer's path
            too (`pop` establishes ownership before deleting). A version
            without the tag parked *both* threads and passed with the guard
            removed: neither could observe the other, so there was nothing
            to detect.
            """
            if getattr(who, "tag", None) == "holder":
                inside.set()
                b_finished.wait(_HANDOFF_DEADLINE)
            return real_add(item)

        monkeypatch.setattr(FigureManager.figs._seen, "add", parking_add)
        record = FigureManager.figs[fig]

        def hold():
            who.tag = "holder"
            FigureManager.figs[fig] = record

        def enter():
            who.tag = "enterer"
            inside.wait(5)
            FigureManager.figs.pop(fig, None)
            b_finished.set()

        holder = threading.Thread(target=hold)
        enterer = threading.Thread(target=enter)
        holder.start()
        enterer.start()

        # The holder parks until the deadline because the enterer is blocked
        # on the guard; unguarded, the enterer completes immediately and the
        # holder is released early. The gap between those is the assertion.
        entered_while_held = b_finished.wait(_HANDOFF_DEADLINE / 2)

        for worker in (holder, enterer):
            worker.join(timeout=10)
            assert not worker.is_alive(), "the registry deadlocked"

        assert not entered_while_held, (
            "a second thread entered the registry while another was inside "
            "its critical section; the guard is not excluding anything"
        )
    finally:
        b_finished.set()
        FigureManager.figs.pop(fig, None)
        plt.close(fig)
