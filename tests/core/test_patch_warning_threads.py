"""Concurrent draws must not leave a filter behind.

``_draw_quietly`` suppresses matplotlib's warnings with
``warnings.catch_warnings()``, which saves the *global* filter list on entry
and restores it on exit. Two threads drawing at once do not merely race on
that list -- they corrupt it, because the restores nest wrongly::

    A enters, saving S0          filters = ignore + S0
    B enters, saving S1          S1 already contains A's ignore
    A exits,  restoring S0       filters = S0
    B exits,  restoring S1       filters = ignore + S0

B puts back a snapshot it took while A was suppressing, so a process-wide
``ignore`` outlives every draw -- which is precisely the leak #327 removed,
reintroduced under concurrency and this time permanently.

Serialising the suppression is what makes the save and restore pair up, and
that is what these tests pin. They are about the *filter list*, not about
drawing: the work under the lock is a plain sleep rather than a plot, so the
failure is attributable to the suppression rather than to matplotlib's own
thread-safety, and the test does not depend on concurrent plotting working.
"""

from __future__ import annotations

import copy
import threading
import time
import warnings

import pytest

from maidr.patch.common import _draw_quietly

THREADS = 8
DRAWS = 40


def _slow_draw() -> str:
    """Stand in for a plotting call long enough for the calls to overlap."""
    time.sleep(0.002)
    return "drawn"


def _draw_repeatedly() -> None:
    for _ in range(DRAWS):
        _draw_quietly(_slow_draw, (), {})


def _run_concurrently(target) -> None:
    threads = [threading.Thread(target=target) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_concurrent_draws_leave_the_filter_list_as_they_found_it():
    # Without the lock this leaves one ('ignore', None, Warning, None, 0)
    # behind at position 0 -- a process-wide "swallow everything" that no
    # later draw removes.
    before = copy.copy(warnings.filters)

    _run_concurrently(_draw_repeatedly)

    assert warnings.filters == before


def test_a_warning_after_concurrent_draws_still_reaches_the_caller():
    # The consequence of the leak, stated the way a user meets it: a warning
    # raised long after every draw has finished, and nowhere near a figure.
    # No `simplefilter` here -- the recorder must inherit whatever the draws
    # left installed, which is the whole point.
    _run_concurrently(_draw_repeatedly)

    with warnings.catch_warnings(record=True) as caught:
        warnings.warn("heard after the threads", UserWarning)

    assert [str(w.message) for w in caught] == ["heard after the threads"]


def test_the_suppression_still_works_under_concurrency():
    # Serialising must not cost the property the helper exists for.
    heard: list[str] = []

    def draw_and_warn() -> None:
        for _ in range(DRAWS):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                _draw_quietly(_warn_then_draw, (), {})
            heard.extend(str(w.message) for w in caught)

    def _warn_then_draw() -> str:
        warnings.warn("from inside the draw", UserWarning)
        return _slow_draw()

    _run_concurrently(draw_and_warn)

    assert heard == []


def test_a_nested_draw_does_not_deadlock():
    # `regplot.patched_plot` wraps `Axes.plot`, which `lineplot.line` wraps
    # too, so one draw enters the helper twice on the same thread. A plain
    # Lock would deadlock here; the RLock is why it does not.
    def outer() -> str:
        return _draw_quietly(lambda: "inner", (), {})

    finished = []

    def run() -> None:
        finished.append(_draw_quietly(outer, (), {}))

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=10)

    assert not thread.is_alive(), "nested _draw_quietly deadlocked"
    assert finished == ["inner"]


@pytest.mark.parametrize("threads", [2, THREADS])
def test_the_return_value_survives_concurrency(threads: int):
    # Serialising changes when a draw runs, never what it returns.
    results: list[str] = []
    lock = threading.Lock()

    def collect() -> None:
        for _ in range(DRAWS):
            value = _draw_quietly(_slow_draw, (), {})
            with lock:
                results.append(value)

    workers = [threading.Thread(target=collect) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert results == ["drawn"] * (threads * DRAWS)
