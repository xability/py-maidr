"""The per-figure render lock.

The lock's behaviour was covered from ``tests/widget/test_shiny.py`` while
it lived inside the Shiny integration, and moved here when it became
shared (#531). Since #532 the only thing that takes it is
``Maidr._create_html_tag``, so that it covers every caller rather than the
two doors this package ships; ``tests/core/test_render_serialises.py``
covers that, and the per-door concurrency tests still assert the
consequence through each integration.
"""

from __future__ import annotations

import gc
import weakref

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from maidr.util.figure_lock import figure_lock  # noqa: E402


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
