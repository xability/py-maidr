"""How a notebook shows a plain matplotlib figure, which a chart's frame matches.

In a notebook -- JupyterLab, Notebook 7, VS Code, Colab, and the HTML
nbconvert exports from them -- a figure drawn without maidr is shown as the
image matplotlib_inline makes of it: IPython's ``print_figure`` (or
``retina_figure``) with ``InlineBackend.print_figure_kwargs``, in the first of
``InlineBackend.figure_formats`` the frontend shows. A chart in maidr's frame
takes that image's size and shape (:func:`maidr.util.inline_chart.size_like_plain_figure`).

``import maidr`` makes maidr's backend matplotlib's before matplotlib_inline
is loaded, so in most kernels nothing registers the ``InlineBackend``
configuration with the shell, and a ``%config InlineBackend...`` went
nowhere: ``%config`` only reaches what the shell lists. Nor is a display
formatter for a figure registered, which is where a Quarto render reads the
format from. :func:`register_inline_backend` registers the configuration as
matplotlib_inline does, so that ``%config`` reaches it, and changes to it
register the figure's formatter, as they do without maidr.
:func:`notebook_figure_format` then reads the formatter when one is
registered -- the last word, whether ``%config`` or ``set_matplotlib_formats``
set it -- and the configuration when none is.
"""

from __future__ import annotations

import sys
from typing import Any

#: The figure formats in the order a notebook frontend picks one when a figure
#: comes in several: JupyterLab and Notebook 7 rank an SVG over a PNG or JPEG
#: (rendermime ranks 80 and 90), as nbconvert's HTML export does
#: (``display_data_priority``), and a PDF last. ``retina`` is a PNG; with
#: ``png`` as well, IPython registers it over the plain one.
_SHOWN_FIRST = ("svg", "retina", "png", "jpeg", "pdf")

#: matplotlib_inline's other names for two of the formats.
_ALIASES = {"jpg": "jpeg", "png2x": "retina"}

#: What the inline backend uses when nothing is configured.
_DEFAULT: tuple[str, dict[str, Any]] = ("png", {"bbox_inches": "tight"})


def in_notebook_frame(use_iframe: bool) -> bool:
    """Whether a chart rendered now is shown in maidr's frame in a notebook.

    That is a chart ``show()``, ``plt.show()`` or ``render()`` makes in a
    notebook kernel, a Quarto render's included (a page Quarto writes the
    chart into decides that on its own; see
    :func:`maidr.util.inline_chart.inline_applies`). Not one Shiny, Flask,
    Streamlit, Gradio or MLflow puts in a page or frame of its own, though
    the app runs in a notebook, and not one ``save_html`` writes.

    Parameters
    ----------
    use_iframe : bool
        False for a document of its own (``save_html``).

    Returns
    -------
    bool
        True when the chart's frame goes into a notebook's output.
    """
    from maidr.util.environment import Environment
    from maidr.util.inline_chart import in_standalone_document

    return (
        use_iframe
        and not in_standalone_document()
        and Environment.is_notebook()
        and not Environment.is_flask()
        and not Environment.is_shiny()
    )


def _shell() -> Any:
    """The IPython shell, or None, without importing IPython to learn there is none."""
    if sys.modules.get("IPython") is None:
        return None
    try:
        from IPython import get_ipython

        return get_ipython()
    except Exception:
        return None


def register_inline_backend() -> Any:
    """Register matplotlib_inline's ``InlineBackend`` configuration with the shell.

    As matplotlib_inline's ``configure_inline_support`` does when it is the
    backend: the configuration, with the shell's own config (a kernel's
    ``ipython_kernel_config.py``), is listed among the shell's configurables,
    so that ``%config InlineBackend.figure_formats = ...`` and
    ``%config InlineBackend.print_figure_kwargs = ...`` reach it, and knows the
    shell, so that a change registers the figure's display formatter. Nothing
    is registered until something changes: a figure is not given a formatter
    by ``import maidr``.

    Safe to call more than once, and when matplotlib_inline registered it
    already: the configuration is a singleton.

    Returns
    -------
    matplotlib_inline.config.InlineBackend or None
        The configuration, or None outside an IPython shell or without
        matplotlib_inline.
    """
    shell = _shell()
    if shell is None:
        return None
    try:
        from matplotlib_inline.config import InlineBackend

        config = InlineBackend.instance(parent=shell)
        if config.shell is None:
            config.shell = shell
        configurables = shell.configurables
        if config not in configurables:
            configurables.append(config)
    except Exception:
        # A probe must never be why ``import maidr`` or a chart fails.
        return None
    return config


def _registered_formats(shell: Any) -> dict[str, Any]:
    """The kernel's display formatters for a matplotlib figure, by format."""
    from matplotlib.figure import Figure

    names = {
        "image/png": "png",
        "image/svg+xml": "svg",
        "application/pdf": "pdf",
        "image/jpeg": "jpeg",
    }
    found: dict[str, Any] = {}
    for mime, formatter in shell.display_formatter.formatters.items():
        if mime not in names:
            continue
        try:
            printer = formatter.lookup_by_type(Figure)
        except KeyError:
            continue
        # A function, or a ``functools.partial`` of one.
        name = getattr(printer, "__name__", "") or getattr(
            getattr(printer, "func", None), "__name__", ""
        )
        if mime == "image/png" and name == "retina_figure":
            found["retina"] = printer
        else:
            found[names[mime]] = printer
    return found


def _first_shown(formats: Any) -> str | None:
    """The format of several a notebook frontend shows."""
    given = {_ALIASES.get(str(f).lower(), str(f).lower()) for f in formats}
    return next((f for f in _SHOWN_FIRST if f in given), None)


def notebook_figure_format() -> tuple[str, dict[str, Any]]:
    """The format a notebook shows a plain figure in, and its ``savefig`` arguments.

    The display formatter for a figure, when the kernel has one: what
    ``set_matplotlib_formats`` registered, or a ``%config`` registered once
    :func:`register_inline_backend` had run. Its ``keywords`` are the
    arguments IPython's ``print_figure`` is given. Otherwise the
    ``InlineBackend`` configuration's ``figure_formats`` and
    ``print_figure_kwargs``, which are what matplotlib_inline registers the
    formatter with once it is the backend. With several formats, the one
    the frontend shows (see :data:`_SHOWN_FIRST`).

    Returns
    -------
    tuple of (str, dict)
        ``retina``, ``png``, ``jpeg``, ``svg`` or ``pdf``, and the
        arguments; ``("png", {"bbox_inches": "tight"})``, the inline
        backend's defaults, outside a shell or when nothing can be read.
    """
    shell = _shell()
    if shell is None:
        return _DEFAULT[0], dict(_DEFAULT[1])
    try:
        registered = _registered_formats(shell)
    except Exception:
        registered = {}
    shown = _first_shown(registered)
    if shown is not None:
        keywords = getattr(registered[shown], "keywords", None)
        return shown, dict(keywords) if isinstance(keywords, dict) else {}
    config = register_inline_backend()
    if config is None:
        return _DEFAULT[0], dict(_DEFAULT[1])
    try:
        shown = _first_shown(config.figure_formats)
        keywords = dict(config.print_figure_kwargs)
    except Exception:
        return _DEFAULT[0], dict(_DEFAULT[1])
    if shown is None:
        # No format at all: the inline backend shows no image then, and the
        # chart keeps the size of the default one.
        return _DEFAULT[0], dict(_DEFAULT[1])
    return shown, keywords
