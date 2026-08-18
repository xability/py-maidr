from __future__ import annotations

import pytest
from matplotlib import pyplot as plt

from maidr.core.enum.plot_type import PlotType
from maidr.core.enum.library import Library
from maidr.util import bundle_freshness as freshness
from maidr.util import dependencies
from maidr.util import warn as warn_module
from tests.fixture.matplotlib_factory import MatplotlibFactory
from tests.fixture.seaborn_factory import SeabornFactory


@pytest.fixture(autouse=True)
def offline_cdn_version(monkeypatch):
    """Keep CDN URL construction off the network for the whole suite.

    ``MAIDR_CDN_VERSION=latest`` short-circuits the ``latest`` dist-tag
    lookup, so rendering tests neither hit jsDelivr/npm nor depend on
    whatever version happens to be published when CI runs.  Tests that
    exercise resolution itself override this explicitly.

    Also clears the deduplication state behind the one-shot warnings, so
    a warning raised by one test cannot suppress the same warning in the
    next.
    """
    monkeypatch.setenv(dependencies.CDN_VERSION_ENV_VAR, dependencies.LATEST_TAG)
    monkeypatch.setattr(freshness, "_bundle_warned", set())
    monkeypatch.setattr(warn_module, "_warned_keys", set())

    # Default-deny the network rather than relying on the pin above.
    # ``bundle_status()`` deliberately ignores pins when resolving the
    # published version, so the env var alone no longer keeps every path
    # offline — without this, a test that resolves without stubbing would
    # quietly reach jsDelivr and depend on whatever is published today.
    # Tests that want a resolution replace this with their own stub.
    def _no_network(*_args, **_kwargs):
        raise OSError("network disabled in tests; stub dependencies.urlopen")

    monkeypatch.setattr(dependencies, "urlopen", _no_network)
    dependencies.set_cdn_version(None)
    yield
    dependencies.set_cdn_version(None)


# setup and teardown
@pytest.fixture
def plot_fixture():
    factories = {
        Library.MATPLOTLIB: MatplotlibFactory(),
        Library.SEABORN: SeabornFactory(),
    }

    def create_plot(lib: Library, plot_type: PlotType | list[PlotType]):
        if lib not in factories:
            raise ValueError(f"Unsupported library: {lib}")
        if not isinstance(plot_type, list):
            plot_type = [plot_type]

        factory = factories[lib]
        with factory.create_plot(plot_type) as plot:
            return plot

    return create_plot


@pytest.fixture
def forbid_network():
    """Assert the test made no version-lookup request.

    Yields the list of attempted URLs and fails at teardown if it is not
    empty.

    Recording rather than raising is deliberate.  ``_fetch_latest_version``
    catches ``Exception`` on purpose — a lookup failure must degrade to
    the ``@latest`` URL rather than break rendering — so an
    ``AssertionError`` raised from a stubbed ``urlopen`` is swallowed
    there and the probe passes whether or not the call happened.  Several
    of these probes were silently vacuous for exactly that reason.
    """
    calls: list[str] = []
    real_urlopen = dependencies.urlopen

    def recording(request, timeout=None):
        calls.append(getattr(request, "full_url", str(request)))
        raise OSError("network disabled in tests")

    dependencies.urlopen = recording
    try:
        yield calls
    finally:
        dependencies.urlopen = real_urlopen
    assert not calls, f"expected no network call, got: {calls}"


@pytest.fixture
def axes():
    fig, ax = plt.subplots()
    yield ax
    plt.close(fig)


def pytest_addoption(parser):
    """Register the opt-in flag for the timing benchmarks."""
    parser.addoption(
        "--run-benchmark",
        action="store_true",
        default=False,
        help="run the timing benchmarks, which are skipped by default",
    )
    parser.addoption(
        "--run-browser",
        action="store_true",
        default=False,
        help="run the browser tests, which are skipped by default",
    )


def pytest_configure(config):
    """Declare the ``benchmark`` marker so strict-marker runs accept it."""
    config.addinivalue_line(
        "markers", "benchmark: a timing measurement, skipped unless asked for"
    )
    config.addinivalue_line(
        "markers", "browser: drives a real browser, skipped unless asked for"
    )


def pytest_collection_modifyitems(config, items):
    """Skip the two opt-in groups unless their flag is given.

    ``benchmark`` is machine- and load-dependent, so gating CI on it would
    buy flakes rather than information. The measurement still lives in the
    suite so the numbers quoted in the docs can be re-checked on demand
    rather than re-derived from scratch.

    ``browser`` is opt-in for an unrelated reason -- see below.
    """
    if not config.getoption("--run-benchmark"):
        skip = pytest.mark.skip(reason="timing benchmark; pass --run-benchmark")
        for item in items:
            if "benchmark" in item.keywords:
                item.add_marker(skip)

    # Browser tests are opt-in for a different reason than the benchmarks.
    # They are not flaky-by-nature; they need a browser binary and a Shiny
    # server, neither of which every contributor has, and a missing
    # browser should read as "not run here" rather than as a failure.
    if not config.getoption("--run-browser"):
        skip = pytest.mark.skip(reason="browser test; pass --run-browser")
        for item in items:
            if "browser" in item.keywords:
                item.add_marker(skip)
