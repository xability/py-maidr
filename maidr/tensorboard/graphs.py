"""Read the Keras model graph of a TensorBoard log directory as directed graphs.

TensorBoard's Graphs dashboard draws, under its *Keras* tag, the model
Keras's ``TensorBoard`` callback logged with ``write_graph=True``: its layers
and what each is called on. The callback logs the model's config, the JSON
``model.to_json()`` returns, so it is drawn just as
:func:`maidr.keras.plot_model` draws a model, and needs no Keras.

The op-level graph TensorFlow can log beside it (``Event.graph_def``) is not
read: it is the model's every operation, hundreds of nodes for a few layers,
and Keras 3's callback does not write it.
"""

from __future__ import annotations

import os
from typing import Iterable

from maidr.tensorboard.events import KERAS_MODEL_PLUGIN
from maidr.tensorboard.logdir import TensorBoardChart, load
from maidr.util.caller_warning import warn_at_caller
from maidr.util.graph_drawing import draw_directed_graph
from maidr.util.keras_config import keras_graph

__all__ = ["read_tensorboard_graph"]


def read_tensorboard_graph(
    logdir: str | os.PathLike,
    *,
    runs: Iterable[str] | None = None,
    expand_nested: bool = False,
) -> list[TensorBoardChart]:
    """
    Read the Keras model graphs of a TensorBoard log directory.

    One chart per run that logged a model, as TensorBoard's Graphs dashboard
    draws it under the *Keras* tag: one box per layer, top to bottom from the
    inputs, with an arrow from each layer to the layers called on its output.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with (``--logdir``), such
        as the ``log_dir`` of Keras's ``TensorBoard`` callback with
        ``write_graph=True``, its default.
    runs : iterable of str, optional
        Only these runs. Keras logs the model in its ``train`` run.
    expand_nested : bool, default False
        Whether a model used as a layer is drawn as its own layers, in a
        scope named for it, rather than as one box.

    Returns
    -------
    list of TensorBoardChart
        One per run, tagged ``keras``. Pass one to :func:`maidr.show`,
        :func:`maidr.render` or :func:`maidr.save_html`.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` is not a directory.

    Notes
    -----
    The chart is a ``directed_graph``, an experimental type. A run that
    logged its model more than once is drawn from the last. A model logged as
    something other than a Keras config, such as a TensorFlow op graph, is not
    read.

    Examples
    --------
    >>> import maidr
    >>> (graph,) = maidr.read_tensorboard_graph("logs/fit")
    >>> maidr.save_html(graph, "model.html")
    """
    logged = load(logdir, KERAS_MODEL_PLUGIN, tags=None, runs=runs)
    charts = []
    for tag, by_run in logged.items():
        for run, (_, _, values) in by_run.items():
            try:
                name, nodes = keras_graph(values[-1], expand_nested=expand_nested)
            except (TypeError, ValueError) as error:
                warn_at_caller(
                    f"maidr could not read the model logged as '{tag}' in run "
                    f"'{run}'; it is left out: {error}"
                )
                continue
            if not nodes:
                warn_at_caller(
                    f"The model logged as '{tag}' in run '{run}' has no layers; "
                    "it is left out."
                )
                continue
            title = name or "Model"
            title = title if run == "." else f"{title} ({run})"
            figure = draw_directed_graph(
                nodes, title=title, node_label="Layer", caption="Layer type"
            )
            charts.append(TensorBoardChart(tag, (run,), figure))
    if not charts:
        warn_at_caller(f"maidr found no Keras model graph in {os.fspath(logdir)}.")
    return charts
