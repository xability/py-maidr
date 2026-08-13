"""Resolving the CDN version must not stall an event loop.

``maidr.render()`` is synchronous, and Shiny calls it from
``render_maidr.render()``, which is ``async``. Under the default the first
figure in an app therefore performed a blocking ``urlopen`` **on the event
loop** -- up to ``MAIDR_CDN_TIMEOUT``, and that budget is only approximate
because ``urlopen``'s timeout applies per socket operation and does not
reliably cover ``getaddrinfo``. Every concurrent session queued behind it on
``_fetch_lock`` (#296).

The fix is to answer from the bundled version instead when a lookup would have
to be made on a loop. What these pin is that the request is not made -- asserted
on the call count rather than on elapsed time, because a timing assertion on CI
measures the runner's load as much as the code.

They also pin the two things that keep the answer from being merely
context-dependent: an explicit pin still wins, and a lookup that has already
completed anywhere in the process is used, so an app that resolves once from
synchronous code at start-up serves the resolved version from then on.
"""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from maidr.util import dependencies


class _FakeResponse(io.BytesIO):
    """Minimal ``urlopen`` stand-in supporting the ``with`` protocol."""

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


@pytest.fixture
def requests(monkeypatch):
    """Record every registry request, answering each with version 9.9.9.

    Yields the list of requested URLs, so a test can say "no request was
    made" as a fact about the network rather than about the clock.
    """
    monkeypatch.delenv(dependencies.CDN_VERSION_ENV_VAR, raising=False)
    dependencies.set_cdn_version(None)
    dependencies.reset_cdn_version_cache()

    calls: list[str] = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return _FakeResponse(json.dumps({"version": "9.9.9"}).encode("utf-8"))

    monkeypatch.setattr(dependencies, "urlopen", fake_urlopen)
    yield calls

    dependencies.set_cdn_version(None)
    dependencies.reset_cdn_version_cache()


def in_loop(call):
    """Run ``call`` on a fresh event loop and return its result."""

    async def main():
        return call()

    return asyncio.run(main())


def test_a_render_on_an_event_loop_makes_no_request(requests) -> None:
    """The reported bug: the loop must not be made to wait.

    Asserting the request count rather than the duration. A stalled loop is
    what the user experiences, but the *cause* is the round trip, and that is
    the thing a test can state without measuring a shared CI runner.
    """
    version = in_loop(dependencies.get_cdn_version)

    assert requests == []
    assert version == dependencies.maidr_js_version()


def test_a_synchronous_render_still_resolves(requests) -> None:
    """The control. Nothing outside an event loop changes."""
    version = dependencies.get_cdn_version()

    assert len(requests) == 1
    assert version == "9.9.9"


def test_the_version_emitted_on_a_loop_is_concrete(requests) -> None:
    """Bundled, not ``latest``.

    ``@latest`` is the mutable dist-tag this whole module exists to stop
    emitting -- jsDelivr serves it with a seven-day ``max-age``, so a browser
    can replay a week-old bundle. Declining to resolve must not quietly
    reintroduce it.
    """
    url = in_loop(dependencies.maidr_js_cdn_url)

    assert requests == []
    assert f"maidr@{dependencies.LATEST_TAG}/" not in url
    assert f"maidr@{dependencies.maidr_js_version()}/" in url


def test_an_explicit_pin_still_wins_on_a_loop(requests) -> None:
    """A pin is the caller's own answer and costs no request either way."""
    dependencies.set_cdn_version("3.74.0")

    assert in_loop(dependencies.get_cdn_version) == "3.74.0"
    assert requests == []


def test_a_completed_lookup_is_used_on_a_loop(requests) -> None:
    """Resolve once from synchronous code and every async render benefits.

    This is what keeps the behaviour from being context-dependent for the
    life of the process: after any resolution anywhere, the loop and the
    main thread agree. It is also the supported way for an async app to
    serve a release newer than its wheel.
    """
    assert dependencies.get_cdn_version() == "9.9.9"

    assert in_loop(dependencies.get_cdn_version) == "9.9.9"
    assert len(requests) == 1


def test_a_cached_failure_is_not_retried_on_a_loop(monkeypatch, requests) -> None:
    """A failed lookup stays failed, and stays cheap.

    An offline notebook must not stall on a doomed request for every figure,
    and the loop must not either. The answer is ``latest`` here rather than
    the bundled version, which is what a failed lookup has always produced --
    this path is unchanged and is pinned so it stays that way.
    """
    monkeypatch.setattr(dependencies, "_fetch_latest_version", lambda budget: None)

    assert dependencies.get_cdn_version() == dependencies.LATEST_TAG

    assert in_loop(dependencies.get_cdn_version) == dependencies.LATEST_TAG
    assert requests == []


def test_two_concurrent_renders_on_one_loop_both_return(requests) -> None:
    """No pile-up, because there is nothing to pile up behind.

    Concurrent first-renders used to queue on ``_fetch_lock`` while the first
    of them made the request, so a slow resolver cost every session the same
    stall rather than costing one of them.
    """

    async def main():
        return await asyncio.gather(
            asyncio.to_thread(lambda: None),
            *[asyncio.sleep(0, dependencies.get_cdn_version()) for _ in range(4)],
        )

    results = asyncio.run(main())

    assert requests == []
    assert set(results[1:]) == {dependencies.maidr_js_version()}


def test_bundled_cdn_url_still_prefers_a_pin_then_a_lookup(requests) -> None:
    """The offline URL builder shares the fallback order, so it cannot drift.

    Both it and `get_cdn_version`'s event-loop branch answer "which version,
    without asking?" and they used to spell that out separately. When they
    disagreed, a pinned session emitted the bundled version here while every
    iframe emitted the pinned one, and one page loaded two builds of
    ``maidr.js``.
    """
    dependencies.set_cdn_version("3.74.0")
    assert "maidr@3.74.0/" in dependencies.bundled_cdn_url(
        dependencies.MAIDR_JS_FILENAME
    )

    dependencies.set_cdn_version(None)
    assert dependencies.get_cdn_version() == "9.9.9"
    assert "maidr@9.9.9/" in dependencies.bundled_cdn_url(
        dependencies.MAIDR_JS_FILENAME
    )

    dependencies.reset_cdn_version_cache()
    assert f"maidr@{dependencies.maidr_js_version()}/" in dependencies.bundled_cdn_url(
        dependencies.MAIDR_JS_FILENAME
    )
