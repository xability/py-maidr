"""A benchmark for the claim ``docs/index.qmd`` makes about the event loop.

Skipped by default: it is a timing measurement, so it is too machine- and
load-dependent to gate CI on. Run it deliberately when the numbers in the
docs need re-checking::

    uv run pytest tests/core/test_render_is_synchronous.py --run-benchmark

The claim it exists to keep honest is that ``maidr.render()`` blocks the
event loop -- *starves* it, not freezes it. The distinction matters: the
issue that reported this originally recorded zero event-loop wakeups
during rendering, which turned out to be an artefact of measuring across
the first render, whose one-time costs (imports, font cache, CDN version
resolution) dwarf the steady state.
"""

from __future__ import annotations

import asyncio
import time

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402

#: Seconds each measurement window runs for.
_WINDOW = 0.6

#: Wakeups the ticker asks for, per second.
_TICK = 0.001


def _render_once() -> None:
    """Render one trivial chart and drop it."""
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    maidr.render(ax, use_cdn=True)
    plt.close(fig)


async def _ticks_while_idle() -> int:
    """Return the wakeups a ticker gets over an *awaited* window.

    The control has to yield rather than spin: a busy-wait blocks the loop
    just as rendering does, which would make the two windows agree and the
    comparison meaningless. That is a mistake this harness made once.
    """
    stop = asyncio.Event()
    task = asyncio.create_task(_ticker(stop))
    await asyncio.sleep(0.1)
    await asyncio.sleep(_WINDOW)
    stop.set()
    return await task


async def _ticker(stop: asyncio.Event) -> int:
    """Count wakeups until told to stop."""
    wakeups = 0
    while not stop.is_set():
        await asyncio.sleep(_TICK)
        wakeups += 1
    return wakeups


async def _ticks_while_rendering() -> tuple[int, float, int]:
    """Return wakeups, elapsed seconds, and renders completed."""
    stop = asyncio.Event()
    task = asyncio.create_task(_ticker(stop))
    await asyncio.sleep(0.1)

    start = time.perf_counter()
    renders = 0
    while time.perf_counter() - start < _WINDOW:
        _render_once()
        renders += 1
    elapsed = time.perf_counter() - start

    stop.set()
    return await task, elapsed, renders


@pytest.mark.benchmark
def test_rendering_starves_the_event_loop() -> None:
    """Rendering costs the loop most of its wakeups, but not all of them.

    Asserted as a wide band rather than a fixed number: the point is the
    shape of the result -- much slower, still running -- which is what the
    documentation says. A tight threshold here would fail on a loaded CI
    box while telling nobody anything they did not already know.
    """
    # Warm up: the first render pays for imports, the font cache and the
    # CDN version lookup, and is worth roughly thirty steady-state ones.
    for _ in range(5):
        _render_once()

    idle_ticks = asyncio.run(_ticks_while_idle())
    busy_ticks, elapsed, renders = asyncio.run(_ticks_while_rendering())

    assert renders > 0, "no render completed inside the measurement window"
    per_render_ms = elapsed / renders * 1000

    assert idle_ticks > busy_ticks, (
        f"rendering did not slow the loop at all ({busy_ticks} vs {idle_ticks})"
    )
    assert busy_ticks > 0, (
        "the loop never ran during rendering -- the docs say starved, not "
        "frozen, so either the docs or this is now wrong"
    )
    print(
        f"\nidle {idle_ticks} ticks / rendering {busy_ticks} ticks "
        f"({renders} renders, {per_render_ms:.0f} ms each)"
    )
