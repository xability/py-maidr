"""The per-figure render lock, and the resolution that decides its scope.

The lock's behaviour was covered from ``tests/widget/test_shiny.py`` while
it lived inside the Shiny integration. It now serves every threaded door,
so the unit tests move here with it; the Shiny-specific ones (that a
render actually takes it, that two renders do not overlap) stay there.
"""

from __future__ import annotations

import gc
import weakref

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from maidr.util.figure_lock import figure_lock, resolve_figure  # noqa: E402


def test_each_figure_gets_its_own_lock_and_keeps_it():
    """Per figure, not process-wide, and stable across calls.

    A single shared lock would serialise unrelated sessions and give back
    most of what rendering on a thread buys, since ``savefig`` on
    *distinct* figures is safe in parallel. A lock that differed per call
    would guard nothing at all.
    """
    first, _ = plt.subplots()
    second, _ = plt.subplots()
    try:
        assert figure_lock(first) is figure_lock(first), "must be stable"
        assert figure_lock(first) is not figure_lock(second), "must be per figure"
    finally:
        plt.close(first)
        plt.close(second)


def test_an_unresolvable_figure_gets_a_fresh_lock_rather_than_a_shared_one():
    """Sharing one lock among things we cannot tell apart invites a deadlock.

    The render is safe on its own -- only the lock's scope is lost -- so
    the fallback hands back an unshared lock rather than a sentinel-keyed
    one.
    """
    assert figure_lock(None) is not figure_lock(None)


def test_the_lock_does_not_keep_a_closed_figure_alive():
    """The map is weak-keyed, so it adds no retention of its own (#498).

    Worth pinning because a strong map keyed by figure is exactly the
    shape that kept every registered figure alive for the life of the
    process (#456), and this one is keyed the same way.
    """
    # A bare `Figure`, deliberately not `plt.subplots()`, so that nothing
    # but the lock map can be the reason this passes or fails.
    figure = Figure()
    figure_lock(figure)
    ref = weakref.ref(figure)

    del figure
    gc.collect()

    assert ref() is None, "the lock map is keeping the figure alive"


@pytest.mark.parametrize(
    "shape",
    ["axes", "figure", "list of artists", "no argument"],
    ids=["axes", "figure", "list", "current"],
)
def test_every_way_of_naming_one_chart_takes_the_same_lock(shape):
    """The lock is only exclusion if two names for one figure agree on it.

    ``maidr.render`` accepts an ``Axes``, a ``Figure``, a list of artists
    and ``None`` for the current figure, and renders the same chart from
    every one of them. Resolution that answered ``None`` for some of those
    would hand back a *fresh* lock -- so two renders of one figure, named
    differently, would not exclude each other and would race on
    ``fig.dpi`` exactly as if there were no lock.

    ``Figure`` and ``None`` are not hypothetical: both resolved to no
    figure before the resolution moved here, so a Shiny render function
    returning ``fig`` rather than ``ax`` was unsynchronised.
    """
    figure, axes = plt.subplots()
    axes.bar(["a", "b"], [1, 2])
    named = {
        "axes": axes,
        "figure": figure,
        "list of artists": [axes],
        "no argument": None,
    }[shape]
    try:
        assert resolve_figure(named) is figure, "must name the same figure"
        assert figure_lock(resolve_figure(named)) is figure_lock(figure), (
            "must take the same lock as the figure itself"
        )
    finally:
        plt.close(figure)


def test_a_value_naming_no_figure_resolves_to_none():
    """The fallback branch, from both directions.

    A value ``get_axes`` does not understand returns ``None``; an empty
    container makes it raise. Both mean "nothing to lock", and the
    distinction matters only in that the second reaches the ``except``.
    """
    assert resolve_figure("not a plot") is None
    assert resolve_figure([]) is None


def test_an_unexpected_resolver_failure_is_logged_not_swallowed(monkeypatch, caplog):
    """A bug in ``get_axes`` must not vanish into "lock scope lost".

    The catch sits immediately before an unsynchronised render, so a real
    failure there is worth a record. It was a bare ``except Exception``
    with no logging until review of #504.
    """
    import logging

    from maidr.core.figure_manager import FigureManager

    monkeypatch.setattr(
        FigureManager,
        "get_axes",
        staticmethod(lambda value: (_ for _ in ()).throw(AttributeError("boom"))),
    )
    with caplog.at_level(logging.DEBUG, logger="maidr.util.figure_lock"):
        assert resolve_figure(object()) is None

    assert any("without a shared lock" in record.message for record in caplog.records)
