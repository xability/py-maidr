from __future__ import annotations

from typing import Any, Literal

from htmltools import Tag
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core import Maidr
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager


def _get_plot_or_current(plot: Any | None) -> Any:
    """
    Get the plot object or current matplotlib figure if plot is None.

    Parameters
    ----------
    plot : Any or None
        The plot object. If None, returns the current matplotlib figure.

    Returns
    -------
    Any
        The plot object or current matplotlib figure.
    """
    if plot is None:
        # Lazy import matplotlib.pyplot when needed
        import matplotlib.pyplot as plt

        return plt.gcf()
    return plot


def render(plot: Any | None = None) -> Tag:
    """
    Render a MAIDR plot to HTML.

    Parameters
    ----------
    plot : Any or None, optional
        The plot object to render. If None, uses the current matplotlib figure.

    Returns
    -------
    htmltools.Tag
        The rendered HTML representation of the plot.
    """
    plot = _get_plot_or_current(plot)

    ax = FigureManager.get_axes(plot)
    if isinstance(ax, list):
        for axes in ax:
            maidr = FigureManager.get_maidr(axes.get_figure())
        return maidr.render()
    else:
        maidr = FigureManager.get_maidr(ax.get_figure())
        return maidr.render()


def show(
    plot: Any | None = None,
    renderer: Literal["auto", "ipython", "browser"] = "auto",
    clear_fig: bool = True,
) -> object:
    """
    Display a MAIDR plot.

    Parameters
    ----------
    plot : Any or None, optional
        The plot object to display. If None, uses the current matplotlib figure.
    renderer : {"auto", "ipython", "browser"}, default "auto"
        The renderer to use for display.
    clear_fig : bool, default True
        Whether to clear the figure after displaying.

    Returns
    -------
    object
        The display result.
    """
    plot = _get_plot_or_current(plot)

    ax = FigureManager.get_axes(plot)
    if isinstance(ax, list):
        for axes in ax:
            maidr = FigureManager.get_maidr(axes.get_figure())
        return maidr.show(renderer)
    else:
        maidr = FigureManager.get_maidr(ax.get_figure())
        return maidr.show(renderer, clear_fig=clear_fig)


def save_html(
    plot: Any | None = None,
    *,
    file: str,
    lib_dir: str | None = "lib",
    include_version: bool = True,
    data_in_svg: bool = True,
) -> str:
    """
    Save a MAIDR plot as HTML file.

    Parameters
    ----------
    plot : Any or None, optional
        The plot object to save. If None, uses the current matplotlib figure.
    file : str
        The file path where to save the HTML.
    lib_dir : str or None, default "lib"
        Directory name for libraries.
    include_version : bool, default True
        Whether to include version information.
    data_in_svg : bool, default True
        Controls where the MAIDR JSON payload is placed in the HTML or SVG.

    Returns
    -------
    str
        The path to the saved HTML file.
    """
    plot = _get_plot_or_current(plot)

    ax = FigureManager.get_axes(plot)
    htmls = []
    if isinstance(ax, list):
        for axes in ax:
            maidr = FigureManager.get_maidr(axes.get_figure())
            htmls.append(maidr._create_html_doc(use_iframe=False, data_in_svg=data_in_svg))
        return htmls[-1].save_html(
            file, libdir=lib_dir, include_version=include_version
        )
    else:
        maidr = FigureManager.get_maidr(ax.get_figure())
        return maidr.save_html(
            file, lib_dir=lib_dir, include_version=include_version, data_in_svg=data_in_svg
        )


def stacked(plot: Axes | BarContainer) -> Maidr:
    ax = FigureManager.get_axes(plot)
    return FigureManager.create_maidr(ax, PlotType.STACKED)


def close(plot: Any | None = None) -> None:
    """
    Close a MAIDR plot and clean up resources.

    Parameters
    ----------
    plot : Any or None, optional
        The plot object to close. If None, uses the current matplotlib figure.
    """
    plot = _get_plot_or_current(plot)

    ax = FigureManager.get_axes(plot)
    FigureManager.destroy(ax.get_figure())
