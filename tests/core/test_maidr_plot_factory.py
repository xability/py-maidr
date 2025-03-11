import pytest

from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.barplot import BarPlot
from maidr.core.plot.boxplot import BoxPlot
from maidr.core.plot.grouped_barplot import GroupedBarPlot
from maidr.core.plot.heatmap import HeatPlot
from maidr.core.plot.histogram import HistPlot
from maidr.core.plot.lineplot import MultiLinePlot
from maidr.core.plot.maidr_plot_factory import MaidrPlotFactory
from maidr.core.plot.scatterplot import ScatterPlot


# test invalid inputs
def test_create_with_invalid_plot_type(mocker):
    with pytest.raises(TypeError) as e:
        _ = MaidrPlotFactory.create(mocker.Mock(), mocker.Mock(), None)  # type: ignore # noqa
        assert "Unsupported plot type: None" == str(e.value)


# test valid inputs
@pytest.mark.parametrize(
    "plot_type, expected_plot_data",
    [
        (PlotType.BAR, BarPlot),
        (PlotType.BOX, BoxPlot),
        (PlotType.COUNT, BarPlot),
        (PlotType.DODGED, GroupedBarPlot),
        (PlotType.HEAT, HeatPlot),
        (PlotType.HIST, HistPlot),
        (PlotType.LINE, MultiLinePlot),
        (PlotType.SCATTER, ScatterPlot),
        (PlotType.STACKED, GroupedBarPlot),
    ],
)
def test_create_plot_data(mocker, plot_type, expected_plot_data):
    mock_plot_data = mocker.Mock(spec=expected_plot_data)
    mocker.patch(
        f"maidr.core.plot.maidr_plot_factory.{expected_plot_data.__name__}",
        return_value=mock_plot_data,
    )

    actual_plot_data = MaidrPlotFactory.create(mocker.Mock(), plot_type)

    assert isinstance(actual_plot_data, expected_plot_data)
