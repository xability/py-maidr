import threading

import matplotlib.pyplot as plt
import pytest
import seaborn as sns

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
        meaningful. Unguarded, B is free to complete both of its appends
        while A is parked here, and A's id then lands behind B's -- the
        misalignment. Guarded, B cannot enter the critical section at all,
        so this simply times out and the order is preserved. Either way the
        test finishes.
        """
        if getattr(who, "tag", None) == "A":
            first_appended.set()
            second_done.wait(1.5)
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

    threads = [threading.Thread(target=register_a), threading.Thread(target=register_b)]
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
