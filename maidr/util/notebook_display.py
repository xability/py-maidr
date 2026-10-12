"""Show a figure in a notebook when and where the inline backend would.

In a notebook kernel -- JupyterLab, Notebook 7, VS Code, Colab, and a Quarto
render -- matplotlib_inline is matplotlib's backend unless something replaces
it, and it is what puts a figure in the notebook:

* **At the end of a cell.** Every figure the cell opened through pyplot is
  shown and closed (``flush_figures``, an IPython ``post_execute``
  callback), whether or not the cell called ``plt.show()``.
* **As a cell's value, or given to** ``display()``. The display formatter it
  registers for a figure shows it.

``import maidr`` makes maidr's backend matplotlib's instead, and it did
neither. A cell that drew a chart and did not call ``plt.show()`` showed
nothing, and its figure stayed open: the next ``plt.show()`` showed it under
another cell, and the next ``plt.plot()`` drew into it. A figure that was a
cell's value showed as ``<Figure size 640x480 with 1 Axes>``.

:func:`install` gives maidr's backend both, as maidr charts:

* :func:`flush_figures` runs after every cell. Like matplotlib_inline's, it
  acts only when the cell opened a figure through pyplot in interactive mode
  (:func:`note_new_figure`, called by the backend), so ``plt.ioff()`` and
  ``with plt.ioff():`` keep a figure back as they do without maidr. It then
  shows every figure still open and closes them all, or, with
  ``InlineBackend.close_figures`` off, shows the figures the cell opened and
  leaves them open.
* :func:`display_figure` shows a figure that is a cell's value, or is given
  to ``display()``, as its chart, through IPython's
  ``ipython_display_formatter``: the hook ipympl's figures are shown through.
  A figure maidr has no chart of, or one shown while another backend is
  matplotlib's, is left to IPython's other formatters, which show it as they
  would without maidr.

A figure is shown once. One that maidr already showed or rendered in the
cell -- through ``maidr.show()``, ``maidr.render()``, or as the cell's value
-- is not shown again at its end (:func:`note_displayed`), where the inline
backend would show it a second time.

ipywidgets' ``interact`` shows the figures its function drew as soon as it
has run, in its own output, through ``show_inline_matplotlib_plots``, which
calls matplotlib_inline's ``flush_figures`` when that is the backend;
:func:`install` has it call :func:`flush_figures` too.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import weakref
from typing import Any, Iterator

_logger = logging.getLogger(__name__)

#: What ``matplotlib.get_backend()`` answers while maidr's backend is
#: matplotlib's.
MAIDR_BACKEND = "module://maidr.backend"


class _State:
    """The cell being run: the figures it opened, and those maidr showed.

    Attributes
    ----------
    shell : Any
        The shell :func:`install` ran on, or None before it has.
    draw_called : bool
        Whether the running cell opened a figure through pyplot in
        interactive mode; :func:`flush_figures` does nothing until one has,
        as matplotlib_inline's does.
    to_draw : list
        The figures the running cell opened, in order. Held strongly for the
        length of a cell only, as matplotlib_inline holds them.
    displayed : weakref.WeakSet
        The figures maidr showed or rendered during the running cell.
    """

    def __init__(self) -> None:
        self.shell: Any = None
        self.draw_called = False
        self.to_draw: list[Any] = []
        self.displayed: weakref.WeakSet = weakref.WeakSet()

    def reset(self) -> None:
        """Forget the cell that has just run."""
        self.draw_called = False
        self.to_draw = []
        self.displayed = weakref.WeakSet()


_state = _State()

#: Set while a chart is rendered for somewhere other than the notebook's
#: output -- a Streamlit, Gradio or Shiny frame, an MLflow artifact -- so its
#: figure is still shown at the end of the cell; see :func:`elsewhere`.
_ELSEWHERE: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "maidr_rendered_elsewhere", default=False
)


@contextlib.contextmanager
def elsewhere() -> Iterator[None]:
    """Render charts that are not put in the notebook's output.

    A wrapper that calls ``maidr.render()`` to put the chart somewhere else
    renders it here, so that the figure is still shown at the end of the
    cell, as a plain figure saved to a file is.
    """
    token = _ELSEWHERE.set(True)
    try:
        yield
    finally:
        _ELSEWHERE.reset(token)


def maidr_backend_active() -> bool:
    """Whether maidr's backend is matplotlib's."""
    import matplotlib

    try:
        backend = matplotlib.get_backend()
    except Exception:
        _logger.debug("maidr: could not read matplotlib's backend", exc_info=True)
        return False
    return str(backend).lower() == MAIDR_BACKEND


def note_new_figure(figure: Any) -> None:
    """Queue a figure pyplot has just opened, to be shown at the end of the cell.

    Called by maidr's backend for every figure it is given a manager for, as
    matplotlib_inline's ``new_figure_manager_given_figure`` queues it: only
    in interactive mode, and only once :func:`install` has registered the
    callback that empties the queue.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        The figure.
    """
    if _state.shell is None:
        return
    import matplotlib

    if not matplotlib.is_interactive():
        return
    # Last if opened again, as matplotlib_inline orders it.
    if figure in _state.to_draw:
        _state.to_draw.remove(figure)
    _state.to_draw.append(figure)
    _state.draw_called = True


def note_displayed(figure: Any) -> None:
    """Record that maidr has shown or rendered a figure in the running cell.

    :func:`flush_figures` does not show it again. A render :func:`elsewhere`
    is not recorded.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        The figure.
    """
    if _state.shell is None or _ELSEWHERE.get():
        return
    try:
        _state.displayed.add(figure)
    except TypeError:
        # Not weakly referenceable: nothing maidr draws, but never a reason
        # for a chart to fail.
        pass


def _close_figures() -> bool:
    """``InlineBackend.close_figures``: True unless the user turned it off."""
    try:
        from matplotlib_inline.config import InlineBackend

        return bool(InlineBackend.instance().close_figures)
    except Exception:
        _logger.debug(
            "maidr: could not read InlineBackend.close_figures", exc_info=True
        )
        return True


def _show(figure: Any) -> None:
    """Show one figure as ``plt.show()`` would, and say so if it fails."""
    from maidr.backend import show_figure

    try:
        show_figure(figure)
    except Exception:
        shell = _state.shell
        if shell is None:
            raise
        # As matplotlib_inline's flush does, a figure that cannot be shown
        # is a traceback in the cell's output, not an error in the kernel's
        # log; the other figures are still shown.
        shell.showtraceback()


def flush_figures() -> None:
    """Show the figures the cell left open, as matplotlib_inline does.

    An IPython ``post_execute`` callback. Nothing happens unless the cell
    opened a figure through pyplot in interactive mode. Then, with
    ``InlineBackend.close_figures`` on, the default, every open figure is
    shown and all of them are closed; with it off, the figures the cell
    opened that are still open are shown, and left open. A figure maidr
    already showed or rendered in the cell is not shown again. Nothing
    happens while another backend is matplotlib's: that backend shows its
    own figures.
    """
    try:
        if not _state.draw_called or not maidr_backend_active():
            return
        from matplotlib._pylab_helpers import Gcf

        open_figures = [manager.canvas.figure for manager in Gcf.get_all_fig_managers()]
        if _close_figures():
            shown = open_figures
        else:
            shown = [fig for fig in _state.to_draw if fig in open_figures]
        try:
            for figure in shown:
                if figure not in _state.displayed:
                    _show(figure)
        finally:
            if _close_figures() and Gcf.get_all_fig_managers():
                import matplotlib.pyplot as plt

                plt.close("all")
    finally:
        _state.reset()


def display_figure(figure: Any) -> None:
    """Show a figure that is a cell's value, or given to ``display()``, as its chart.

    Registered with IPython's ``ipython_display_formatter`` for
    ``matplotlib.figure.Figure``. Raises ``NotImplementedError`` -- which
    that formatter takes as "not handled", so IPython goes on to the
    figure's other formatters and shows it as it would without maidr --
    while another backend is matplotlib's, and for a figure maidr has no
    chart of.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        The figure.

    Raises
    ------
    NotImplementedError
        When the figure is not shown as a maidr chart.
    """
    from maidr.core.figure_manager import FigureManager

    if not maidr_backend_active():
        raise NotImplementedError
    try:
        maidr_obj = FigureManager.get_maidr(figure)
    except KeyError:
        raise NotImplementedError from None
    from maidr.api import _resolve_use_cdn

    # Left open: a cell's value is not closed by showing it, and the end of
    # the cell closes it if the cell opened it.
    maidr_obj.show(clear_fig=False, use_cdn=_resolve_use_cdn(None))


def display_plain(figure: Any) -> bool:
    """Show a figure as the notebook shows it without maidr: as its image.

    Through the figure's image formatter, the one matplotlib_inline
    registers, with the metadata matplotlib_inline gives it; maidr's own
    display hook is bypassed.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        The figure.

    Returns
    -------
    bool
        False, having shown nothing, outside an IPython shell or when no
        image formatter for a figure is registered.
    """
    from maidr.util.notebook_figure import _registered_formats, _shell

    shell = _shell()
    if shell is None or not _registered_formats(shell):
        return False
    from IPython.display import publish_display_data

    formatter = shell.display_formatter
    hook = formatter.ipython_display_formatter
    enabled = hook.enabled
    hook.enabled = False
    try:
        data, metadata = formatter.format(figure)
    finally:
        hook.enabled = enabled
    if not data:
        return False
    try:
        from matplotlib_inline.backend_inline import _fetch_figure_metadata

        extra = _fetch_figure_metadata(figure)
    except Exception:
        _logger.debug("maidr: could not read the figure's metadata", exc_info=True)
        extra = None
    if extra:
        metadata = {**metadata, **extra}
    publish_display_data(data, metadata=metadata)
    return True


def _register_figure_formatter(shell: Any) -> None:
    """Register the formatter matplotlib_inline gives a figure, if none is.

    matplotlib_inline registers it when it becomes the backend, and maidr's
    backend becomes matplotlib's first, so a figure maidr has no chart of
    had no image. Registered from the ``InlineBackend`` configuration,
    exactly as matplotlib_inline does; a formatter already registered --
    by ``set_matplotlib_formats``, a ``%config``, or Quarto -- is kept.
    """
    from maidr.util.notebook_figure import _registered_formats, register_inline_backend

    if _registered_formats(shell):
        return
    config = register_inline_backend()
    if config is None:
        return
    from IPython.core.pylabtools import select_figure_formats

    select_figure_formats(
        shell, set(config.figure_formats), **dict(config.print_figure_kwargs)
    )


def _flush_after(wrapped: Any, instance: Any, args: Any, kwargs: Any) -> Any:
    """``show_inline_matplotlib_plots``, then maidr's own flush."""
    result = wrapped(*args, **kwargs)
    flush_figures()
    return result


#: Whether ipywidgets' hook has been wrapped; it must be wrapped once.
_widgets_hooked: list[bool] = [False]


def _hook_ipywidgets() -> None:
    """Have ``interact`` show the figures its function drew, as charts.

    ipywidgets calls ``show_inline_matplotlib_plots`` after every run of an
    ``interact`` function, inside its output, and that calls
    matplotlib_inline's ``flush_figures`` only while matplotlib_inline is
    the backend; with maidr's, a figure the function drew without
    ``plt.show()`` stayed open, to be shown by some later cell. Wrapped when
    ipywidgets is imported, or now if it is; :func:`flush_figures` does
    nothing while another backend is matplotlib's.
    """
    if _widgets_hooked[0]:
        return
    _widgets_hooked[0] = True
    import wrapt

    @wrapt.when_imported("ipywidgets.widgets.interaction")
    def _wrap(module: Any) -> None:
        if hasattr(module, "show_inline_matplotlib_plots"):
            wrapt.wrap_function_wrapper(
                module, "show_inline_matplotlib_plots", _flush_after
            )


def install(shell: Any = None) -> bool:
    """Show figures in a notebook as matplotlib_inline does, as maidr charts.

    Registers :func:`flush_figures` to run after every cell, ahead of the
    callbacks already there, and after every run of an ipywidgets
    ``interact`` function, :func:`display_figure` as the figure's display
    hook, and the figure's image formatter when none is registered; and
    puts matplotlib in interactive mode, as IPython does when
    matplotlib_inline becomes the backend, so that ``plt.ioff()`` keeps a
    figure back as it does without maidr. Safe to call more than once:
    ``maidr.set_backend(use_maidr=True)`` calls it again, since
    ``%matplotlib widget`` replaces the display hook.

    Parameters
    ----------
    shell : InteractiveShell, optional
        The shell. The running one by default.

    Returns
    -------
    bool
        True when installed; False outside an IPython shell.
    """
    from maidr.util.notebook_figure import _shell

    shell = shell if shell is not None else _shell()
    if shell is None:
        return False
    try:
        import matplotlib
        from matplotlib.figure import Figure

        callbacks = shell.events.callbacks["post_execute"]
        if flush_figures not in callbacks:
            # First, so the figures are shown and closed before pyplot's own
            # callback draws every figure left open, which in interactive
            # mode it does at the end of every cell: drawn with Agg, only to
            # be saved as SVG and closed.
            callbacks.insert(0, flush_figures)
        shell.display_formatter.ipython_display_formatter.for_type(
            Figure, display_figure
        )
        _register_figure_formatter(shell)
        _hook_ipywidgets()
        if _state.shell is None:
            matplotlib.interactive(True)
        _state.shell = shell
    except Exception:
        # Never why `import maidr` fails.
        _logger.debug("maidr: could not install the notebook display", exc_info=True)
        return False
    return True
