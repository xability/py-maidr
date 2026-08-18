"""Why a version lookup failed, so a monitor can tell a fault from an outage.

The scheduled freshness check passes when the published version cannot be
resolved, because a resolver hiccup is not a drift signal and failing on one
would train maintainers to ignore the job. That is right for a hiccup and
wrong for a persistent failure: the job then stays green forever while
checking nothing, and a green check that verifies nothing is worse than a red
one, because it is indistinguishable from a real pass (#298).

What separates the two is *how* it failed. An endpoint that never answered is
the network, which nobody reading the job can fix. An endpoint that answered
with something py-maidr could not use is py-maidr being wrong about its shape
-- an API that moved or changed its payload -- which is the long-lived cause
the job most needs to catch, because it will not fix itself.

``_fetch_latest_version`` collapses both into ``None``, which is the right
answer for a render. These pin the second channel that keeps the distinction.
"""

from __future__ import annotations

import io
import json
from urllib.error import HTTPError

import pytest

from maidr.util import bundle_freshness as freshness
from maidr.util import cdn
from maidr.util import dependencies


class _FakeResponse(io.BytesIO):
    """Minimal ``urlopen`` stand-in supporting the ``with`` protocol."""

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


ENDPOINT_COUNT = len(cdn._RESOLVER_ENDPOINTS)


@pytest.fixture
def clean(monkeypatch):
    """No pin, no cached lookup, no leftover outcome."""
    monkeypatch.delenv(cdn.CDN_VERSION_ENV_VAR, raising=False)
    cdn.set_cdn_version(None)
    cdn.reset_cdn_version_cache()
    yield
    cdn.set_cdn_version(None)
    cdn.reset_cdn_version_cache()


def answer_with(monkeypatch, responder) -> None:
    """Make every resolver request go through ``responder``."""
    monkeypatch.setattr(cdn, "urlopen", responder)


def json_body(payload: dict):
    """A responder that returns ``payload`` as JSON from every endpoint."""
    return lambda request, timeout=None: _FakeResponse(
        json.dumps(payload).encode("utf-8")
    )


def test_nothing_is_reported_before_a_lookup_runs(clean) -> None:
    """``None`` means "not tried", which is not "tried and reached nothing".

    A pinned or offline session never resolves. Reading an empty outcome as
    a verdict there would report every endpoint as fine, on no evidence.
    """
    assert freshness.resolver_outcome() is None


def test_an_outage_is_reported_as_unreachable(monkeypatch, clean) -> None:
    """A timeout says nothing about whether this code is right."""
    answer_with(
        monkeypatch,
        lambda request, timeout=None: (_ for _ in ()).throw(TimeoutError()),
    )

    assert cdn._fetch_latest_version(3.0) is None

    outcome = freshness.resolver_outcome()
    assert len(outcome.unreachable) == ENDPOINT_COUNT
    assert outcome.answered_badly == ()


def test_an_http_error_is_an_answer(monkeypatch, clean) -> None:
    """404 is the endpoint telling us the path moved.

    Reached, and useless -- a different fact from not having reached it,
    and the one that will still be true next week.
    """

    def not_found(request, timeout=None):
        raise HTTPError(request.full_url, 404, "Not Found", {}, None)

    answer_with(monkeypatch, not_found)

    assert cdn._fetch_latest_version(3.0) is None

    outcome = freshness.resolver_outcome()
    assert len(outcome.answered_badly) == ENDPOINT_COUNT
    assert outcome.unreachable == ()


def test_a_payload_without_the_key_is_an_answer(monkeypatch, clean) -> None:
    """An endpoint that changed shape looks exactly like this.

    The response is a perfectly good JSON document. It simply does not say
    what this code reads, which is the failure the whole distinction exists
    to surface.
    """
    answer_with(monkeypatch, json_body({"something_else": "4.2.0"}))

    assert cdn._fetch_latest_version(3.0) is None
    assert len(freshness.resolver_outcome().answered_badly) == ENDPOINT_COUNT


def test_a_value_that_is_not_a_version_is_an_answer(monkeypatch, clean) -> None:
    """The key is there and holds something unusable."""
    answer_with(
        monkeypatch,
        lambda request, timeout=None: _FakeResponse(
            json.dumps({"version": "not-a-version", "latest": "also-not"}).encode()
        ),
    )

    assert cdn._fetch_latest_version(3.0) is None
    assert len(freshness.resolver_outcome().answered_badly) == ENDPOINT_COUNT


def test_a_body_that_will_not_parse_is_an_answer(monkeypatch, clean) -> None:
    """Bytes arrived. That they were HTML is not the network's fault."""
    answer_with(
        monkeypatch,
        lambda request, timeout=None: _FakeResponse(b"<html>proxy error</html>"),
    )

    assert cdn._fetch_latest_version(3.0) is None
    assert len(freshness.resolver_outcome().answered_badly) == ENDPOINT_COUNT


def test_an_unrecognised_failure_counts_as_unreachable(monkeypatch, clean) -> None:
    """The safe direction for a failure this code did not anticipate.

    `pytest-socket` raises `SocketBlockedError`, which is not an `OSError`.
    Calling an unknown failure "this code is wrong" would redden a
    scheduled check over a sandbox setting nobody can act on.
    """

    class Blocked(Exception):
        pass

    answer_with(
        monkeypatch,
        lambda request, timeout=None: (_ for _ in ()).throw(Blocked()),
    )

    assert cdn._fetch_latest_version(3.0) is None

    outcome = freshness.resolver_outcome()
    assert len(outcome.unreachable) == ENDPOINT_COUNT
    assert outcome.answered_badly == ()


def test_a_success_reports_no_failures(monkeypatch, clean) -> None:
    """The common case names nobody.

    The first endpoint answers, so the second is never asked -- and an
    endpoint that was not asked belongs in neither bucket.
    """
    answer_with(monkeypatch, json_body({"version": "4.2.0"}))

    assert cdn._fetch_latest_version(3.0) == "4.2.0"

    outcome = freshness.resolver_outcome()
    assert outcome == cdn.ResolverOutcome("4.2.0", (), ())


def test_a_fallback_records_the_endpoint_it_fell_back_from(
    monkeypatch, clean
) -> None:
    """Resolution succeeded, and one endpoint is still down.

    Worth keeping rather than discarding on success: an endpoint failing
    every week while the backup covers for it is exactly the drift that
    goes unnoticed until the backup fails too.
    """
    calls = {"n": 0}

    def first_down(request, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError()
        return _FakeResponse(json.dumps({"latest": "9.9.9"}).encode())

    answer_with(monkeypatch, first_down)

    assert cdn._fetch_latest_version(3.0) == "9.9.9"

    outcome = freshness.resolver_outcome()
    assert outcome.resolved == "9.9.9"
    assert len(outcome.unreachable) == 1
    assert outcome.answered_badly == ()


def test_a_reset_discards_the_verdict_with_the_lookup(monkeypatch, clean) -> None:
    """A stale outcome read as the current one is a wrong answer.

    Without this, a monitor that re-resolved after a failure would still
    see the failure, and one that re-resolved after a success would still
    see the success.
    """

    def not_found(request, timeout=None):
        raise HTTPError(request.full_url, 404, "Not Found", {}, None)

    answer_with(monkeypatch, not_found)
    cdn._fetch_latest_version(3.0)
    assert freshness.resolver_outcome().answered_badly

    cdn.reset_cdn_version_cache()

    assert freshness.resolver_outcome() is None


def test_the_render_path_is_unchanged_by_any_of_it(monkeypatch, clean) -> None:
    """A failed lookup still degrades rather than raising.

    The reason the outcome is a separate accessor rather than a widened
    ``BundleStatus``: nothing on the render path has to know about it, and
    the contract that a lookup failure cannot break a chart still holds.
    """
    answer_with(
        monkeypatch,
        lambda request, timeout=None: (_ for _ in ()).throw(TimeoutError()),
    )

    assert cdn.get_cdn_version() == dependencies.maidr_js_version()
    assert freshness.bundle_status(resolve=False).published is None
