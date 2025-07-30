from __future__ import annotations

from typing import Any, Literal

from htmltools import Tag
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core import Maidr
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager


def render(plot: Any) -> Tag:
    ax = FigureManager.get_axes(plot)
    if isinstance(ax, list):
        for axes in ax:
            maidr = FigureManager.get_maidr(axes.get_figure())
        return maidr.render()
    else:
        maidr = FigureManager.get_maidr(ax.get_figure())
        return maidr.render()


def show(
    plot: Any,
    renderer: Literal["auto", "ipython", "browser"] = "auto",
    clear_fig: bool = True,
) -> object:
    ax = FigureManager.get_axes(plot)
    if isinstance(ax, list):
        for axes in ax:
            maidr = FigureManager.get_maidr(axes.get_figure())
        return maidr.show(renderer)
    else:
        maidr = FigureManager.get_maidr(ax.get_figure())
        return maidr.show(renderer, clear_fig=clear_fig)


def save_html(
    plot: Any, file: str, *, lib_dir: str | None = "lib", include_version: bool = True
) -> str:
    ax = FigureManager.get_axes(plot)
    htmls = []
    if isinstance(ax, list):
        for axes in ax:
            maidr = FigureManager.get_maidr(axes.get_figure())
            htmls.append(maidr._create_html_doc(use_iframe=False))
        return htmls[-1].save_html(
            file, libdir=lib_dir, include_version=include_version
        )
    else:
        maidr = FigureManager.get_maidr(ax.get_figure())
        return maidr.save_html(file, lib_dir=lib_dir, include_version=include_version)


def stacked(plot: Axes | BarContainer) -> Maidr:
    ax = FigureManager.get_axes(plot)
    return FigureManager.create_maidr(ax, PlotType.STACKED)


def close(plot: Any) -> None:
    ax = FigureManager.get_axes(plot)
    FigureManager.destroy(ax.get_figure())
