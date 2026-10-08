"""Render plotnine plots with MAIDR accessibility.

Architecture
------------
plotnine draws through matplotlib, but its geoms add low-level collections and
patches to the axes rather than calling the ``Axes.bar`` / ``Axes.plot`` family
py-maidr patches, so ``import maidr`` alone reads almost nothing of a
``ggplot`` -- and what it does read, ``geom_point`` through ``Axes.scatter``,
it places on the wrong panel of a faceted one, since plotnine nests its panels
in a gridspec of its own.

So a ``ggplot`` handed to ``maidr.show`` / ``render`` / ``save_html`` is read
from plotnine's own layer data instead (:mod:`maidr.plotnine.layers`): a copy
of it is drawn, each layer's computed frame -- after its stat, its position
adjustment and its scales -- becomes one MAIDR layer per facet panel, and the
facet layout becomes the subplot grid. The matplotlib figure that draw made
is then rendered by the same :class:`~maidr.core.maidr.Maidr` machinery every
matplotlib chart goes through, so ``use_cdn``, notebooks, Shiny and saved
pages all behave as they do there. The highlight names each drawn element by
the ``gid`` it is given, which matplotlib writes as the element's ``<g id>``.

Limitations
-----------
* Experimental as a whole: see ``docs/stability.qmd#plotnine-support``.
* The geoms read are ``geom_bar``, ``geom_col``, ``geom_histogram``,
  ``geom_point``, ``geom_line``, ``geom_smooth``, ``geom_boxplot`` and
  ``geom_tile``, on ``coord_cartesian``; ``geom_path`` only as a
  precision-recall curve, and ``geom_ribbon`` only as the
  ``stat_summary(fun_data="median_hilow")`` band around a median line drawn
  with it. Anything else is left out with a warning naming it, and a chart
  with nothing read is drawn as a static image.
* A ``ggplot`` shown through plotnine itself -- ``p.show()``, or a notebook's
  own display of ``p`` -- is not read; ``maidr.show(p)`` is the entry point.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Literal

from htmltools import Tag
from matplotlib.figure import Figure

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.maidr import Maidr
from maidr.plotnine.layers import (
    PlotnineLayer,
    Unreadable,
    draw,
    read_layer,
    read_panels,
    read_percentile_bands,
    unreadable_coord,
)
from maidr.util.caller_warning import warn_at_caller
from maidr.util.fallback import fallback_tag

#: The oldest plotnine :mod:`maidr.plotnine.layers` was measured against, and
#: the newest that installs on Python 3.9. Nothing older was measured, and the
#: build steps the reader hooks into are plotnine's internals, so an older one
#: is drawn as a static image rather than read on trust.
MIN_PLOTNINE = (0, 13)

_NOTHING_READ = (
    "maidr found nothing it can read in this plotnine chart, so it is shown "
    "as a static image, without keyboard, sound or braille access."
)


class PlotnineMaidr:
    """
    Render a plotnine ``ggplot`` with MAIDR accessibility.

    Parameters
    ----------
    plot : plotnine.ggplot
        The plot. It is copied before it is drawn and is left as it was.
    """

    def __init__(self, plot: Any) -> None:
        import plotnine

        layers: list[PlotnineLayer] = []
        metadata: dict = {}
        if _version(plotnine.__version__) < MIN_PLOTNINE:
            warn_at_caller(
                f"maidr reads plotnine {'.'.join(map(str, MIN_PLOTNINE))} or "
                f"newer; this is plotnine {plotnine.__version__}."
            )
            figure = _draw_plainly(plot)
        else:
            built, figure, drawn = draw(plot)
            layers, metadata = _read(built, drawn)

        self._figure: Figure = figure
        self._maidr = _PlotnineFigure(figure, layers, metadata)
        if not layers:
            warn_at_caller(_NOTHING_READ)

    @property
    def figure(self) -> Figure:
        """The matplotlib figure plotnine drew."""
        return self._figure

    def render(self, use_cdn: bool | Literal["auto"] = "auto") -> Tag:
        """Return the accessible plot inside an iframe.

        Parameters
        ----------
        use_cdn : bool or {"auto"}, default="auto"
            Where ``maidr.js`` is loaded from; see :func:`maidr.render`.
        """
        if not self._maidr.plots:
            return fallback_tag(self._figure, _NOTHING_READ)
        return self._maidr.render(use_cdn=use_cdn)

    def show(
        self,
        renderer: Literal["auto", "ipython", "browser"] = "auto",
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> object:
        """Display the accessible plot.

        Parameters
        ----------
        renderer : {"auto", "ipython", "browser"}, default="auto"
            Renderer to use.
        use_cdn : bool or {"auto"}, default="auto"
            See :meth:`render`.
        """
        if not self._maidr.plots:
            return fallback_tag(self._figure, _NOTHING_READ).show()
        return self._maidr.show(renderer, clear_fig=True, use_cdn=use_cdn)

    def save_html(
        self,
        file: str,
        *,
        lib_dir: str | None = "lib",
        include_version: bool = True,
        data_in_svg: bool = True,
        use_cdn: bool | Literal["auto"] = "auto",
    ) -> str:
        """Save the accessible plot as an HTML file.

        Parameters
        ----------
        file : str
            Destination HTML file path.
        lib_dir : str or None, default="lib"
            Folder (relative to ``file``) used for static dependencies.
        include_version : bool, default=True
            Whether to stamp the dependency folder name with a version.
        data_in_svg : bool, default=True
            Where the MAIDR JSON payload is placed; see
            :meth:`maidr.core.maidr.Maidr.save_html`.
        use_cdn : bool or {"auto"}, default="auto"
            See :meth:`render`.
        """
        if not self._maidr.plots:
            return fallback_tag(self._figure, _NOTHING_READ).save_html(file)
        return self._maidr.save_html(
            file,
            lib_dir=lib_dir,
            include_version=include_version,
            data_in_svg=data_in_svg,
            use_cdn=use_cdn,
        )

    def _flatten_maidr(self) -> dict:
        """The MAIDR schema this plot renders with."""
        return self._maidr._flatten_maidr()


class _PlotnineFigure(Maidr):
    """
    A :class:`Maidr` whose layers and grid were read from a ``ggplot``.

    Three of the base class's readings of a matplotlib figure do not hold for
    one plotnine drew, and are replaced:

    * the grid cell is the facet layout's ``ROW``/``COL``, already dense and
      zero-based, where the base ranks gridspec starts -- which plotnine's
      nested gridspec reports as ``(0, 0)`` for every panel;
    * no layer supersedes another: each came from its own ``ggplot`` layer,
      so a ``geom_line`` beside a ``geom_smooth`` is two readings, not the one
      curve ``sns.regplot`` registers twice;
    * the figure's title, subtitle and caption are the plot's ``labs``, which
      plotnine draws as figure text rather than as ``suptitle``.
    """

    def __init__(self, fig: Figure, layers: list[PlotnineLayer], metadata: dict):
        super().__init__(fig, layers[0].type if layers else PlotType.LINE)
        self._plots = list(layers)
        self.selector_ids = [Maidr._unique_id() for _ in layers]
        self._metadata = metadata

    def _figure_metadata(self) -> dict:
        return dict(self._metadata)

    def _grid_coordinates(self) -> tuple[Callable[[int], int], Callable[[int], int]]:
        return (lambda row: row), (lambda col: col)

    def _drop_superseded_layers(self) -> None:
        return None


def _read(built: Any, drawn: list) -> tuple[list[PlotnineLayer], dict]:
    """Every layer read from the drawn plot, and the figure-level labels."""
    labels = built.labels
    panels = read_panels(built)
    layers: list[PlotnineLayer] = []

    coord = unreadable_coord(built)
    if coord is not None:
        warn_at_caller(
            f"maidr does not read plotnine charts drawn on {coord}; only "
            "coord_cartesian (and coord_fixed) is read."
        )
        return layers, {}

    bands, paired = read_percentile_bands(built.layers, drawn, panels, labels)
    for index, (layer, groups) in enumerate(zip(built.layers, drawn)):
        if index in bands:
            layers.extend(bands[index])
        if index in paired:
            continue
        try:
            layers.extend(read_layer(layer, groups, panels, labels))
        except Unreadable as reason:
            warn_at_caller(
                f"maidr left the {type(layer.geom).__name__} layer out of this "
                f"plotnine chart: {reason}."
            )

    metadata: dict = {}
    # A single panel carries the title on its layer, as `ax.set_title` does;
    # a faceted chart titles each panel by its facet and the figure by `labs`.
    fields = [(MaidrKey.SUBTITLE, "subtitle"), (MaidrKey.CAPTION, "caption")]
    if len(panels) > 1:
        fields.insert(0, (MaidrKey.TITLE, "title"))
    for key, name in fields:
        text = str(labels.get(name, None) or "").strip()
        if text:
            metadata[key] = text
    return layers, metadata


def _draw_plainly(plot: Any) -> Figure:
    """Draw a copy of ``plot`` with nothing recorded, for the static image."""
    import copy

    from maidr.core.context_manager import ContextManager

    with ContextManager.set_internal_context():
        return copy.deepcopy(plot).draw()


def _version(text: str) -> tuple[int, ...]:
    """The leading numeric components of a version string, as a tuple."""
    return tuple(int(part) for part in re.findall(r"\d+", text)[:2])
