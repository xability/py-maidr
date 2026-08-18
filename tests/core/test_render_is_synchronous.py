"""A benchmark for the claim ``docs/index.qmd`` makes about the event loop.

Skipped by default: it is a timing measurement, so it is too machine- and
load-dependent to gate CI on. Run it deliberately when the number in the
docs needs re-checking::

    uv run pytest tests/core/test_render_is_synchronous.py --run-benchmark

What it measures is the longest the event loop goes without running while
one chart renders. That is the question a Shiny deployment actually has --
"how long does everyone else wait" -- and it is measurable, unlike
counting wakeups over a window, which cannot tell a blocked loop from a
slow one.

Getting that wrong is the reason this file is careful about it. An earlier
version started its ticker before the measurement window and counted the
wakeups from the settling period as though they had happened during
rendering. It reported a healthy-looking number for a loop that in fact
never ran once, and would have reported the same number had rendering been
an outright freeze -- which it is.
"""

from __future__ import annotations

import asyncio
import time

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402

#: How long the ticker settles before anything is measured.
_SETTLE = 0.15

#: Wakeup interval the ticker asks for. The loop cannot beat this, so it
#: also sets the resolution of the gaps observed.
_TICK = 0.001

#: A gap this much larger than the tick interval is the loop being held,
#: not scheduler jitter. Deliberately loose: the render blocks for tens of
#: milliseconds, so anything near the tick interval is noise either way.
_BLOCKED_MS = 10.0


def _render_once() -> None:
    """Render one trivial chart and drop it."""
    fig, ax = plt.subplots()
    try:
        ax.bar(["a", "b"], [1, 2])
        maidr.render(ax, use_cdn=True)
    finally:
        plt.close(fig)


async def _longest_gap_around_one_render() -> tuple[float, float]:
    """Return the loop's longest idle gap, before and during one render.

    Both in seconds. The baseline is what the loop manages with nothing in
    its way, which is what makes the second number mean anything.
    """
    gaps: list[float] = []
    stop = asyncio.Event()

    async def ticker() -> None:
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(_TICK)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    task = asyncio.create_task(ticker())
    await asyncio.sleep(_SETTLE)

    baseline = max(gaps)
    gaps.clear()

    _render_once()
    await asyncio.sleep(_SETTLE)

    stop.set()
    await task
    return baseline, max(gaps)


@pytest.mark.benchmark
def test_one_render_blocks_the_event_loop(monkeypatch) -> None:
    """A render holds the loop of whoever calls it on one.

    ``maidr.render()`` is synchronous and never awaits, so nothing can
    preempt it: for as long as it runs, that loop does not run at all.
    Asserted as "much larger than the baseline" rather than a fixed
    millisecond count, which would fail on a loaded CI box while telling
    nobody anything.

    Note what this does **not** say any more. It used to add "every other
    session on that worker is stopped", which was true when ``render_maidr``
    called this on the event loop. It no longer does -- the render is handed
    to a worker thread -- so a Shiny app does not pay this, and measured
    through the renderer the loop gap is 12.5 ms rather than 609 ms. What is
    asserted here is the property of ``maidr.render()`` that makes moving it
    off the loop necessary, not a description of what a Shiny app does.
    """
    # `_render_once` renders with `use_cdn=True`, and building that URL
    # would resolve the published version over the network. Pinning skips
    # the lookup while leaving the CPU-bound work being measured alone.
    # `tests/conftest.py`'s autouse fixture already pins this and stubs
    # `urlopen`, so the suite is safe without it -- repeated here because a
    # benchmark meant to be run deliberately, often in a sandbox, should
    # not be one global fixture away from stalling on MAIDR_CDN_TIMEOUT.
    monkeypatch.setenv("MAIDR_CDN_VERSION", "latest")

    # Warm up: the first render pays for imports, the font cache and the
    # matplotlib backend, and is worth roughly thirty steady-state ones.
    for _ in range(5):
        _render_once()

    baseline, blocked = asyncio.run(_longest_gap_around_one_render())

    assert blocked * 1000 > _BLOCKED_MS, (
        f"one render held the loop for only {blocked * 1000:.1f} ms; if "
        "`maidr.render` itself has stopped blocking its caller, both this "
        "file and the async callout in docs/index.qmd need updating"
    )
    assert blocked > baseline * 5, (
        f"the render ({blocked * 1000:.1f} ms) is not clearly worse than "
        f"the loop's own jitter ({baseline * 1000:.1f} ms)"
    )
    print(
        f"\nlongest loop gap: {baseline * 1000:.1f} ms idle, "
        f"{blocked * 1000:.1f} ms around one render"
    )
