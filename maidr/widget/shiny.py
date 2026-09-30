"""Shiny for Python integration for MAIDR.

Provides the pair Shiny expects of any custom output: a UI function that
places the container (:func:`output_maidr`) and a renderer that fills it
(:class:`render_maidr`).

Requires the optional ``shiny`` extra::

    pip install "maidr[shiny]"
"""

from __future__ import annotations

import asyncio
import warnings
from typing import Any, Literal, Optional, Union

try:
    from htmltools import Tag, TagList, tags
    from shiny import ui as _shiny_ui
    from shiny.render.renderer import Jsonifiable, Renderer, ValueFn
    from shiny.session import Session, require_active_session
    from starlette.requests import Request
    from starlette.responses import HTMLResponse
except ImportError as error:
    from maidr.widget._extras import missing_extra_error

    raise missing_extra_error(error, "shiny", "shiny") from error

import maidr
from maidr.core.figure_manager import FigureManager
from maidr.util.dependencies import bundled_js_path
from maidr.util.served_bundle import (
    ServedBundle,
    served_bundle_dependency,
    serving_bundle,
)
from maidr.widget._focus import FOCUS_RESTORE_JS


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
    place this deviates from Shiny's packaged-component recipe.  Whether a
    chart needs the bundled ``maidr.js`` is a per-render decision --
    ``use_cdn`` chooses between the CDN and the bundled copy -- so the
    dependency that serves it rides on the rendered value, where Shiny's
    ``_process_ui`` registers it, and only when the chart names it (see
    :meth:`render_maidr._bundle_for`).  Attaching it to the container
    instead would register the bundle with every app even when every
    chart on it loads from the CDN.

    Examples
    --------
    >>> from shiny import ui
    >>> from maidr.widget.shiny import output_maidr
    >>> app_ui = ui.page_fluid(output_maidr("my_plot"))
    """
    return _shiny_ui.output_ui(id, style=f"width: {width}; height: {height};")


def _is_foreign_figure(value: Any) -> bool:
    """Report whether a value belongs to a non-matplotlib plotting library.

    :func:`maidr.render` accepts Plotly figures, Bokeh figures and layouts
    and Altair charts as well as matplotlib artists, but only matplotlib
    artists resolve through :meth:`FigureManager.get_axes`.  Checked by
    module name so that no optional library has to be imported to answer
    the question.

    Parameters
    ----------
    value : Any
        The value returned by the decorated function.

    Returns
    -------
    bool
        True if the value comes from Plotly, Bokeh or Altair.
    """
    root = type(value).__module__.split(".", 1)[0]
    return root in {"plotly", "bokeh", "altair"}


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
        "a Plotly Figure, a Bokeh figure or layout, or an Altair chart"
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


class _ServedChart:
    """One output's chart in one session, served from a route (#534).

    Attributes
    ----------
    route : str
        The session-scoped URL :meth:`shiny.Session.dynamic_route` gave
        the chart, nonce included.
    version : int
        How many renders this session has had of this output; the URL
        carries it so each render is a new address.
    document : str or None
        The latest rendered chart document, or ``None`` when there is
        nothing to serve -- before the first render, or after a render
        that returned ``None`` blanked the output.  A render replaces the
        last document rather than adding to it, so an output holds one
        chart per session: tens of KB whatever ``use_cdn`` is, since the
        bundle is served beside the documents rather than inside them
        (#457).
    """

    __slots__ = ("route", "version", "document")

    def __init__(self) -> None:
        self.route = ""
        self.version = 0
        self.document: Optional[str] = None

    def serve(self, request: Request) -> HTMLResponse:
        """Answer the browser's fetch of the chart document.

        Serves the latest document whatever version is asked for: a
        request naming an older one can only come from a frame a newer
        flush is already replacing, and it gets the current chart rather
        than an error page in front of a reader.

        Parameters
        ----------
        request : starlette.requests.Request
            The request. Its ``v`` query parameter is not consulted; it
            exists so every render has a URL of its own.

        Returns
        -------
        starlette.responses.HTMLResponse
            The chart document, ``no-store``; or 404 when there is none.
        """
        headers = {"Cache-Control": "no-store"}
        if self.document is None:
            return HTMLResponse(
                "<!DOCTYPE html><title>No chart</title>",
                status_code=404,
                headers=headers,
            )
        return HTMLResponse(self.document, headers=headers)


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
        is scoped to one output.  The bundled copy -- what ``False`` loads,
        and what ``"auto"`` falls back to offline -- is served by the app
        itself, once per app and version, rather than carried inside
        every chart.

    Returns
    -------
    render_maidr
        The renderer, registered as a Shiny output.

    Notes
    -----
    The decorated function may return a matplotlib or seaborn artist, a
    Plotly ``Figure``, a Bokeh figure or layout, or an Altair chart.
    Returning ``None`` renders nothing, which is the documented way to leave
    an output blank.

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
        # The chart this output is serving, per session it has rendered in;
        # see :meth:`_serve_out_of_band`.  Keyed by session because Shiny
        # does not stop an app from attaching one renderer instance to
        # several sessions, and state kept on the instance alone would
        # then hand one reader another's chart.
        self._served: dict[str, _ServedChart] = {}
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

    def _render_off_loop(
        self, value: Any, bundle: Optional[ServedBundle] = None
    ) -> Any:
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
        outside it. This function no longer takes a lock itself -- since
        #532 it is :meth:`maidr.core.maidr.Maidr._create_html_tag`, one
        call down through :func:`maidr.render`, that serializes renders of
        one figure -- but it waits on that lock *inside* its executor
        thread, still holding the slot. Enough sessions rendering one
        shared module-level figure could therefore make unrelated figures
        queue for a thread -- the stall this moves off the loop,
        reappearing one level down. Typical Shiny usage is a figure per
        session, where this does not arise.

        That lock is what makes the move safe rather than merely faster --
        see :mod:`maidr.util.figure_lock`.

        Parameters
        ----------
        value : Any
            Whatever the decorated function returned.
        bundle : ServedBundle or None, optional
            Where the chart document can load the bundled ``maidr.js``
            from, from :meth:`_bundle_for`; ``None`` leaves the document
            to carry it, as a render outside a session route does.

        Returns
        -------
        Any
            The rendered chart, as :func:`maidr.render` returns it.
        """
        # Entered here, on the worker thread, rather than around the
        # ``to_thread`` call: the value is then set in the context the
        # render actually runs in, whatever the executor does with contexts.
        with serving_bundle(bundle):
            return maidr.render(value, use_cdn=self.use_cdn)

    def _route(self, session: Session) -> Optional[_ServedChart]:
        """Return this output's route in ``session``, registering it once.

        Registered before the first render rather than after it, because
        the render needs to know the URL its document will be served from:
        the bundle is named relative to it (:meth:`_bundle_for`). A render
        that turns out not to be a frame leaves the route serving 404,
        exactly as a blank render does.

        The route is per output and per session, dropped, document and all,
        when the session ends. Under a module the session is a proxy that
        namespaces the route name itself.

        Parameters
        ----------
        session : shiny.Session
            The active session, which owns the route.

        Returns
        -------
        _ServedChart or None
            The output's served chart; ``None`` when the session registers
            no route -- a stub session returns an empty URL -- and the
            document has to stay in the frame.
        """
        served = self._served.get(session.id)
        if served is None:
            served = _ServedChart()
            served.route = session.dynamic_route(
                f"maidr-{self.output_id}", served.serve
            )
            if not served.route:
                return None
            self._served[session.id] = served
            session.on_ended(lambda: self._served.pop(session.id, None))
        return served

    @staticmethod
    def _bundle_for(served: _ServedChart, session: Session) -> Optional[ServedBundle]:
        """Say where the document at ``served.route`` can load ``maidr.js``.

        With ``use_cdn=False`` every chart document used to carry the
        ~1.9 MB bundle, plus ~370 KB of KaTeX, inline: fetched again for
        every chart on the page and on every render, because a ``srcdoc``
        had nowhere to load it from. The document is now fetched from the
        app's own origin (#534), so it can load the bundle by URL instead,
        and the app can serve that URL: the bundled files, registered as an
        ordinary web dependency the first time a chart names them --
        ``lib/maidr-bundle-<version>/``, the path Shiny serves every
        dependency from, versioned so a browser keeps its copy until the
        bundle changes (#457). The same copy is what ``"auto"`` falls back
        to when the CDN is unreachable; before, its fallback named a
        relative ``lib/`` path under the route that nothing served, and
        the chart was left with no runtime (#455).

        The URL is relative, because an app is often served under a prefix
        the app itself never sees -- Posit Connect, shinyapps.io, a reverse
        proxy -- and only the browser knows it. Shiny resolves both the
        frame's route and its dependencies against the page's own URL, so
        the bundle's directory is the route's depth in ``../`` followed by
        the dependency's path: from ``session/<id>/dynamic_route/<name>``,
        ``../../../lib/maidr-bundle-<version>``.

        The frame is still what isolates the chart from the host page's
        CSS (#457): a host rule such as ``*:focus { outline: none }`` would
        otherwise strip the chart's focus ring. Only where its runtime
        comes from changes.

        Parameters
        ----------
        served : _ServedChart
            The output's served chart, whose route the document comes from.
        session : shiny.Session
            The active session, whose app serves the dependency.

        Returns
        -------
        ServedBundle or None
            The served copy; ``None`` when the installed package has no
            bundle to serve, leaving the render to say so and fall back
            as it always has.
        """
        try:
            bundled_js_path()
        except FileNotFoundError:
            return None
        href = served_bundle_dependency().source_path_map(
            lib_prefix=session.app.lib_prefix
        )["href"]
        depth = served.route.split("?", 1)[0].count("/")
        return ServedBundle("../" * depth + href)

    @staticmethod
    def _serve_out_of_band(rendered: Any, served: Optional[_ServedChart]) -> Any:
        """Take the chart document out of the frame and serve it by URL.

        ``maidr.render`` hands back an ``<iframe>`` carrying the whole
        chart document in its ``srcdoc``. Returned as it is, that document
        rode the output payload over the websocket on every reactive
        flush: about 25 KB on the default ``use_cdn``, and ~2 MB with
        ``use_cdn=False``, when the bundle was inlined into it. A reader
        moving a slider paid that again per tick, for every chart on the
        page, on the one channel every input and output shares (#534).

        So the document stays here and the frame is pointed at a
        session-scoped URL instead, from :meth:`shiny.Session.dynamic_route`,
        which the browser fetches out of band. The payload is then the
        frame and its resize script, whatever the chart weighs, and the
        document travels over HTTP where the websocket is not waiting on
        it. Total bytes per flush go *up* -- the frame plus a separate
        fetch of the document -- while what the websocket carries falls,
        by two orders of magnitude when the document still carried the
        bundle.

        The route is per output and per session; see :meth:`_route`.

        Every render bumps a version in the URL and the document is served
        ``no-store``, so nothing between the reader and the app -- the
        browser's cache included -- ever hands back an earlier chart, and
        a chart that may carry one reader's data is never written to disk
        where the next user of that browser could read it. ``srcdoc``
        content was never cached either.

        What a URL changes is who can fetch it. The websocket is the
        session's own; the route is guarded by the session id in its path,
        the same way Shiny's own downloads are, and by nothing more. A
        chart is therefore reachable by anyone who learns the URL for as
        long as the session lives, which is the trade every
        ``dynamic_route`` makes.

        A ``src`` on the same origin keeps everything ``srcdoc`` gave the
        frame: the parent page still reaches into it to size it, and the
        device permissions its ``allow`` attribute delegates still apply,
        since a feature named there without an allowlist is granted to
        the origin the frame loads from (:mod:`maidr.util.iframe_utils`).

        Being served from the app's origin is also what makes the
        document small: it loads the bundle by URL from the app rather
        than carrying it, so it is tens of KB on every ``use_cdn``
        setting (:meth:`_bundle_for`).

        Parameters
        ----------
        rendered : Any
            What :func:`maidr.render` returned. Anything but a frame
            carrying a ``srcdoc`` -- a fallback tag, a chart rendered
            without an iframe -- is returned untouched.
        served : _ServedChart or None
            The output's route, from :meth:`_route`.

        Returns
        -------
        Any
            The frame, referencing its document by URL; or the frame as
            it came, document inside, when there is no route to serve it
            from.
        """
        if (
            served is None
            or not isinstance(rendered, Tag)
            or "srcdoc" not in rendered.attrs
        ):
            return rendered

        served.version += 1
        served.document = rendered.attrs.pop("srcdoc")
        # ``dynamic_route`` returns the path with a ``nonce`` query already
        # on it, so the version joins with ``&``.
        rendered.attrs["src"] = f"{served.route}&v={served.version}"
        return rendered

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
                # The output is blank now, so the frame that would fetch
                # the last chart is gone; do not keep holding it.
                served = self._served.get(session.id)
                if served is not None:
                    served.document = None
                return None

            _check_supported(value, self.__name__)
            served = self._route(session)
            bundle = None if served is None else self._bundle_for(served, session)
            rendered = await asyncio.to_thread(self._render_off_loop, value, bundle)
        finally:
            _close_new_figures(open_before)

        rendered = self._serve_out_of_band(rendered, served)

        # The script rides with the chart rather than with the container:
        # ``output_maidr`` is not always what places the output -- Express
        # mode goes through ``auto_output_ui``, and an app may write its
        # own ``ui.output_ui`` -- but every chart comes through here. It
        # guards itself, so arriving once per render costs nothing after
        # the first.
        payload = TagList(rendered, tags.script(FOCUS_RESTORE_JS))

        # Only when the document names the served copy: ``use_cdn=True``
        # and an Altair chart load from the CDN and register nothing. It
        # loads nothing into the page either -- it has no script -- and is
        # registered once per app however often it arrives.
        if bundle is not None and bundle.referenced:
            payload.append(served_bundle_dependency())

        # The same call ``shiny.render.ui`` makes: it resolves any
        # ``HTMLDependency`` on the rendered tag, registers it with the
        # app so the asset is served, and returns ``{"deps", "html"}``.
        return session._process_ui(payload)


__all__ = ["output_maidr", "render_maidr"]
