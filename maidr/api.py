from __future__ import annotations

import json
import os
from typing import Any, Literal

from htmltools import Tag
from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core import Maidr
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager


# ---------------------------------------------------------------------------
# Module-level default for ``use_cdn``
# ---------------------------------------------------------------------------
#
# Users can override the default via ``maidr.set_use_cdn(...)`` or by
# setting the ``MAIDR_USE_CDN`` environment variable.  The env var is
# read lazily on first access so that ``import maidr`` does not have any
# order-dependent side effects.

_USE_CDN_ENV_VAR = "MAIDR_USE_CDN"
_use_cdn_default: bool | Literal["auto"] | None = None

# ---------------------------------------------------------------------------
# Notebook load-once state for ``init_notebook``
# ---------------------------------------------------------------------------
#
# Mirrors the pattern used by Plotly (``init_notebook_mode``) and Bokeh
# (``output_notebook``): the bundled ``maidr.js`` / ``maidr.css`` are
# injected into the parent notebook DOM exactly once per kernel session
# and subsequent iframe outputs pull them from ``window.parent`` rather
# than duplicating the ~1.7 MB bundle per cell.

_NOTEBOOK_LOADED: bool = False


def _coerce_use_cdn(value: Any) -> bool | Literal["auto"]:
    """Normalise an arbitrary value into ``bool`` or ``"auto"``.

    Accepts strings (``"1"``, ``"true"``, ``"auto"``, ``"0"``, ``"false"``,
    ``""``) as well as proper booleans.  Unknown / missing / empty values
    fall back to ``"auto"`` — this default emits the CDN loader with a
    client-side ``onerror`` handler that swaps in the bundled copy when
    the CDN is unreachable, giving users offline resilience with zero
    configuration.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return "auto"
    text = str(value).strip().lower()
    if text == "auto":
        return "auto"
    if text in {"0", "false", "no", "off"}:
        return False
    if text in {"1", "true", "yes", "on"}:
        return True
    # Empty / unknown strings fall back to the safe ``"auto"`` mode.
    return "auto"


def set_use_cdn(value: bool | Literal["auto"]) -> None:
    """Set the process-wide default for ``use_cdn``.

    Parameters
    ----------
    value : bool or {"auto"}
        The new default used by :func:`render`, :func:`show`, and
        :func:`save_html` when they are called without an explicit
        ``use_cdn=`` keyword argument.  Also picked up by the
        matplotlib backend when the user calls ``plt.show()``.
    """
    global _use_cdn_default
    _use_cdn_default = _coerce_use_cdn(value)


def get_use_cdn() -> bool | Literal["auto"]:
    """Return the current default for ``use_cdn``.

    Reads ``MAIDR_USE_CDN`` from the environment on first call so
    that ``MAIDR_USE_CDN=auto python ...`` works without requiring
    callers to invoke :func:`set_use_cdn` themselves.

    Notes
    -----
    The built-in default is ``"auto"`` — this mode emits a CDN
    ``<script>`` with a client-side ``onerror`` handler that falls
    back to the bundled copy on network failure.  The browser is
    the authoritative signal for CDN reachability, so no Python-side
    network probing is performed.
    """
    global _use_cdn_default
    if _use_cdn_default is None:
        _use_cdn_default = _coerce_use_cdn(
            os.environ.get(_USE_CDN_ENV_VAR)
        )
    return _use_cdn_default


def _resolve_use_cdn(
    value: bool | Literal["auto"] | None,
) -> bool | Literal["auto"]:
    """Resolve a user-supplied ``use_cdn`` value to a concrete mode.

    When ``value`` is ``None`` the process-wide default (from
    :func:`get_use_cdn` / :data:`MAIDR_USE_CDN`) is consulted.
    Explicit values (``True``, ``False``, or ``"auto"``) are honoured
    verbatim.  Unlike earlier revisions there is no Python-side
    connectivity probe — offline detection is performed in the
    browser via a ``<script onerror>`` fallback.
    """
    if value is None:
        return get_use_cdn()
    return value


def init_notebook(
    use_cdn: bool | Literal["auto"] | None = None,
    force: bool = False,
) -> None:
    """Inject the bundled ``maidr.js`` / ``maidr.css`` into the notebook DOM.

    Mirrors the ``plotly.offline.init_notebook_mode`` / ``bokeh.io.output_notebook``
    pattern: load the library once at the top of the notebook instead of
    duplicating the ~1.7 MB bundle in every iframe ``srcdoc``.  The source
    strings are stashed on ``window.__maidrJsSource`` / ``window.__maidrCssSource``
    in the parent document so that later iframe outputs can evaluate them
    in their own JS context without the bundle re-appearing in the
    notebook file.

    Parameters
    ----------
    use_cdn : bool, {"auto"}, or None, optional
        * ``True``: inject ``<script src="{CDN}">`` and ``<link>`` tags
          so the notebook loads the CDN copy once.
        * ``False``: read the bundled ``maidr.js`` / ``maidr.css`` from
          the installed package and embed them as strings on ``window``.
        * ``"auto"``: try the CDN first and fall back to the bundled
          source client-side.
        * ``None`` (default): defer to :func:`get_use_cdn`.
    force : bool, default False
        Re-inject even if :data:`_NOTEBOOK_LOADED` is already ``True``.
        Useful in Colab where each cell renders in isolation and the
        parent context is reset between cells.

    Notes
    -----
    No-op outside notebook environments (``Environment.is_notebook()``
    returns ``False``).  Safe to call multiple times — the guard flag
    prevents re-injection unless ``force=True``.
    """
    global _NOTEBOOK_LOADED

    from maidr.util.environment import Environment

    if not Environment.is_notebook():
        return
    if _NOTEBOOK_LOADED and not force:
        return

    try:
        from IPython.display import HTML, display
    except ImportError:
        # IPython not importable — nothing to display into.
        return

    from maidr.util.dependencies import (
        MAIDR_CSS_CDN_URL,
        MAIDR_JS_CDN_URL,
        bundled_css_path,
        read_bundled_js,
    )

    mode = _resolve_use_cdn(use_cdn)

    if mode is True:
        # CDN-only: a single <script src> + <link> reference suffices;
        # nothing is stashed on window.* because iframes inject their
        # own CDN <script> as before.
        html = (
            f'<link rel="stylesheet" href="{MAIDR_CSS_CDN_URL}">'
            f'<script src="{MAIDR_JS_CDN_URL}"></script>'
        )
    else:
        # ``False`` or ``"auto"``: embed the bundled source strings
        # once in the parent DOM.  For ``"auto"`` we also kick off a
        # CDN <script>/<link> so the parent can use the remote copy
        # opportunistically, but iframes will prefer the local strings
        # because they are guaranteed to resolve.
        try:
            js_source = read_bundled_js()
            css_source = bundled_css_path().read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            # Bundle is missing — fall back to CDN so we don't silently
            # break the user's notebook.
            html = (
                f'<link rel="stylesheet" href="{MAIDR_CSS_CDN_URL}">'
                f'<script src="{MAIDR_JS_CDN_URL}"></script>'
            )
        else:
            # json.dumps produces a JS-safe string literal (escapes quotes,
            # backslashes, newlines, etc.).  ``ensure_ascii=True`` (the
            # default) also escapes U+2028 / U+2029 which JS treats as
            # line terminators.  We then rewrite ``</`` to ``<\/`` so
            # that a stray ``</script>`` inside the JS source cannot
            # terminate the outer ``<script>`` tag early — the leading
            # backslash is a legal (redundant) JSON escape.
            js_literal = json.dumps(js_source).replace("</", "<\\/")
            css_literal = json.dumps(css_source).replace("</", "<\\/")
            cdn_bootstrap = ""
            if mode == "auto":
                cdn_bootstrap = (
                    f'<link rel="stylesheet" href="{MAIDR_CSS_CDN_URL}">'
                    f'<script src="{MAIDR_JS_CDN_URL}"></script>'
                )
            html = (
                f"<script>"
                f"window.__maidrJsSource = {js_literal};"
                f"window.__maidrCssSource = {css_literal};"
                f"</script>"
                f"{cdn_bootstrap}"
            )

    display(HTML(html))
    _NOTEBOOK_LOADED = True


def _is_plotly_figure(obj: Any) -> bool:
    """
    Check if an object is a Plotly figure without importing plotly at top level.

    Parameters
    ----------
    obj : Any
        The object to check.

    Returns
    -------
    bool
        True if the object is a Plotly figure.
    """
    module = getattr(type(obj), "__module__", "")
    return module.startswith("plotly.")


def _get_plotly_maidr(fig: Any) -> Any:
    """
    Create a PlotlyMaidr instance from a Plotly figure.

    Parameters
    ----------
    fig : plotly.graph_objects.Figure
        The Plotly figure.

    Returns
    -------
    PlotlyMaidr
        The PlotlyMaidr instance for the given figure.
    """
    from maidr.plotly import PlotlyMaidr

    return PlotlyMaidr(fig)


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


def render(
    plot: Any | None = None,
    use_cdn: bool | Literal["auto"] | None = None,
) -> Tag:
    """
    Render a MAIDR plot to HTML.

    Parameters
    ----------
    plot : Any or None, optional
        The plot object to render. If None, uses the current matplotlib figure.
    use_cdn : bool, {"auto"}, or None, default=None
        * ``True``: load ``maidr.js`` from the public jsDelivr CDN only
          (no offline fallback).
        * ``False``: reference the copy bundled inside the installed
          ``maidr`` package.  Use this in air-gapped environments.
        * ``"auto"``: emit a CDN ``<script>`` with a client-side
          ``onerror`` handler that swaps in the bundled copy when the
          CDN is unreachable.  This is the default mode and gives
          offline resilience without any Python-side network probing.
        * ``None`` (default): use the process-wide default set via
          :func:`set_use_cdn` or the ``MAIDR_USE_CDN`` env var (both
          default to ``"auto"``).

    Returns
    -------
    htmltools.Tag
        The rendered HTML representation of the plot.
    """
    use_cdn = _resolve_use_cdn(use_cdn)
    if plot is not None and _is_plotly_figure(plot):
        return _get_plotly_maidr(plot).render(use_cdn=use_cdn)

    plot = _get_plot_or_current(plot)

    ax = FigureManager.get_axes(plot)
    if isinstance(ax, list):
        for axes in ax:
            maidr = FigureManager.get_maidr(axes.get_figure())
        return maidr.render(use_cdn=use_cdn)
    else:
        maidr = FigureManager.get_maidr(ax.get_figure())
        return maidr.render(use_cdn=use_cdn)


def show(
    plot: Any | None = None,
    renderer: Literal["auto", "ipython", "browser"] = "auto",
    clear_fig: bool = True,
    use_cdn: bool | Literal["auto"] | None = None,
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
    use_cdn : bool, {"auto"}, or None, default=None
        See :func:`render` for the three possible modes.  ``None``
        defers to :func:`get_use_cdn` (the process-wide default).

    Returns
    -------
    object
        The display result.
    """
    use_cdn = _resolve_use_cdn(use_cdn)
    if plot is not None and _is_plotly_figure(plot):
        return _get_plotly_maidr(plot).show(renderer, use_cdn=use_cdn)

    plot = _get_plot_or_current(plot)

    ax = FigureManager.get_axes(plot)
    if isinstance(ax, list):
        for axes in ax:
            maidr = FigureManager.get_maidr(axes.get_figure())
        return maidr.show(renderer, use_cdn=use_cdn)
    else:
        maidr = FigureManager.get_maidr(ax.get_figure())
        return maidr.show(renderer, clear_fig=clear_fig, use_cdn=use_cdn)


def save_html(
    plot: Any | None = None,
    *,
    file: str,
    lib_dir: str | None = "lib",
    include_version: bool = True,
    data_in_svg: bool = True,
    use_cdn: bool | Literal["auto"] | None = None,
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
    use_cdn : bool, {"auto"}, or None, default=None
        * ``True``: reference the public jsDelivr CDN only (no files
          copied, no offline fallback).
        * ``False``: bundle ``maidr.js`` / ``maidr.css`` into ``lib_dir``
          next to the saved HTML and reference them with relative
          paths.  The resulting directory is self-contained and works
          without any network access.
        * ``"auto"``: copy the bundle alongside the HTML and emit a
          CDN loader with a client-side ``onerror`` fallback, so the
          HTML works both online and offline.  This is the default mode.
        * ``None`` (default): use the process-wide default (see
          :func:`set_use_cdn` / ``MAIDR_USE_CDN``).  Both default to
          ``"auto"``.

    Returns
    -------
    str
        The path to the saved HTML file.
    """
    use_cdn = _resolve_use_cdn(use_cdn)
    if plot is not None and _is_plotly_figure(plot):
        return _get_plotly_maidr(plot).save_html(
            file,
            lib_dir=lib_dir,
            include_version=include_version,
            use_cdn=use_cdn,
        )

    plot = _get_plot_or_current(plot)

    ax = FigureManager.get_axes(plot)
    htmls = []
    if isinstance(ax, list):
        for axes in ax:
            maidr = FigureManager.get_maidr(axes.get_figure())
            htmls.append(
                maidr._create_html_doc(
                    use_iframe=False,
                    data_in_svg=data_in_svg,
                    use_cdn=use_cdn,
                )
            )
        return htmls[-1].save_html(
            file, libdir=lib_dir, include_version=include_version
        )
    else:
        maidr = FigureManager.get_maidr(ax.get_figure())
        return maidr.save_html(
            file,
            lib_dir=lib_dir,
            include_version=include_version,
            data_in_svg=data_in_svg,
            use_cdn=use_cdn,
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
    if plot is not None and _is_plotly_figure(plot):
        # For Plotly figures, no FigureManager cleanup needed
        return

    plot = _get_plot_or_current(plot)

    ax = FigureManager.get_axes(plot)
    FigureManager.destroy(ax.get_figure())
