import pytest

from maidr.core.enum.library import Library
from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.barplot import BarPlot


@pytest.mark.parametrize("lib", [Library.MATPLOTLIB, Library.SEABORN])
def test_bar_plot_data(plot_fixture, lib):
    expected_maidr_data = {
        MaidrKey.TYPE: PlotType.BAR,
        MaidrKey.SELECTOR: "g[maidr='true'] > path",
        MaidrKey.TITLE: f"Test {lib.value} bar title",
        MaidrKey.AXES: {
            MaidrKey.X: {
                MaidrKey.LABEL: f"Test {lib.value} bar x label",
                MaidrKey.LEVEL: ["1", "2", "3"],
            },
            MaidrKey.Y: {
                MaidrKey.LABEL: f"Test {lib.value} bar y label",
            },
        },
        MaidrKey.DATA: [4, 5, 6],
    }

    _, ax = plot_fixture(lib, PlotType.BAR)
    actual_maidr = BarPlot(ax)

    assert actual_maidr.schema == expected_maidr_data


def test_sns_count_plot_data(plot_fixture):
    expected_maidr_data = {
        MaidrKey.TYPE: PlotType.BAR,
        MaidrKey.SELECTOR: "g[maidr='true'] > path",
        MaidrKey.TITLE: f"Test seaborn count title",
        MaidrKey.AXES: {
            MaidrKey.X: {
                MaidrKey.LABEL: f"Test seaborn count x label",
                MaidrKey.LEVEL: ["a", "b", "c"],
            },
            MaidrKey.Y: {
                MaidrKey.LABEL: f"Test seaborn count y label",
            },
        },
        MaidrKey.DATA: [3, 2, 1],
    }

    _, ax = plot_fixture(Library.SEABORN, PlotType.COUNT)
    actual_maidr = BarPlot(ax)

    assert actual_maidr.schema == expected_maidr_data
