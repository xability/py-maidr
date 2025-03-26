import pytest

from maidr.core.enum.library import Library
from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager


@pytest.mark.parametrize("lib", [Library.MATPLOTLIB, Library.SEABORN])
def test_box_plot_data(plot_fixture, lib):
    # x_level = ["1", "2", "3"] if lib == Library.MATPLOTLIB else ["0", "1", "2"]
    expected_maidr_data = {
        MaidrKey.TYPE: PlotType.BOX,
        MaidrKey.ORIENTATION: "vert",
        MaidrKey.TITLE: f"Test {lib.value} box title",
        MaidrKey.AXES: {
            MaidrKey.X: {
                MaidrKey.LABEL: f"Test {lib.value} box x label",
            },
            MaidrKey.Y: {
                MaidrKey.LABEL: f"Test {lib.value} box y label",
            },
        },
        MaidrKey.DATA: [
            {
                MaidrKey.FILL.value: "0",
                MaidrKey.LOWER_OUTLIER.value: [],
                MaidrKey.MIN.value: 1.0,
                MaidrKey.Q1.value: 1.5,
                MaidrKey.Q2.value: 2.0,
                MaidrKey.Q3.value: 2.5,
                MaidrKey.MAX.value: 3.0,
                MaidrKey.UPPER_OUTLIER.value: [],
            },
            {
                MaidrKey.FILL.value: "1",
                MaidrKey.LOWER_OUTLIER.value: [],
                MaidrKey.MIN.value: 4.0,
                MaidrKey.Q1.value: 4.5,
                MaidrKey.Q2.value: 5.0,
                MaidrKey.Q3.value: 5.5,
                MaidrKey.MAX.value: 6.0,
                MaidrKey.UPPER_OUTLIER.value: [],
            },
            {
                MaidrKey.FILL.value: "2",
                MaidrKey.LOWER_OUTLIER.value: [],
                MaidrKey.MIN.value: 7.0,
                MaidrKey.Q1.value: 7.5,
                MaidrKey.Q2.value: 8.0,
                MaidrKey.Q3.value: 8.5,
                MaidrKey.MAX.value: 9.0,
                MaidrKey.UPPER_OUTLIER.value: [],
            },
        ],
    }

    fig, _ = plot_fixture(lib, PlotType.BOX)
    actual_maidr = FigureManager.get_maidr(fig)

    assert actual_maidr.plots[0].schema == expected_maidr_data
