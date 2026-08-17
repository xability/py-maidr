"""Shiny for Python integration for MAIDR.

Provides the pair Shiny expects of any custom output: a UI function that
places the container (:func:`output_maidr`) and a renderer that fills it
(:class:`render_maidr`).

Requires the optional ``shiny`` extra::

    pip install "maidr[shiny]"
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

try:
    from htmltools import Tag
    from shiny import ui as _shiny_ui
    from shiny.render.renderer import Jsonifiable, Renderer, ValueFn
    from shiny.session import require_active_session
except ImportError as error:  # pragma: no cover - exercised by the extra
    raise ImportError(
        "maidr's Shiny integration requires the `shiny` package. "
        "Install it with: pip install \"maidr[shiny]\""
    ) from error

import maidr
from maidr.core.figure_manager import FigureManager

#: Accepted by ``use_cdn`` on :class:`render_maidr`; ``None`` defers to the
#: process-wide default (:func:`maidr.get_use_cdn`).
UseCdn = Optional[Union[bool, Literal["auto"]]]


def output_maidr(
    id: str,  # noqa: A002 - Shiny's UI functions all name this argument `id`
    *,
    width: str = "100%",
    height: str = "auto",
) -> Tag:
    """
    Create a container for a :class:`render_maidr` output.

    Parameters
    ----------
    id : str
        Output id, matching the name of the ``@render_maidr`` function.
        Module namespacing is applied by Shiny, so the same id works
        inside a :func:`shiny.module.ui`.
    width : str, default "100%"
        CSS width of the container.
    height : str, default "auto"
        CSS height of the container.

    Returns
    -------
    htmltools.Tag
        The output container.

    Notes
    -----
    No :class:`htmltools.HTMLDependency` is attached here, which is the one
    place this deviates from Shiny's packaged-component recipe.  Which copy
    of ``maidr.js`` a chart needs is a per-render decision -- ``use_cdn``
    chooses between the CDN and the bundled copy -- so the dependency rides
    on the rendered value, where Shiny's ``_process_ui`` picks it up.
    Attaching it to the container instead would ship the bundle to every
    page even when every chart on it loads from the CDN.

    Examples
    --------
    >>> from shiny import ui
    >>> from maidr.widget.shiny import output_maidr
    >>> app_ui = ui.page_fluid(output_maidr("my_plot"))
    """
    return _shiny_ui.output_ui(id, style=f"width: {width}; height: {height};")


def _is_foreign_figure(value: Any) -> bool:
    """Report whether a value belongs to a non-matplotlib plotting library.

    :func:`maidr.render` accepts Plotly figures and Altair charts as well as
    matplotlib artists, but only matplotlib artists resolve through
    :meth:`FigureManager.get_axes`.  Checked by module name so that neither
    optional library has to be imported to answer the question.

    Parameters
    ----------
    value : Any
        The value returned by the decorated function.

    Returns
    -------
    bool
        True if the value comes from Plotly or Altair.
    """
    root = type(value).__module__.split(".", 1)[0]
    return root in {"plotly", "altair"}


def _check_supported(value: Any, fn_name: str) -> None:
    """Raise a readable error when a render function returns the wrong thing.

    Parameters
    ----------
    value : Any
        The value returned by the decorated function.
    fn_name : str
        Name of the decorated function, for the error message.

    Raises
    ------
    TypeError
        If ``value`` is not something :func:`maidr.render` can render.
    """
    if _is_foreign_figure(value):
        return
    if FigureManager.get_axes(value):
        return
    raise TypeError(
        f"@render_maidr function {fn_name!r} returned "
        f"{type(value).__name__}; expected a matplotlib or seaborn artist, "
        "a Plotly Figure, or an Altair chart"
    )


def _close_new_figures(before: set) -> None:
    """Release pyplot's hold on figures opened while the render function ran.

    A Shiny render function runs once per reactive flush, so a function
    that builds its figure with ``plt.subplots()`` opens a new one every
    time, and pyplot keeps every figure -- and its canvas -- alive until
    something closes it.  Twenty-five flushes left twenty-five figures
    open and matplotlib warning about it.  :class:`shiny.render.plot`
    closes its figure for the same reason.

    Only figures that were not open beforehand are closed, so an app
    that builds one figure at module scope and returns it on each flush
    keeps the figure it owns.

    ``plt.close`` is deliberately the only thing done here.  It is safe on
    a figure the app is still holding: matplotlib can still draw a closed
    figure, and maidr's record of it in :class:`FigureManager` is left
    intact.  Dropping that record -- as an earlier version of this
    function did, via ``FigureManager.destroy`` -- looked like the
    matching cleanup but was not: "this figure number was not open before"
    is true both for a figure the render built to throw away *and* for one
    it built lazily on the first flush and cached, which is what
    ``@reactive.calc`` and any memoised helper produce.  For the cached
    one, destroying the record stripped the chart of the data maidr
    extracted at plotting time, and every later flush fell back to a
    static image: an accessible chart quietly turning into a picture, with
    only a warning on the server to show for it.

    ``FigureManager.figs`` therefore still retains an entry per figure.
    That is pre-existing behaviour rather than something this introduces,
    and it cannot be fixed from here: the entry's value is a
    :class:`~maidr.core.maidr.Maidr` that holds the figure, so even a
    weakly-keyed map would keep it reachable.

    Parameters
    ----------
    before : set
        ``plt.get_fignums()`` as it was before the render function ran.
    """
    try:
        import matplotlib.pyplot as plt

        for num in set(plt.get_fignums()) - before:
            plt.close(plt.figure(num))
    except Exception:
        # Cleanup is housekeeping; it must never replace the user's own
        # error, nor fail a render that otherwise succeeded.
        pass


class render_maidr(Renderer[Any]):
    """
    Render a plot as an accessible MAIDR chart in a Shiny app.

    Decorate a function that returns a plot, and pair it with
    :func:`output_maidr` in the UI.  The chart is sonified, navigable by
    keyboard, and readable as braille and text.

    Parameters
    ----------
    _fn : callable, optional
        The decorated function.  Supplied by Python when the decorator is
        used bare; ``None`` when it is called with options.
    width : str, default "100%"
        CSS width of the output container.
    height : str, default "auto"
        CSS height of the output container.
    use_cdn : bool, {"auto"}, or None, default None
        Where the chart loads ``maidr.js`` from -- see :func:`maidr.render`.
        ``None`` defers to the process-wide default.  Prefer this argument
        over :func:`maidr.set_use_cdn` in a Shiny app: the setter is
        process-wide state shared by every concurrent session, while this
        is scoped to one output.

    Returns
    -------
    render_maidr
        The renderer, registered as a Shiny output.

    Notes
    -----
    The decorated function may return a matplotlib or seaborn artist, a
    Plotly ``Figure``, or an Altair chart.  Returning ``None`` renders
    nothing, which is the documented way to leave an output blank.

    Any pyplot figure the function opens is closed once the chart has been
    rendered; see :func:`_close_new_figures`.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> from shiny import App, ui
    >>> from maidr.widget.shiny import output_maidr, render_maidr
    >>>
    >>> app_ui = ui.page_fluid(output_maidr("bars"))
    >>>
    >>> def server(input, output, session):
    ...     @render_maidr
    ...     def bars():
    ...         fig, ax = plt.subplots()
    ...         ax.bar(["a", "b"], [1, 2])
    ...         return ax
    >>>
    >>> app = App(app_ui, server)
    """

    def __init__(
        self,
        _fn: Optional[ValueFn[Any]] = None,
        *,
        width: str = "100%",
        height: str = "auto",
        use_cdn: UseCdn = None,
    ) -> None:
        # Assigned before ``super().__init__``: it ends by registering the
        # renderer with the session, after which these must already be set.
        self.width = width
        self.height = height
        self.use_cdn = use_cdn
        super().__init__(_fn)

    def auto_output_ui(self) -> Tag:
        """Return the container Shiny Express places for this output."""
        return output_maidr(self.output_id, width=self.width, height=self.height)

    async def render(self) -> Optional[Jsonifiable]:
        """
        Run the decorated function and return its chart as Shiny UI.

        Implemented instead of ``transform()`` because the pyplot figures
        to clean up afterwards can only be told apart from the app's own
        by what was open *before* the function ran.
        :class:`shiny.render.plot` overrides ``render()`` for the same
        reason.

        Returns
        -------
        Jsonifiable or None
            Shiny's rendered-UI payload, or ``None`` when the decorated
            function returned ``None``.
        """
        import matplotlib.pyplot as plt

        session = require_active_session(None)

        open_before = set(plt.get_fignums())
        try:
            value = await self.fn()
            if value is None:
                return None

            _check_supported(value, self.__name__)
            rendered = maidr.render(value, use_cdn=self.use_cdn)
        finally:
            _close_new_figures(open_before)

        # The same call ``shiny.render.ui`` makes: it resolves any
        # ``HTMLDependency`` on the rendered tag, registers it with the
        # app so the asset is served, and returns ``{"deps", "html"}``.
        return session._process_ui(rendered)


__all__ = ["output_maidr", "render_maidr"]
