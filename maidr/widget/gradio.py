"""Gradio integration for MAIDR.

Provides :func:`render_maidr`, which turns a chart into the markup of an
accessible chart for a ``gr.HTML`` component, and :func:`output_maidr`,
which makes that component.

Requires the optional ``gradio`` extra::

    pip install "maidr[gradio]"

Notes
-----
``gr.HTML`` places its value with ``innerHTML``, where a ``<script>`` does
not run, so the chart cannot be placed on the page directly. It is placed in
an iframe whose ``srcdoc`` carries the chart and ``maidr.js``, the frame a
notebook gets: named after the chart, sized to it as maidr's braille and text
panels open, and allowed the Bluetooth and serial access a refreshable
tactile display needs. A ``srcdoc`` frame shares the app's origin, so maidr
keeps its settings there as it does on any page.

Measured on Gradio 6.29 in Chromium: the frame's chart is reached with Tab,
its arrow keys move through the data and ``b`` turns braille on, both in a
chart placed when the app is built and in one an event handler returns.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from htmltools import HTML, tags

from maidr.util.iframe_utils import wrap_in_iframe_matplotlib

#: Accepted by ``use_cdn``; ``None`` defers to :func:`maidr.get_use_cdn`.
UseCdn = Optional[Union[bool, Literal["auto"]]]


def render_maidr(plot: Any, *, use_cdn: UseCdn = None) -> str:
    """
    Return the markup of an accessible chart, for a ``gr.HTML`` component.

    Use it as the component's value, or return it from an event handler
    whose output is one.

    Parameters
    ----------
    plot : Any
        The chart -- a matplotlib or seaborn artist, a Plotly ``Figure``, a
        Bokeh figure or layout, an Altair chart, or a chart a py-maidr
        reader returned, such as :func:`maidr.read_wandb_history`'s.
        Required: Gradio runs event handlers on separate threads, so
        matplotlib's current figure may be another user's by the time it
        would be read.
    use_cdn : bool, {"auto"}, or None, default None
        Where the chart loads ``maidr.js`` from; see :func:`maidr.render`.
        ``False`` puts the script, about 2 MB, inside every chart, so an app
        without network access still works. ``None`` defers to
        :func:`maidr.get_use_cdn`. Prefer this argument to
        :func:`maidr.set_use_cdn`, which changes what every user's handler
        renders.

    Returns
    -------
    str
        An ``<iframe>`` element whose ``srcdoc`` is the chart.

    Raises
    ------
    TypeError
        If ``plot`` is ``None``.

    Examples
    --------
    >>> import gradio as gr
    >>> import matplotlib.pyplot as plt
    >>> from maidr.widget.gradio import render_maidr
    >>>
    >>> def bars(n):
    ...     fig, ax = plt.subplots()
    ...     ax.bar(range(n), range(1, n + 1))
    ...     return render_maidr(ax)
    >>>
    >>> with gr.Blocks() as demo:
    ...     n = gr.Slider(2, 10, value=4, step=1, label="Bars")
    ...     chart = gr.HTML(bars(4))
    ...     n.change(bars, n, chart)
    """
    if plot is None:
        raise TypeError(
            "render_maidr() takes the chart to render; matplotlib's current "
            "figure is shared by every user of a Gradio app, so it is not "
            "read in its place."
        )
    return _markup(plot, use_cdn, stacklevel=5)


def output_maidr(plot: Any = None, *, use_cdn: UseCdn = None, **kwargs: Any) -> Any:
    """
    Make a ``gr.HTML`` component holding an accessible chart.

    Parameters
    ----------
    plot : Any, optional
        The chart to show, as for :func:`render_maidr`. ``None`` leaves the
        component empty, for an event handler to fill with
        :func:`render_maidr`.
    use_cdn : bool, {"auto"}, or None, default None
        As for :func:`render_maidr`.
    **kwargs
        Passed on to ``gr.HTML``, such as ``label`` or ``elem_id``.

    Returns
    -------
    gradio.HTML
        The component, placed where it is made inside ``gr.Blocks``.

    Raises
    ------
    ImportError
        If Gradio is not installed.

    Examples
    --------
    >>> import gradio as gr
    >>> from maidr.widget.gradio import output_maidr
    >>>
    >>> with gr.Blocks() as demo:
    ...     output_maidr(fig)
    """
    try:
        import gradio as gr
    except ImportError as error:
        from maidr.widget._extras import missing_extra_error

        raise missing_extra_error(error, "gradio", "gradio") from error

    value = None if plot is None else _markup(plot, use_cdn, stacklevel=5)
    return gr.HTML(value, **kwargs)


def _markup(plot: Any, use_cdn: UseCdn, stacklevel: int) -> str:
    """The chart's frame, a warning pointing ``stacklevel`` frames out."""
    # The Streamlit integration's render, which inlines the bundle when
    # ``use_cdn`` is False and warns when a chart cannot honor that. Both
    # embed one chart in one frame, and both need the chart's title to name
    # it. The Streamlit-specific warning it raises is for ``plot is None``,
    # which neither caller here passes.
    from maidr.widget.streamlit import _render

    html, title = _render(plot, use_cdn, stacklevel=stacklevel)
    return str(wrap_in_iframe_matplotlib(tags.div(HTML(html)), title))


__all__ = ["output_maidr", "render_maidr"]
