from __future__ import annotations
from contextlib import contextmanager
from typing import Any

from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from numpy import ndarray

from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager
from tests.fixture.library_factory import LibraryFactory


class MatplotlibFactory(LibraryFactory):
    @contextmanager
    def create_plot(self, plot_types: list[PlotType]) -> Any:
        fig, axs = plt.subplots(1, len(plot_types))
        axs = axs if isinstance(axs, ndarray) else [axs]

        for ax, plot_type in zip(axs, plot_types):
            self.plot_on_ax(ax, plot_type)

        try:
            yield fig, FigureManager.get_axes(*axs)
        finally:
            plt.close(fig)

    def plot_on_ax(self, ax: Axes, plot_type: PlotType) -> None:
        if PlotType.BAR is plot_type:
            self.create_barplot(ax)
        elif PlotType.BOX is plot_type:
            self.create_boxplot(ax)
        elif PlotType.STEP is plot_type:
            self.create_stepplot(ax)

    def create_barplot(self, ax: Axes) -> Any:
        # TODO: using numbers makes matplotlib to add additional ticks messing with the
        # level extraction
        ax.bar(["1", "2", "3"], [4, 5, 6])
        ax.set_title("Test matplotlib bar title")
        ax.set_xlabel("Test matplotlib bar x label")
        ax.set_ylabel("Test matplotlib bar y label")

    def create_boxplot(self, ax: Axes) -> Any:
        ax.boxplot([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        ax.set_title("Test matplotlib box title")
        ax.set_xlabel("Test matplotlib box x label")
        ax.set_ylabel("Test matplotlib box y label")

    def create_stepplot(self, ax: Axes) -> Any:
        """Draw a hypnogram: an ordinal sleep stage held over time.

        The stages are plotted as numeric codes so they keep driving
        sonification and braille, then named via ``set_yticks(..., labels=...)``
        the way a user would. ``where="post"`` is the reading a hypnogram
        implies: the stage holds until the next reading, then jumps.
        """
        ax.step(
            [0.0, 0.5, 1.0, 1.5, 2.0, 2.5],
            [4, 2, 1, 0, 3, 4],
            where="post",
        )
        ax.set_yticks([0, 1, 2, 3, 4], labels=["N3", "N2", "N1", "REM", "Awake"])
        ax.set_title("Test matplotlib step title")
        ax.set_xlabel("Test matplotlib step x label")
        ax.set_ylabel("Test matplotlib step y label")
