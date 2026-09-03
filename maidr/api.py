from __future__ import annotations

import json
import os
import warnings
from typing import Any, Literal

from htmltools import Tag
from matplotlib.axes import Axes
from matplotlib.container import BarContainer
from matplotlib.figure import Figure

from maidr.core import Maidr
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.exception.unsupported_plot_error import UnsupportedPlotError
from maidr.util.fallback import fallback_tag, warn_unsupported


def _is_altair_chart(plot: Any) -> bool:
    """Check if the plot is an Altair chart object.

    Parameters
    ----------
    plot : Any
        The object to check.

    Returns
    -------
    bool
        ``True`` if the object is an Altair chart, ``False`` otherwise
        (including when the optional ``altair`` extra is not installed).
    """
    try:
        from maidr.altair.utils import is_altair_chart

        return is_altair_chart(plot)
    except ImportError:
        return False


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
# (``output_notebook``): the bundled ``maidr.js`` / ``maidr-math.css`` are
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
    back to the bundled copy on network failure.  The browser remains
    the authoritative signal for CDN *reachability*; Python never
    probes that.

    Python does make one network request on the CDN paths (``True``
    and ``"auto"``): resolving the published ``maidr`` version so the
    emitted URL is immutable instead of the mutable ``@latest``
    dist-tag, which browsers cache for a week.  It runs once per
    process, is bounded by ``MAIDR_CDN_TIMEOUT`` (3s total), and falls
    back to ``@latest`` on failure.  Set ``MAIDR_CDN_VERSION=latest``
    to skip it entirely.  ``use_cdn=False`` never makes any request.

    With one exception, which this setting cannot reach: the Altair
    adapter always loads from the CDN and always resolves, because
    ``use_cdn`` is not plumbed through it.  So an Altair chart can
    still spend the lookup budget under ``MAIDR_USE_CDN=false``.
    ``MAIDR_CDN_VERSION=bundled`` is the setting that stops it, and
    :func:`save_html` / :func:`show` say the same.
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
    Explicit values are validated: only ``True``, ``False`` and ``"auto"``
    are accepted.  Anything else used to pass through untouched, and the
    consumers branch ``is False`` / ``== "auto"`` / else-CDN, so a slip
    like ``use_cdn="false"`` or ``use_cdn=0`` -- the string and integer
    forms :func:`set_use_cdn` and ``MAIDR_USE_CDN`` do accept -- rendered
    a CDN-only page with no offline fallback for the one reader who had
    asked for offline, and said nothing.  Resolving the mode itself makes
    no network request: offline *detection* is performed in the browser
    via a ``<script onerror>`` fallback, not by probing from Python.  (The
    CDN modes do resolve the published version over the network when
    they build a URL — see :func:`get_use_cdn`.)

    Raises
    ------
    TypeError
        If ``value`` is not ``None``, ``True``, ``False`` or ``"auto"``.
        Identity checks, so ``0`` and ``1`` are rejected rather than
        passing as equal to ``False`` and ``True``.
    """
    if value is None:
        return get_use_cdn()
    if value is True or value is False or value == "auto":
        return value
    raise TypeError(
        f"use_cdn must be True, False or 'auto', got {value!r}; "
        "set_use_cdn() and MAIDR_USE_CDN accept the string forms"
    )


#: What the Altair path fetches remotely, named in the warning so a reader
#: can see what would have to travel with the page rather than being told
#: only that something will not.
#:
#: A tuple rather than the prose it becomes, so a test can compare it to
#: what the adapter really requests. As one string it could not be: `vega`
#: is a substring of both `vega-lite` and `vega-embed`, so a check for it
#: passes whether or not plain `vega` is still fetched, and a dependency
#: quietly dropped would go on being named.
#: `tests/core/test_altair_use_cdn_is_not_silent.py` holds it to the four.
_ALTAIR_REMOTE_RUNTIME = ("vega", "vega-lite", "vega-embed", "vegalite.js")


def _listed() -> str:
    """Render :data:`_ALTAIR_REMOTE_RUNTIME` as prose for the warning."""
    *rest, last = _ALTAIR_REMOTE_RUNTIME
    return f"{', '.join(rest)} and maidr's own {last}"


def _warn_altair_ignores_use_cdn(
    use_cdn: bool | Literal["auto"] | None, *, stacklevel: int
) -> None:
    """Say that ``use_cdn=False`` cannot be honoured for an Altair chart.

    The Altair path delegates to the upstream Vega-Lite adapter, which is
    loaded from a CDN and has no bundled counterpart -- so the flag was
    accepted and discarded, and the reader who most needs to know is the
    one it fails for: ``use_cdn=False`` means they cannot reach a CDN, and
    without this they get a chart that never initialises and no reason why
    (#521).

    Only an explicit ``False`` warns. ``"auto"`` is the CDN with a fallback
    that this path does not have either, but a reader on ``"auto"`` has not
    said they are offline, and warning them on every render would be noise
    on the common case.

    Parameters
    ----------
    use_cdn : bool, {"auto"}, or None
        The caller's value, unresolved. Resolved here rather than by the
        caller because ``None`` defers to the process default, which may
        itself be ``False``.
    stacklevel : int
        Passed through to :func:`warnings.warn`. Keyword-only because it is
        a frame count rather than a value about the chart, and the three
        entry points that pass it sit at the same depth today -- so a
        positional argument would read as one more thing about `use_cdn`
        and silently become wrong the moment one of them grew a wrapper.
    """
    if _resolve_use_cdn(use_cdn) is not False:
        return

    warnings.warn(
        "maidr: use_cdn=False cannot be honoured for an Altair chart. That "
        "path renders through the upstream Vega-Lite adapter, which is only "
        f"published on a CDN, so the page still loads {_listed()} remotely "
        "and will not initialise without network access. Render the "
        "same data through matplotlib or seaborn for an offline chart.",
        stacklevel=stacklevel,
    )


def init_notebook(
    use_cdn: bool | Literal["auto"] | None = None,
    force: bool = False,
) -> None:
    """Inject the bundled ``maidr.js`` / ``maidr-math.css`` into the notebook DOM.

    Mirrors the ``plotly.offline.init_notebook_mode`` / ``bokeh.io.output_notebook``
    pattern: load the library once at the top of the notebook instead of
    duplicating the ~1.7 MB bundle in every iframe ``srcdoc``.  The source
    strings are stashed on ``window.__maidrJsSource`` /
    ``window.__maidrMathCssSource`` in the parent document so that later
    iframe outputs can evaluate them in their own JS context without the
    bundle re-appearing in the notebook file.

    The stylesheet stashed alongside the script is ``maidr-math.css``, the
    KaTeX rules that style LaTeX in AI chat responses.  It travels as a
    source string for the same reason the script does: an iframe rendered
    from ``srcdoc`` has no base URL, so ``maidr.js`` cannot fetch the file
    for itself the way it does on a page that loaded it over HTTP.

    Parameters
    ----------
    use_cdn : bool, {"auto"}, or None, optional
        * ``True``: inject a ``<script src="{CDN}">`` tag so the notebook
          loads the CDN copy once.
        * ``False``: read the bundled ``maidr.js`` / ``maidr-math.css``
          from the installed package and embed them as strings on
          ``window``.
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

    Pins its tags to the *bundled* version rather than resolving one.
    ``maidr/__init__.py`` calls this at import, and resolving here would
    put a blocking network request inside ``import maidr`` — before the
    user has run anything, and before the documented opt-outs could be
    applied.  A stalled DNS resolver is not reliably bounded by a socket
    timeout, so that wait has no dependable ceiling.

    The bundled version needs no request and is still immutable, so these
    tags are cache-safe: emitting ``@latest`` here would have left the
    parent document subject to the same seven-day cache lifetime this
    module exists to remove.  Plots themselves render in iframes that
    inject their own ``<script>`` at the *resolved* version, so the first
    ``render()`` / ``save_html()`` is where a lookup happens.

    That split has a known, accepted cost: whenever the bundle is behind
    the published release — the very case :func:`maidr.bundle_status`
    exists to report — a notebook session fetches *two* different
    ``maidr.js`` builds, and this parent-document tag is a prefetch the
    plots do not end up using.  It is still the right trade: the
    alternative is resolving at import time, which is the blocking
    request described above, and the duplicate cost falls away as soon as
    the bundle is refreshed at release time.  Please do not "fix" this by
    resolving here.
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

    from maidr.util.bundle_freshness import (
        warn_bundle_unreadable,
        warn_if_bundle_is_stale,
    )
    from maidr.util.dependencies import (
        MAIDR_JS_FILENAME,
        read_bundled_js,
        read_bundled_math_css,
    )
    from maidr.util.cdn import (
        bundled_cdn_url,
    )

    mode = _resolve_use_cdn(use_cdn)

    if mode is True:
        # CDN-only: a single <script src> reference suffices; nothing is
        # stashed on window.* because iframes inject their own CDN
        # <script> as before.  No stylesheet accompanies it — the script
        # tag's own URL is what maidr.js resolves maidr-math.css against,
        # so the CDN copy of that file is already reachable from here.
        html = f'<script src="{bundled_cdn_url(MAIDR_JS_FILENAME)}"></script>'
    else:
        # ``False`` or ``"auto"``: embed the bundled source strings
        # once in the parent DOM.  For ``"auto"`` we also kick off a
        # CDN <script>/<link> so the parent can use the remote copy
        # opportunistically, but iframes will prefer the local strings
        # because they are guaranteed to resolve.
        try:
            js_source = read_bundled_js()
            math_css_source = read_bundled_math_css()
        except (FileNotFoundError, OSError):
            # Bundle is missing — fall back to CDN so we don't silently
            # break the user's notebook.
            #
            # This branch is reachable with ``mode is False``, where the
            # caller was promised no Python-side network I/O.  Honour
            # that: resolving a version here would issue exactly the
            # request they opted out of, on an install that is already
            # broken.  Emit the unresolved ``@latest`` URL instead, and
            # say why, since silently contacting the CDN under
            # ``use_cdn=False`` is the more surprising outcome.
            # Both modes emit the same markup; only ``False`` has been
            # promised no network I/O, so only it needs telling that its
            # bundle could not be read.
            if mode is False:
                warn_bundle_unreadable()
            html = (
                f'<script src="{bundled_cdn_url(MAIDR_JS_FILENAME)}">'
                f"</script>"
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
            math_css_literal = json.dumps(math_css_source).replace("</", "<\\/")
            cdn_bootstrap = ""
            if mode == "auto":
                cdn_bootstrap = (
                    f'<script src="{bundled_cdn_url(MAIDR_JS_FILENAME)}">'
                    f"</script>"
                )
            html = (
                f"<script>"
                f"window.__maidrJsSource = {js_literal};"
                f"window.__maidrMathCssSource = {math_css_literal};"
                f"</script>"
                f"{cdn_bootstrap}"
            )

    if mode is not True:
        # The bundled source is what we just stashed on ``window``, so
        # tell the user if it has drifted behind the published release.
        # Offline-safe: never resolves over the network by itself.
        warn_if_bundle_is_stale(bundle_is_primary=mode is False)

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


def _resolve_figure(plot: Any) -> Figure | None:
    """
    The figure ``plot`` lives on, resolved once for every entry point.

    ``render``, ``show``, ``save_html`` and ``close`` all need the same
    thing -- the ``Figure`` whose ``Maidr`` holds the registered layers --
    and each used to work it out from :meth:`FigureManager.get_axes` on
    its own. A ``Figure`` is an ``Artist``, so ``get_axes`` answers it
    with ``fig.axes``, a list; three of the four grew a branch that walked
    that list, one ``get_maidr`` lookup per axes, and the fourth did not
    and raised. Walking it also meant the ``plot=None`` and ``plot=fig``
    forms went through a different branch from ``plot=ax``, which is how
    ``clear_fig`` came to be forwarded on one path and not the other, and
    how a figure with no axes at all -- an empty list -- never bound the
    ``Maidr`` and raised ``UnboundLocalError`` where a figure with an
    empty *axes* reached the #443 fallback.

    Parameters
    ----------
    plot : Any
        A matplotlib ``Figure``, ``Axes``, artist or container, or a
        seaborn ``FacetGrid``/``JointGrid``/``PairGrid`` -- anything
        :meth:`FigureManager.get_axes` resolves.

    Returns
    -------
    Figure or None
        The figure, or ``None`` when nothing resolves. A ``Figure`` is
        returned as it is, whether or not it has axes yet, so that
        :meth:`FigureManager.get_maidr` can raise the empty-figure
        ``UnsupportedPlotError`` for it rather than this function guessing.
    """
    if isinstance(plot, Figure):
        return plot
    # A raw list of artists resolves to its first entry's figure: every
    # documented input maps to one figure, so first and last agree.
    ax = FigureManager.get_axes(plot)
    if isinstance(ax, list):
        # A seaborn Grid resolves to every axes of its figure; any one of
        # them names the figure, and the list branch picks the first.
        ax = FigureManager.get_axes(ax)
    return None if ax is None else ax.get_figure()


def _figure_or_raise(plot: Any) -> Figure:
    """The figure for ``plot``, or a ``TypeError`` that names what was passed.

    The failure used to be ``AttributeError: 'NoneType' object has no
    attribute 'get_figure'``, which names maidr's bookkeeping rather than
    the caller's mistake.
    """
    fig = _resolve_figure(plot)
    if fig is None:
        raise TypeError(
            f"maidr cannot find a figure for {plot!r}; pass a matplotlib "
            "Figure, Axes or artist, or a seaborn FacetGrid, JointGrid or "
            "PairGrid"
        )
    return fig


def render(
    plot: Any | None = None,
    use_cdn: bool | Literal["auto"] | None = None,
) -> Tag:
    """
    Render a MAIDR plot to HTML.

    Parameters
    ----------
    plot : Any or None, optional
        The plot object to render. Supports matplotlib/seaborn artists,
        Plotly figures, and Altair chart objects. If None, uses the
        current matplotlib figure.
    use_cdn : bool, {"auto"}, or None, default=None
        * ``True``: load ``maidr.js`` from the public jsDelivr CDN only
          (no offline fallback).
        * ``False``: reference the copy bundled inside the installed
          ``maidr`` package.  Use this in air-gapped environments.
        * ``"auto"``: emit a CDN ``<script>`` with a client-side
          ``onerror`` handler that swaps in the bundled copy when the
          CDN is unreachable.  This is the default mode.  Reachability
          is decided in the browser, but building the URL resolves the
          published version over the network once per process (bounded
          by ``MAIDR_CDN_TIMEOUT``; set ``MAIDR_CDN_VERSION=latest`` to
          skip it).
        * ``None`` (default): use the process-wide default set via
          :func:`set_use_cdn` or the ``MAIDR_USE_CDN`` env var (both
          default to ``"auto"``).

        Altair charts always use the CDN — this argument is not
        plumbed through that adapter, so ``False`` warns rather than
        taking effect (#521).

    Returns
    -------
    htmltools.Tag
        The rendered HTML representation of the plot.
    """
    if _is_altair_chart(plot):
        from maidr.altair import AltairMaidr

        _warn_altair_ignores_use_cdn(use_cdn, stacklevel=3)

        return AltairMaidr(plot).render()

    use_cdn = _resolve_use_cdn(use_cdn)
    if plot is not None and _is_plotly_figure(plot):
        return _get_plotly_maidr(plot).render(use_cdn=use_cdn)

    fig = _figure_or_raise(_get_plot_or_current(plot))
    try:
        maidr = FigureManager.get_maidr(fig)
        return maidr.render(use_cdn=use_cdn)
    except UnsupportedPlotError as error:
        warn_unsupported(error, stacklevel=3)
        return fallback_tag(error.fig, error.message)


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
        The plot object to display. Supports matplotlib/seaborn artists,
        Plotly figures, and Altair chart objects. If None, uses the
        current matplotlib figure.
    renderer : {"auto", "ipython", "browser"}, default "auto"
        The renderer to use for display.
    clear_fig : bool, default True
        Whether to clear the figure after displaying.
    use_cdn : bool, {"auto"}, or None, default=None
        See :func:`render` for the three possible modes.  ``None``
        defers to :func:`get_use_cdn` (the process-wide default).

        The two CDN modes (``True`` and ``"auto"``) resolve the published
        version over the network once per process when building the URL,
        bounded by ``MAIDR_CDN_TIMEOUT``; ``MAIDR_CDN_VERSION`` skips it.
        ``False`` makes no request.  Altair charts always use the CDN —
        this argument is not plumbed through that adapter.

    Returns
    -------
    object
        The display result.
    """
    if _is_altair_chart(plot):
        from maidr.altair import AltairMaidr

        _warn_altair_ignores_use_cdn(use_cdn, stacklevel=3)

        return AltairMaidr(plot).show(renderer)

    use_cdn = _resolve_use_cdn(use_cdn)
    if plot is not None and _is_plotly_figure(plot):
        return _get_plotly_maidr(plot).show(renderer, use_cdn=use_cdn)

    fig = _figure_or_raise(_get_plot_or_current(plot))
    try:
        maidr = FigureManager.get_maidr(fig)
        return maidr.show(renderer, clear_fig=clear_fig, use_cdn=use_cdn)
    except UnsupportedPlotError as error:
        warn_unsupported(error, stacklevel=3)
        return fallback_tag(error.fig, error.message).show()


def save_html(
    plot: Any | None = None,
    file: str | None = None,
    *,
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
        The plot object to save. Supports matplotlib/seaborn artists,
        Plotly figures, and Altair chart objects. If None, uses the
        current matplotlib figure.
    file : str
        The file path where to save the HTML. Required; may be passed
        positionally, as in ``maidr.save_html(plot, "output.html")``, the
        form the getting-started tutorial uses and the form
        :meth:`Maidr.save_html` and its Plotly and Altair counterparts
        take.
    lib_dir : str or None, default "lib"
        Directory name for libraries.
    include_version : bool, default True
        Whether to include version information.
    data_in_svg : bool, default True
        Controls where the MAIDR JSON payload is placed in the HTML or SVG.
    use_cdn : bool, {"auto"}, or None, default=None
        * ``True``: reference the public jsDelivr CDN only (no files
          copied, no offline fallback).
        * ``False``: bundle ``maidr.js`` and its assets into ``lib_dir``
          next to the saved HTML and reference the script with a
          relative path.  The resulting directory is self-contained and
          works without any network access.
        * ``"auto"``: copy the bundle alongside the HTML and emit a
          CDN loader with a client-side ``onerror`` fallback, so the
          HTML works both online and offline.  This is the default mode.
        * ``None`` (default): use the process-wide default (see
          :func:`set_use_cdn` / ``MAIDR_USE_CDN``).  Both default to
          ``"auto"``.

        The two CDN modes (``True`` and ``"auto"``) resolve the published
        version over the network once per process when building the URL,
        bounded by ``MAIDR_CDN_TIMEOUT``; ``MAIDR_CDN_VERSION`` skips it.
        ``False`` makes no request.  Altair charts always use the CDN —
        this argument is not plumbed through that adapter.

    Returns
    -------
    str
        The path to the saved HTML file.

    Raises
    ------
    TypeError
        If ``file`` is not given.
    """
    # `file` has a default only so that it can follow the optional `plot`
    # positionally; it is no less required than it was as a keyword-only
    # argument, and saying so here reads better than the AttributeError a
    # `None` path would raise from inside htmltools.
    if file is None:
        raise TypeError("save_html() missing required argument: 'file'")

    if _is_altair_chart(plot):
        from maidr.altair import AltairMaidr

        _warn_altair_ignores_use_cdn(use_cdn, stacklevel=3)

        return AltairMaidr(plot).save_html(
            file,
            lib_dir=lib_dir,
            include_version=include_version,
            data_in_svg=data_in_svg,
        )

    use_cdn = _resolve_use_cdn(use_cdn)
    if plot is not None and _is_plotly_figure(plot):
        return _get_plotly_maidr(plot).save_html(
            file,
            lib_dir=lib_dir,
            include_version=include_version,
            use_cdn=use_cdn,
        )

    # Resolved to the figure once. The Figure form -- which includes the
    # default, `plt.gcf()` -- used to walk `fig.axes` and build a whole
    # HTML document per axes, keeping only the last: a `subplots(3, 3)`
    # rendered nine times for one file (#694).
    fig = _figure_or_raise(_get_plot_or_current(plot))
    try:
        maidr = FigureManager.get_maidr(fig)
        return maidr.save_html(
            file,
            lib_dir=lib_dir,
            include_version=include_version,
            data_in_svg=data_in_svg,
            use_cdn=use_cdn,
        )
    except UnsupportedPlotError as error:
        # A file still gets written, holding the image and the reason. Raising
        # instead would leave a build step that expected an artefact with
        # nothing on disk and a traceback, which is the worse of the two
        # failures -- and it is what `plt.show()` has always avoided.
        warn_unsupported(error, stacklevel=3)
        return fallback_tag(error.fig, error.message).save_html(file)


def stacked(plot: Axes | BarContainer) -> Maidr:
    ax = FigureManager.get_axes(plot)
    return FigureManager.create_maidr(ax, PlotType.STACKED)


def close(plot: Any | None = None) -> None:
    """
    Close a MAIDR plot and clean up resources.

    Parameters
    ----------
    plot : Any or None, optional
        The plot object to close: a matplotlib ``Figure``, ``Axes`` or
        artist, or a seaborn Grid. If None, uses the current matplotlib
        figure.
    """
    if plot is not None and _is_plotly_figure(plot):
        # For Plotly figures, no FigureManager cleanup needed
        return

    # Nothing resolved is nothing to close: `destroy` already treats an
    # unregistered figure as done, and closing is the one call that should
    # not raise about what it was handed.
    fig = _resolve_figure(_get_plot_or_current(plot))
    if fig is not None:
        FigureManager.destroy(fig)
