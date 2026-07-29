from __future__ import annotations

import pytest
from matplotlib import pyplot as plt

from maidr.core.enum.plot_type import PlotType
from maidr.core.enum.library import Library
from maidr.util import dependencies
from tests.fixture.matplotlib_factory import MatplotlibFactory
from tests.fixture.seaborn_factory import SeabornFactory


@pytest.fixture(autouse=True)
def offline_cdn_version(monkeypatch):
    """Keep CDN URL construction off the network for the whole suite.

    ``MAIDR_CDN_VERSION=latest`` short-circuits the ``latest`` dist-tag
    lookup, so rendering tests neither hit jsDelivr/npm nor depend on
    whatever version happens to be published when CI runs.  Tests that
    exercise resolution itself override this explicitly.
    """
    monkeypatch.setenv(dependencies.CDN_VERSION_ENV_VAR, dependencies.LATEST_TAG)
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
def axes():
    fig, ax = plt.subplots()
    yield ax
    plt.close(fig)
