"""Every caller renders one figure at a time, not only the two doors.

``savefig`` writes ``fig.dpi`` for its duration and restores it, so two
renders of one figure at once race on that attribute and the loser draws
its whole chart at the other call's dpi -- a complete, well-formed SVG at
the wrong scale, raising nothing (#454).

The Shiny and Streamlit integrations each held a lock against that until
#532. This covers the callers that never went near a widget: a threaded
Flask app -- ``Environment.is_flask`` makes it a supported embedding, and
Werkzeug serves threaded -- or anything rendering from a thread pool.
"""

from __future__ import annotations

import re
import threading

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402

#: Attributes that differ between two renders of the same chart by design --
#: fresh uuids per layer, and the timestamp matplotlib stamps into the SVG.
_VOLATILE_IN_SVG = re.compile(
    r'(\bid="[^"]*"|url\(#[^)]*\)|<dc:date>[^<]*</dc:date>'
    r'|xlink:href="#[^"]*"|maidr="[^"]*")'
)


def _render_from_threads(name, workers=6):
    """Render ``name`` from ``workers`` threads at once, normalised."""
    outputs: list[str] = []
    failures: list[Exception] = []
    # One constant for the barrier and the thread count, because they must
    # agree: a barrier expecting more arrivals than there are threads waits
    # forever (#506).
    start = threading.Barrier(workers)

    def render_once() -> None:
        try:
            start.wait(timeout=30)
            outputs.append(
                _VOLATILE_IN_SVG.sub("", str(maidr.render(name, use_cdn=True)))
            )
        except Exception as error:  # noqa: BLE001 - reported after the join
            failures.append(error)

    threads = [threading.Thread(target=render_once, daemon=True) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        # Longer than the barrier's own deadline, so a thread still
        # legitimately waiting there is not reported as a deadlocked render.
        thread.join(timeout=60)
        assert not thread.is_alive(), "a render deadlocked on the lock"

    assert not failures, failures
    assert len(outputs) == workers
    return outputs


@pytest.mark.parametrize("names", ["axes", "figure"], ids=["axes", "figure"])
def test_concurrent_renders_through_the_api_agree(names):
    """``maidr.render`` serialises by itself, with no integration involved.

    Measured before the lock moved here, six threads on one figure through
    ``maidr.render`` directly: 1 of 5 trials came back with two distinct
    outputs. Nothing raised in any of them.

    Parametrised over what names the chart because the two used to take
    different paths to the lock -- a ``Figure`` resolved to a list of axes
    and, before #531, to no lock at all. Locking by the figure the ``Maidr``
    instance already holds removes the resolution step rather than fixing
    it, so both names now reach one lock by construction; this pins that
    they still do.

    The barrier synchronises the *start*, not the duration. On a runner
    slow enough that each render finishes before the next thread is
    scheduled this would pass with no lock at all -- a false negative
    rather than CI noise. Measured 10 of 10 detections with the lock
    removed.
    """
    fig, ax = plt.subplots()
    ax.bar([str(i) for i in range(30)], list(range(30)))
    try:
        outputs = _render_from_threads(ax if names == "axes" else fig)
    finally:
        plt.close(fig)

    assert len(set(outputs)) == 1, (
        "concurrent renders of one figure disagreed; one drew the chart at "
        "another render's dpi, which produces a valid SVG at the wrong "
        "scale rather than an error"
    )


def test_two_figures_still_render_in_parallel():
    """The lock is per figure, so unrelated renders are not serialised.

    A process-wide lock would pass the test above and quietly throw away
    the parallelism that rendering on a thread exists for. Asserted by
    overlap rather than by timing: each render reports when it is inside
    the lock, and two figures must be inside at once.
    """
    first, first_ax = plt.subplots()
    first_ax.bar(["a"], [1])
    second, second_ax = plt.subplots()
    second_ax.bar(["b"], [2])

    from maidr.core.figure_manager import FigureManager

    inside = threading.Barrier(2)
    overlapped = threading.Event()
    original = type(FigureManager.get_maidr(first))._build_html_tag

    def reporting_build(self, *args, **kwargs):
        try:
            # Both renders must be inside the lock at once, or this times
            # out -- which is the failure this test is looking for.
            inside.wait(timeout=5)
            overlapped.set()
        except threading.BrokenBarrierError:
            pass
        return original(self, *args, **kwargs)

    type(FigureManager.get_maidr(first))._build_html_tag = reporting_build
    try:
        threads = [
            threading.Thread(
                target=lambda axes=axes: maidr.render(axes, use_cdn=True), daemon=True
            )
            for axes in (first_ax, second_ax)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            assert not thread.is_alive(), "a render deadlocked"
    finally:
        type(FigureManager.get_maidr(first))._build_html_tag = original
        plt.close(first)
        plt.close(second)

    assert overlapped.is_set(), (
        "two distinct figures did not render at the same time; the lock is "
        "serialising more than one figure's worth of work"
    )
