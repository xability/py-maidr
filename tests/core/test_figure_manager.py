import matplotlib.pyplot as plt
import pytest
import seaborn as sns

from maidr.core import Maidr
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.enum.library import Library


# test cases for invalid inputs
def test_get_axes_from_none():
    assert FigureManager.get_axes(None) is None


def test_create_maidr_with_none_axes(mocker):
    with pytest.raises(ValueError) as e:
        FigureManager.create_maidr(None, mocker.Mock())  # type: ignore
    assert "No plot found." == str(e.value)


def test_create_maidr_with_none_plot_type(mocker):
    with pytest.raises(ValueError) as e:
        FigureManager.create_maidr(mocker.Mock(), None)  # type: ignore
    assert "No plot type found." == str(e.value)


# Parametrize the test to run with different libraries and plot types.
@pytest.mark.parametrize(
    "lib, plot_type",
    [
        # Parametrize matplotlib plots.
        (Library.MATPLOTLIB, PlotType.BAR),
        (Library.MATPLOTLIB, PlotType.BOX),
        # ``ax.step`` delegates to the already-patched ``Axes.plot``; this
        # guards against it registering a STEP *and* a LINE layer.
        (Library.MATPLOTLIB, PlotType.STEP),
        # Parametrize seaborn plots.
        (Library.SEABORN, PlotType.BAR),
        (Library.SEABORN, PlotType.BOX),
        (Library.SEABORN, PlotType.COUNT),
    ],
)
def test_get_maidr_with_single_axes(plot_fixture, lib, plot_type):
    fig, ax = plot_fixture(lib, plot_type)
    maidr = FigureManager.get_maidr(fig)

    assert isinstance(maidr, Maidr)
    assert maidr.fig is fig

    assert len(maidr.plots) == len([plot_type]) == 1
    for m_data, p_type in zip(maidr.plots, [plot_type]):
        if p_type == PlotType.COUNT:
            assert m_data.type == PlotType.BAR
        else:
            assert m_data.type == p_type


# group tests related to matplotlib
class TestMatplotlibFigureManager:
    # test `get_figure()` for matplotlib plots
    def test_get_axes_from_subplot_axes(self, axes):
        assert FigureManager.get_axes(axes) == axes

    def test_get_figure_from_bar_container(self, axes):
        bar = plt.bar([1, 2, 3], [4, 5, 6])
        assert FigureManager.get_axes(bar) == axes


# group tests related to seaborn
class TestSeabornFigureManager:
    # test `get_figure()` for seaborn plots
    def test_get_figure_from_barplot_axes(self, axes):
        bar_ax = sns.barplot(x=[1, 2, 3], y=[4, 5, 6])
        assert FigureManager.get_axes(bar_ax) == axes

    def test_get_figure_from_countplot_axes(self, axes):
        count_ax = sns.countplot(x=[1, 2, 2, 3, 3, 3])
        assert FigureManager.get_axes(count_ax) == axes
