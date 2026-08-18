"""Shiny for Python integration for MAIDR.

Provides the pair Shiny expects of any custom output: a UI function that
places the container (:func:`output_maidr`) and a renderer that fills it
(:class:`render_maidr`).

Requires the optional ``shiny`` extra::

    pip install "maidr[shiny]"
"""

from __future__ import annotations

import asyncio
import logging
import threading
import warnings
import weakref
from typing import Any, Literal, Optional, Union

try:
    from htmltools import Tag, TagList, tags
    from shiny import ui as _shiny_ui
    from shiny.render.renderer import Jsonifiable, Renderer, ValueFn
    from shiny.session import require_active_session
except ImportError as error:
    from maidr.widget._extras import missing_extra_error

    raise missing_extra_error(error, "shiny", "shiny") from error

import maidr
from maidr.core.figure_manager import FigureManager
from maidr.widget._focus import FOCUS_RESTORE_JS

_logger = logging.getLogger(__name__)

#: One lock per ``Figure``, so two renders of the *same* figure cannot run
#: at once. Not process-wide: ``savefig`` on distinct figures is safe in
#: parallel, and a single lock would serialise unrelated sessions and throw
#: away most of what moving off the event loop buys.
#:
#: Why a lock is needed at all: ``savefig`` mutates the figure it is
#: writing, for the duration of the write. Two things, both measured by
#: watching the attribute from another thread while renders ran:
#:
#: * ``fig.dpi`` goes 100 -> 72 -> 100, so two concurrent writes race on
#:   that one attribute and the loser renders its whole chart at the
#:   other's dpi. A 640x480 chart came out 460.8x345.6 -- exactly the
#:   100/72 ratio -- as a valid SVG, raising nothing, on 1 of 6 concurrent
#:   renders. For a tool whose highlight overlay is positioned against
#:   that geometry, silently wrong dimensions are the bad kind of wrong.
#: * ``fig.canvas`` is swapped to a canvas that supports the output format
#:   and swapped back (``FigureCanvasAgg`` -> ``FigureCanvasSVG`` ->
#:   ``FigureCanvasAgg``), by
#:   ``FigureCanvasBase._switch_canvas_and_return_print_method``.
#:
#: That second one also answers a question this raises: ``savefig`` now
#: runs on a worker thread, and GUI backends generally want canvas work on
#: the main thread. It does not reach the GUI canvas -- the write goes
#: through the format's own canvas, which for SVG is pure Python and has
#: no thread affinity. maidr's own backend delegates to ``FigureCanvasAgg``
#: besides, and is what ``import maidr`` activates.
#:
#: ``threading.Lock``, not ``RLock``: nothing re-enters a render of the
#: same figure on the same thread today, and if something ever does, a
#: deadlock is a better outcome than two interleaved writes to one figure,
#: because it is the one that shows up.
#:
#: A ``WeakKeyDictionary`` so a closed figure's lock goes with it. The lock
#: does not reference the figure, so this adds no retention (#498).
_FIGURE_LOCKS: weakref.WeakKeyDictionary[Any, threading.Lock] = (
    weakref.WeakKeyDictionary()
)

#: Guards creation of the per-figure locks above, which is itself a
#: check-then-act on a shared mapping.
_FIGURE_LOCKS_GUARD = threading.Lock()


def _figure_lock(figure: Any) -> threading.Lock:
    """Return the lock for ``figure``, creating it on first use.

    Parameters
    ----------
    figure : Any
        The ``matplotlib`` figure about to be rendered, or ``None`` when it
        could not be resolved.

    Returns
    -------
    threading.Lock
        A lock unique to that figure. An unresolvable figure gets a fresh
        lock rather than a shared one -- serialising things we cannot tell
        apart would be a guess in the direction of a deadlock, and the
        render is safe on its own.

        Note what that means: an unresolvable value gets **no**
        synchronisation at all. Correct today because the values that land
        here -- plotly, altair -- are rendered without touching a
        ``matplotlib`` figure's ``dpi`` or ``canvas``, so there is no
        shared state to race on. A future plot type that resolves to
        ``None`` here *and* mutates shared figure state would be
        unprotected silently, which is the reason to say so rather than
        leave it to be inferred.
    """
    if figure is None:
        return threading.Lock()
    with _FIGURE_LOCKS_GUARD:
        lock = _FIGURE_LOCKS.get(figure)
        if lock is None:
            lock = threading.Lock()
            _FIGURE_LOCKS[figure] = lock
        return lock


#: Accepted by ``use_cdn`` on :class:`render_maidr`; ``None`` defers to the
#: process-wide default (:func:`maidr.get_use_cdn`).
#:
#: Spelled with ``Optional``/``Union`` rather than ``|`` because this is an
#: assignment, not an annotation: ``from __future__ import annotations``
#: defers annotations only, so ``bool | Literal["auto"] | None`` would be
#: evaluated here and raises ``TypeError`` on Python 3.9, which this
#: package supports.
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

    # ``get_axes`` is a resolver, not a validator: handed something it does
    # not understand it raises whatever the traversal happens to hit -- an
    # ``AttributeError`` for a list of non-artists, and a bare
    # ``StopIteration`` for an empty list or dict, which Python then turns
    # into ``RuntimeError: coroutine raised StopIteration`` on the way out
    # of the async render.  Whatever it raises, the answer to the question
    # asked here is the same, and it is worth saying plainly.
    try:
        resolved = FigureManager.get_axes(value)
    except Exception:
        resolved = None

    if resolved:
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

    ``FigureManager.figs`` therefore still keeps a record per figure --
    which is correct, and no longer a leak. The record is stored on the
    figure itself (#456), so it lasts exactly as long as the application's
    own reference: a cached figure keeps its data across flushes, and a
    throwaway one is reclaimed with everything maidr extracted from it.

    Parameters
    ----------
    before : set
        ``plt.get_fignums()`` as it was before the render function ran.
    """
    try:
        import matplotlib.pyplot as plt

        for num in set(plt.get_fignums()) - before:
            plt.close(plt.figure(num))
    except Exception as error:
        # Cleanup is housekeeping: it runs in a ``finally``, so raising
        # here would replace whatever the render was already failing with.
        # Swallowed, but not silently -- a bug in this function would
        # otherwise present as figures quietly accumulating, which is the
        # symptom it exists to prevent and gives no hint where to look.
        warnings.warn(
            f"maidr: could not close the figures this render opened ({error}). "
            "They will stay open for the life of the process.",
            UserWarning,
            stacklevel=2,
        )


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

    def auto_output_ui(self, **kwargs: Any) -> Tag:
        """Return the container Shiny Express places for this output.

        Parameters
        ----------
        **kwargs : Any
            Arguments for :func:`output_maidr`, supplied by
            :func:`shiny.express.output_args` and taking precedence over
            the ones given to the decorator.  Shiny splats
            ``@output_args(...)`` into this method, so a renderer whose
            signature takes nothing raises ``TypeError`` there --
            ``shiny.render.plot`` accepts ``**kwargs`` here for the same
            reason.

        Returns
        -------
        htmltools.Tag
            The output container.
        """
        # `setdefault` rather than Shiny's `set_kwargs_value` helper: that
        # one exists to skip `MISSING`/`None` so an unset argument does not
        # override the UI function's own default, and neither of these can
        # be either.
        kwargs.setdefault("width", self.width)
        kwargs.setdefault("height", self.height)
        return output_maidr(self.output_id, **kwargs)

    def _render_off_loop(self, value: Any) -> Any:
        """Render ``value`` on a worker thread, one render per figure at a time.

        ``maidr.render`` never awaits, so on the event loop it holds it for
        its whole duration. Every other session on that worker waits the
        whole time, once per reactive flush (#454).

        Moving it to a thread works because the expensive part releases the
        GIL: ``fig.savefig`` is 87-88% of the render at every chart size.
        Had it held the GIL throughout, this would have relocated the work
        without unblocking anything.

        Measured through this renderer, eight renders of a 50-bar chart,
        longest gap in a 1 ms ticker::

            idle control              1.3 ms
            on the loop             484.9 ms     wall 484 ms
            off the loop             13.4 ms     wall 565 ms

        **It is not free.** The same eight renders take ~17% longer in
        wall-clock off the loop, because each one pays a thread handoff. A
        lone user rendering sequentially is slightly slower so that
        concurrent users stop blocking each other -- which is the trade
        being made here, and the reason to keep both numbers in view
        rather than only the one that flatters it.

        A second ceiling worth knowing: ``asyncio.to_thread`` uses the
        loop's default executor, capped at ``min(32, cpu_count + 4)``
        threads and shared with anything else in the process that uses it.
        Past that many concurrent renders, sessions queue for a thread
        rather than running in parallel. The loop still stays free, which
        is what this is for.

        Lock contention eats into that same pool rather than sitting
        outside it: a render waiting on :func:`_figure_lock` is blocked
        *inside* its executor thread, still holding the slot. Enough
        sessions rendering one shared module-level figure could therefore
        make unrelated figures queue for a thread -- the stall this moves
        off the loop, reappearing one level down. Typical Shiny usage is a
        figure per session, where this does not arise.

        The lock is what makes the move safe rather than merely faster --
        see :data:`_FIGURE_LOCKS`.

        Parameters
        ----------
        value : Any
            Whatever the decorated function returned.

        Returns
        -------
        Any
            The rendered chart, as :func:`maidr.render` returns it.
        """
        figure = None
        try:
            axes = FigureManager.get_axes(value)
            figure = getattr(axes, "figure", None)
        except (AttributeError, StopIteration):
            # Narrow, and not the case an earlier comment here claimed. A
            # foreign figure -- plotly, altair -- does not raise: `get_axes`
            # matches no branch and returns `None`, which `getattr` above
            # turns into `figure = None` without ever reaching here.
            # Measured: plotly-shaped, `None`, `int` and `str` all return
            # `None`; only an empty list or dict raises, as `StopIteration`.
            #
            # So this catches malformed input that `_check_supported`
            # should already have rejected. Logged rather than swallowed:
            # a bare `except Exception` here would quietly downgrade a real
            # bug in `get_axes` to "lock scope lost", immediately before an
            # unsynchronised render.
            _logger.debug(
                "could not resolve a figure to lock for %r; rendering "
                "without a shared lock",
                type(value).__name__,
                exc_info=True,
            )
            figure = None

        with _figure_lock(figure):
            return maidr.render(value, use_cdn=self.use_cdn)

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
            rendered = await asyncio.to_thread(self._render_off_loop, value)
        finally:
            _close_new_figures(open_before)

        # The script rides with the chart rather than with the container:
        # ``output_maidr`` is not always what places the output -- Express
        # mode goes through ``auto_output_ui``, and an app may write its
        # own ``ui.output_ui`` -- but every chart comes through here. It
        # guards itself, so arriving once per render costs nothing after
        # the first.
        payload = TagList(rendered, tags.script(FOCUS_RESTORE_JS))

        # The same call ``shiny.render.ui`` makes: it resolves any
        # ``HTMLDependency`` on the rendered tag, registers it with the
        # app so the asset is served, and returns ``{"deps", "html"}``.
        return session._process_ui(payload)


__all__ = ["output_maidr", "render_maidr"]
