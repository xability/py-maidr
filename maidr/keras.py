"""Read the training curves and the graph of a Keras model into maidr.

>>> from maidr.keras import plot_history
>>> history = model.fit(x, y, validation_split=0.2, epochs=20)
>>> maidr.show(plot_history(history))

:func:`plot_history` draws what ``model.fit`` returns, one chart per metric
with its training and validation curves, and :class:`MaidrCallback` keeps an
accessible page of the same charts up to date while the model trains.
:func:`plot_model` draws the model's layers as a directed graph.

``import maidr`` does not import this module, and this module imports Keras
only to subclass its ``Callback``: :func:`plot_history` reads a plain
``History.history`` dictionary as well, and :func:`plot_model` a model's
config or JSON, with no Keras installed.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Mapping
from typing import Any, Iterable

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from maidr.util.caller_warning import warn_at_caller
from maidr.util.graph_drawing import draw_directed_graph
from maidr.util.keras_config import keras_graph

try:
    from keras.callbacks import Callback as _Callback
except ImportError:  # pragma: no cover - depends on the environment
    _Callback = None

__all__ = [
    "MaidrCallback",
    "plot_confusion_matrix",
    "plot_history",
    "plot_model",
    "plot_pr_curve",
]

#: What a metric's two curves are called, in the legend and when read.
TRAINING = "training"
VALIDATION = "validation"

_VALIDATION_PREFIX = "val_"
#: Each curve's color, the same in every chart.
_COLORS = {TRAINING: "C0", VALIDATION: "C1"}
_WIDTH = 7.0
_PANEL_HEIGHT = 3.0

#: One metric's curves: each curve's name, and its epochs and values.
_Curves = dict[str, tuple[np.ndarray, np.ndarray]]


def plot_history(
    history: Any,
    *,
    metrics: Iterable[str] | None = None,
) -> Figure:
    """
    Draw the training curves of a Keras model.

    One chart per metric, stacked top to bottom, with the epoch along the x
    axis and two lines, named ``training`` and ``validation``: the metric on
    the training data, and on the validation data when ``model.fit`` was
    given some. A metric with no validation values, such as the learning
    rate, is one line named for the metric. The loss comes first.

    As in Keras, a metric whose name starts with ``val_`` is read as the
    validation curve of the metric named without it.

    Parameters
    ----------
    history : keras.callbacks.History or dict
        What ``model.fit`` returns, or its ``.history`` dictionary, which
        maps each metric, such as ``"loss"`` or ``"val_accuracy"``, to its
        value at each epoch.
    metrics : iterable of str, optional
        Only these metrics, in this order, named without the ``val_`` prefix,
        such as ``["loss", "accuracy"]``. A metric not in ``history`` is
        warned about.

    Returns
    -------
    matplotlib.figure.Figure
        The charts, ready for :func:`maidr.show`, :func:`maidr.render` or
        :func:`maidr.save_html`. The figure is not managed by pyplot, so
        ``plt.show()`` does not show it.

    Raises
    ------
    TypeError
        If ``history`` is neither a ``History`` nor a dictionary.
    ValueError
        If ``history`` holds no metric that can be drawn.

    Notes
    -----
    Epochs are counted from 1, as Keras counts them when it trains. A value
    that is not finite, such as a loss that became ``NaN``, is a gap in the
    line. A metric whose value is not a single number at each epoch, such
    as a per-class score, is left out with a warning.

    With ``validation_freq`` above 1, Keras records the validation values on
    fewer epochs than the training ones without saying which, so
    ``plot_history`` leaves them out with a warning. :class:`MaidrCallback`
    records the epoch of every value and draws them.

    Examples
    --------
    >>> import maidr
    >>> from maidr.keras import plot_history
    >>> history = {"loss": [0.9, 0.6, 0.5], "val_loss": [1.0, 0.7, 0.65]}
    >>> maidr.save_html(plot_history(history), "training.html")
    """
    logs, epochs = _logs(history)
    return _draw(_curves_from_logs(logs, epochs), metrics)


#: What each normalization divides a cell by, and what its value is then called.
_NORMALIZED = {
    None: "Count",
    "true": "Share of the true class",
    "pred": "Share of the predicted class",
    "all": "Share of all samples",
}


def plot_confusion_matrix(
    y_true: Any,
    y_pred: Any,
    *,
    labels: Iterable[str] | None = None,
    normalize: str | None = None,
    title: str = "Confusion matrix",
) -> Figure:
    """
    Draw a classifier's confusion matrix as a heatmap.

    The true class runs down the rows and the predicted class across the
    columns, so the diagonal is what the model got right. A reader moves
    across a row to hear where one class's samples went.

    Parameters
    ----------
    y_true : array_like
        The true classes: class indices, or one-hot rows.
    y_pred : array_like
        The predicted classes: class indices, or what ``model.predict``
        returns. Rows of class probabilities are read by their largest; a
        single probability per sample, as a sigmoid gives, is the positive
        class from 0.5 up.
    labels : iterable of str, optional
        Each class's name, in index order. By default the class indices.
    normalize : {None, "true", "pred", "all"}, default None
        ``None`` keeps the counts. ``"true"`` divides each row by its total,
        so a cell is the share of that true class predicted as the column's;
        ``"pred"`` divides each column; ``"all"`` divides by every sample.
    title : str, default "Confusion matrix"
        The chart's title.

    Returns
    -------
    matplotlib.figure.Figure
        The heatmap, ready for :func:`maidr.show`, :func:`maidr.render` or
        :func:`maidr.save_html`. Not managed by pyplot.

    Raises
    ------
    ValueError
        If ``y_true`` and ``y_pred`` hold a different number of samples, are
        empty, hold a negative class index or a value that is neither an
        index nor a probability, or ``normalize`` is not one of the above, or
        ``labels`` names fewer classes than the data holds. More labels than
        the data holds are allowed: the classes that never occur are shown
        as empty rows and columns.

    Notes
    -----
    The tutorial way to put a confusion matrix in TensorBoard is to log it as
    an image, which carries no numbers for a screen reader to read. Drawing
    it from the predictions keeps them. NumPy alone computes it.

    Examples
    --------
    >>> import maidr
    >>> from maidr.keras import plot_confusion_matrix
    >>> figure = plot_confusion_matrix(
    ...     y_test, model.predict(x_test), labels=["cat", "dog"], normalize="true"
    ... )
    >>> maidr.show(figure)
    """
    if normalize not in _NORMALIZED:
        raise ValueError(
            f"normalize is None, 'true', 'pred' or 'all', not {normalize!r}"
        )
    true, true_width = _classes(y_true, "y_true")
    predicted, predicted_width = _classes(y_pred, "y_pred")
    if true.size == 0:
        raise ValueError("There are no samples to count.")
    if true.shape != predicted.shape:
        raise ValueError(
            f"y_true holds {true.size} samples and y_pred {predicted.size}; "
            "they are counted in pairs."
        )
    names = None if labels is None else [str(label) for label in labels]
    # A class the rows declare counts even when no sample of it is seen.
    count = max(int(max(true.max(), predicted.max())) + 1, true_width, predicted_width)
    if names is not None:
        if len(names) < count:
            raise ValueError(
                f"labels names {len(names)} classes and the data holds {count}."
            )
        count = len(names)
    matrix = np.zeros((count, count))
    np.add.at(matrix, (true, predicted), 1)
    if normalize == "true":
        matrix = _share(matrix, matrix.sum(axis=1, keepdims=True))
    elif normalize == "pred":
        matrix = _share(matrix, matrix.sum(axis=0, keepdims=True))
    elif normalize == "all":
        matrix = _share(matrix, matrix.sum())
    names = names or [str(index) for index in range(count)]
    side = min(9.0, 3.0 + 0.45 * count)
    fig = Figure(figsize=(side + 1.2, side))
    ax = fig.add_subplot()
    image = ax.imshow(
        matrix,
        cmap="Blues",
        vmin=0,
        z_label=_NORMALIZED[normalize],
    )
    fig.colorbar(image, ax=ax, label=_NORMALIZED[normalize])
    ax.set_xticks(range(count), names, rotation=45 if count > 6 else 0)
    ax.set_yticks(range(count), names)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    if count <= 12:
        brightest = matrix.max() or 1
        for (row, column), value in np.ndenumerate(matrix):
            text = f"{value:.0f}" if normalize is None else f"{value:.4g}"
            color = "white" if value > brightest / 2 else "black"
            ax.text(column, row, text, ha="center", va="center", color=color)
    fig.tight_layout()
    return fig


def plot_pr_curve(
    y_true: Any,
    y_pred: Any,
    *,
    title: str = "Precision-recall curve",
) -> Figure:
    """
    Draw a binary classifier's precision-recall curve from its predictions.

    Parameters
    ----------
    y_true : array_like
        Whether each sample is positive: 1 or ``True`` for the positive
        class, or one-hot rows of two classes.
    y_pred : array_like or dict of str to array_like
        What ``model.predict`` returns: one sigmoid output per sample, as a
        column or flat, or two-class softmax rows, whose second column is the
        positive class's score. Several models' predictions by name draw a
        line each.
    title : str, default "Precision-recall curve"
        The chart's title.

    Returns
    -------
    matplotlib.figure.Figure
        The chart, ready for :func:`maidr.show`, :func:`maidr.render` or
        :func:`maidr.save_html`. Not managed by pyplot.

    Raises
    ------
    ValueError
        If the labels hold no positive sample, or the predictions are not a
        score per sample or two-class rows.

    Notes
    -----
    Each line is named with its average precision and the precision a
    classifier guessing at random reaches -- the share of positives -- which
    is drawn as a dashed line, as :func:`maidr.read_tensorboard_pr_curves`
    draws TensorBoard's PR curves.

    Examples
    --------
    >>> import maidr
    >>> from maidr.keras import plot_pr_curve
    >>> maidr.show(plot_pr_curve(y_test, model.predict(x_test)))
    """
    from maidr.tensorboard.pr_curves import plot_pr_curves

    truth = np.asarray(y_true)
    if truth.ndim == 2 and truth.shape[1] == 2:
        truth = truth[:, 1]
    if isinstance(y_pred, Mapping):
        scores: Any = {str(name): _positive(v) for name, v in y_pred.items()}
    else:
        scores = _positive(y_pred)
    return plot_pr_curves(truth, scores, title=title)


def _positive(values: Any) -> np.ndarray:
    """The positive class's score per sample, from a sigmoid or a 2-class softmax."""
    array = np.asarray(values, dtype=float)
    if array.ndim == 2 and array.shape[1] == 2:
        return array[:, 1]
    if array.ndim == 1 or (array.ndim == 2 and array.shape[1] == 1):
        return array.reshape(-1)
    raise ValueError(
        "A PR curve reads one score per sample or two-class rows, not shape "
        f"{array.shape}; for more classes, pass one class's column."
    )


def _classes(values: Any, name: str) -> tuple[np.ndarray, int]:
    """
    Class indices from indices, one-hot rows, or predicted probabilities.

    Returns the indices and the number of classes the input's shape declares:
    the width of one-hot or probability rows, else 0.
    """
    array = np.asarray(values)
    if array.ndim == 2 and array.shape[1] > 1:
        return array.argmax(axis=1), array.shape[1]
    array = array.reshape(-1)
    if array.dtype.kind == "f" and not np.all(np.mod(array, 1) == 0):
        if np.all((array >= 0) & (array <= 1)):
            return (array >= 0.5).astype(int), 2
        raise ValueError(
            f"{name} holds values that are neither class indices nor "
            "probabilities between 0 and 1."
        )
    indices = array.astype(int)
    if indices.size and indices.min() < 0:
        raise ValueError(f"{name} holds a negative class index, {indices.min()}.")
    return indices, 0


def _share(matrix: np.ndarray, totals: Any) -> np.ndarray:
    """``matrix`` over ``totals``, a cell over an empty total being 0."""
    with np.errstate(invalid="ignore", divide="ignore"):
        shares = np.where(totals > 0, matrix / totals, 0.0)
    return np.round(shares, 4)


def plot_model(
    model: Any,
    *,
    title: str | None = None,
    expand_nested: bool = False,
) -> Figure:
    """
    Draw a Keras model's layers as a directed graph.

    One box per layer, top to bottom from the inputs, with an arrow from each
    layer to the layers called on its output, as ``keras.utils.plot_model``
    draws it. Left and Right walk the layers in the order data flows through
    them; the Inputs and Outputs rotor units follow the arrows, so a skip
    connection is heard as a second input. Each layer is announced with its
    type and, from a built model, its output shape and parameter count.

    Parameters
    ----------
    model : keras.Model, dict or str
        A built ``Sequential`` or functional model, its ``get_config()``
        dictionary, or the JSON ``model.to_json()`` returns. Only the
        config is read, so a model saved as JSON is drawn with no Keras
        installed.
    title : str, optional
        The chart's title. By default the model's name.
    expand_nested : bool, default False
        Whether a model used as a layer, such as a ``Sequential`` block, is
        drawn as its own layers in a frame named for it -- a scope, opened
        with Down and closed with Up -- rather than as one box.

    Returns
    -------
    matplotlib.figure.Figure
        The graph, ready for :func:`maidr.show`, :func:`maidr.render` or
        :func:`maidr.save_html`. The figure is not managed by pyplot, so
        ``plt.show()`` does not show it.

    Raises
    ------
    TypeError
        If ``model`` is not a model, a config or a model's JSON, or is a
        subclassed model whose config Keras cannot give.
    ValueError
        If ``model`` is JSON that does not parse, or a config with no layers.

    Notes
    -----
    The chart is a ``directed_graph``, an experimental type that needs a
    maidr.js release carrying it; an older one shows the drawing without
    reading it. The copy of maidr.js py-maidr bundles does not carry it yet,
    so until it does, the chart is read only from the CDN: online under the
    default ``use_cdn="auto"``, or with ``use_cdn=True``. With
    ``use_cdn=False``, or offline, maidr warns and the chart is not read.

    Both config formats are read: Keras 3's, and Keras 2's (``tf.keras``).
    A layer called more than once is one box fed by everything it was called
    on. A layer's attributes are its type and, where its config has them, its
    units, filters, kernel size, activation and rate; a built model adds its
    output shape and parameter count, which a config alone does not hold.

    Examples
    --------
    >>> import maidr
    >>> from maidr.keras import plot_model
    >>> maidr.save_html(plot_model(model, expand_nested=True), "model.html")
    """
    name, nodes = keras_graph(model, expand_nested=expand_nested)
    if not nodes:
        raise ValueError("maidr found no layers in this model's config.")
    return draw_directed_graph(
        nodes,
        title=title if title is not None else name or "Model",
        node_label="Layer",
        caption="Layer type",
    )


class MaidrCallback(_Callback if _Callback is not None else object):
    """
    Keep an accessible page of a model's training curves while it trains.

    Pass it to ``model.fit(callbacks=[...])``. At the end of every ``every``
    epochs it writes ``path`` again with the charts :func:`plot_history`
    draws, so a reader can open the page during a long run and reload it to
    hear how far the model has come. When training ends, the page is written
    a last time; with no ``path``, the charts are shown in the notebook
    instead, if there is one.

    Parameters
    ----------
    path : str or os.PathLike, optional
        The HTML file to keep up to date. The page is replaced in one step,
        so a reload never meets a half-written file. A page that cannot be
        written, or drawn, is warned about, and training goes on. In multi-worker
        training, give each worker its own path, or the callback to one.
    every : int, default 1
        Write the page every this many epochs.
    metrics : iterable of str, optional
        Only these metrics, in this order, as for :func:`plot_history`.

    Attributes
    ----------
    history : dict of str to list of tuple
        Each metric's values so far, as ``(epoch, value)`` pairs, epochs
        counted from 1. Reset when a new ``model.fit`` begins.

    Raises
    ------
    ImportError
        If Keras is not installed.
    ValueError
        If ``every`` is below 1.

    Examples
    --------
    >>> from maidr.keras import MaidrCallback
    >>> model.fit(x, y, validation_split=0.2, epochs=50,
    ...           callbacks=[MaidrCallback("training.html", every=5)])
    """

    def __init__(
        self,
        path: str | os.PathLike | None = None,
        *,
        every: int = 1,
        metrics: Iterable[str] | None = None,
    ) -> None:
        if _Callback is None:
            raise ImportError(
                "MaidrCallback is a Keras callback, and Keras is not installed: "
                "pip install keras"
            )
        if every < 1:
            raise ValueError(f"every is a number of epochs, at least 1, not {every}")
        super().__init__()
        self.path = None if path is None else os.fspath(path)
        self.every = every
        self.metrics = None if metrics is None else list(metrics)
        self.history: dict[str, list[tuple[int, float]]] = {}
        self._written_at: int | None = None
        self._dropped: set[str] = set()

    def figure(self) -> Figure:
        """
        Draw the curves recorded so far.

        Returns
        -------
        matplotlib.figure.Figure
            The charts :func:`plot_history` would draw for them.
        """
        curves: dict[str, _Curves] = {}
        for key, points in self.history.items():
            if not points:
                continue
            epochs, values = zip(*points)
            name, curve = _split(key)
            curves.setdefault(name, {})[curve] = (
                np.asarray(epochs, dtype=int),
                np.asarray(values, dtype=float),
            )
        return _draw(_ordered(curves), self.metrics)

    def on_train_begin(self, logs: Mapping[str, Any] | None = None) -> None:
        """
        Start a new history, as each ``model.fit`` does.

        Parameters
        ----------
        logs : mapping, optional
            Passed by Keras; not read.
        """
        self.history = {}
        self._written_at = None
        self._dropped = set()

    def on_epoch_end(self, epoch: int, logs: Mapping[str, Any] | None = None) -> None:
        """
        Record the epoch's metrics, and write the page every ``every`` epochs.

        Parameters
        ----------
        epoch : int
            The epoch that ended, counted from 0 as Keras passes it.
        logs : mapping, optional
            Each metric's value at this epoch. A value that is not a single
            number is not recorded, with a warning the first time.
        """
        for key, value in (logs or {}).items():
            number = _number(value)
            if number is not None:
                self.history.setdefault(key, []).append((epoch + 1, number))
            elif key not in self._dropped:
                self._dropped.add(key)
                warn_at_caller(
                    f"'{key}' is not a single number at epoch {epoch + 1}; "
                    "it is not drawn."
                )
        if self.path is not None and (epoch + 1) % self.every == 0:
            self._write(epoch + 1)

    def on_train_end(self, logs: Mapping[str, Any] | None = None) -> None:
        """
        Write the page a last time, or show the charts in a notebook.

        Parameters
        ----------
        logs : mapping, optional
            Passed by Keras; not read.
        """
        if not any(self.history.values()):
            return
        last = max(epoch for points in self.history.values() for epoch, _ in points)
        if self.path is not None:
            if self._written_at != last:
                self._write(last)
            return
        from maidr.util.environment import Environment

        if Environment.is_notebook():
            import maidr

            maidr.show(self.figure())

    def _write(self, epoch: int) -> None:
        """Replace the page with the charts so far, warning if it cannot."""
        import maidr

        directory, name = os.path.split(os.path.abspath(self.path))
        partial = os.path.join(directory, f".{name}.{os.getpid()}.partial")
        figure = None
        try:
            figure = self.figure()
            maidr.save_html(figure, partial)
            os.replace(partial, self.path)
        except Exception as error:
            # The page is an aid to watching the run: a full disk, a
            # directory that went away or a metric that was never logged
            # must not cost the training itself.
            warn_at_caller(
                f"maidr could not write {self.path} after epoch {epoch} ({error}); "
                "training goes on."
            )
            # A failed clean-up must not hide why the write failed.
            with contextlib.suppress(OSError):
                os.remove(partial)
            return
        finally:
            if figure is not None:
                maidr.close(figure)
        self._written_at = epoch


def _logs(history: Any) -> tuple[Mapping[str, Any], list[int] | None]:
    """The metrics of a ``History`` or its dictionary, and its epochs."""
    if isinstance(history, Mapping):
        return history, None
    logs = getattr(history, "history", None)
    if isinstance(logs, Mapping):
        epochs = getattr(history, "epoch", None)
        return logs, list(epochs) if epochs else None
    raise TypeError(
        "plot_history reads what model.fit returns, or its .history "
        f"dictionary, not {type(history).__name__}"
    )


def _curves_from_logs(
    logs: Mapping[str, Any], epochs: list[int] | None
) -> dict[str, _Curves]:
    """
    Each metric's curves, from a ``History.history`` dictionary.

    Parameters
    ----------
    logs : mapping
        Each key's values, one per epoch.
    epochs : list of int or None
        ``History.epoch``, counted from 0, or ``None`` to count from 1.

    Returns
    -------
    dict
        Metric by metric, loss first, each its training and validation curve
        as epochs and values. A key that cannot be drawn is warned about.
    """
    lengths = [len(values) for values in logs.values() if _is_sequence(values)]
    count = len(epochs) if epochs else max(lengths, default=0)
    numbers = np.asarray(epochs, dtype=int) + 1 if epochs else np.arange(1, count + 1)
    curves: dict[str, _Curves] = {}
    if count == 0:
        return curves
    for key, values in logs.items():
        if not _is_sequence(values):
            warn_at_caller(f"'{key}' is not a list of values per epoch; left out.")
            continue
        read = [_number(value) for value in values]
        if any(value is None for value in read):
            warn_at_caller(
                f"'{key}' is not a single number at each epoch; it is left out."
            )
            continue
        if len(read) != count:
            warn_at_caller(
                f"'{key}' has {len(read)} values for {count} epochs, as with "
                "validation_freq above 1, and which epochs they belong to is "
                "not recorded; it is left out. MaidrCallback records them."
            )
            continue
        name, curve = _split(key)
        curves.setdefault(name, {})[curve] = (numbers, np.asarray(read, dtype=float))
    return _ordered(curves)


def _split(key: str) -> tuple[str, str]:
    """``"val_loss"`` is the validation curve of ``"loss"``."""
    if key.startswith(_VALIDATION_PREFIX) and len(key) > len(_VALIDATION_PREFIX):
        return key[len(_VALIDATION_PREFIX) :], VALIDATION
    return key, TRAINING


def _ordered(curves: dict[str, _Curves]) -> dict[str, _Curves]:
    """The loss first, then the rest as Keras logged them; training first."""
    names = sorted(curves, key=lambda name: name != "loss")
    order = (TRAINING, VALIDATION)
    return {
        name: {curve: curves[name][curve] for curve in order if curve in curves[name]}
        for name in names
    }


def _number(value: Any) -> float | None:
    """A value logged at one epoch, as a float, or ``None`` if it is not one."""
    try:
        array = np.asarray(value, dtype=float)
    except Exception:
        # Whatever a backend's tensor raises, such as a GPU tensor NumPy
        # cannot read, costs that value, never the training run.
        return None
    if array.size != 1:
        return None
    return float(array.reshape(()))


def _is_sequence(values: Any) -> bool:
    """Whether ``values`` is a list of values, one per epoch."""
    return not isinstance(values, (str, bytes, Mapping)) and hasattr(values, "__len__")


def _draw(curves: dict[str, _Curves], metrics: Iterable[str] | None) -> Figure:
    """
    Draw one chart per metric, top to bottom, through the patched ``plot``.

    Parameters
    ----------
    curves : dict
        Metric by metric, each its curves as epochs and values.
    metrics : iterable of str or None
        Only these metrics, in this order; one not in ``curves`` is warned
        about.

    Returns
    -------
    matplotlib.figure.Figure
        A figure not managed by pyplot, with its layers registered with maidr.

    Raises
    ------
    ValueError
        If no metric is left to draw.
    """
    if metrics is not None:
        wanted = list(dict.fromkeys(metrics))
        for name in wanted:
            if name not in curves:
                known = ", ".join(f"'{n}'" for n in curves) or "none"
                warn_at_caller(
                    f"No metric '{name}' was logged; the metrics are {known}."
                )
        curves = {name: curves[name] for name in wanted if name in curves}
    if not curves:
        raise ValueError("There is no metric to draw.")
    fig = Figure(figsize=(_WIDTH, _PANEL_HEIGHT * len(curves) + 0.4))
    axes = fig.subplots(len(curves), 1, squeeze=False)[:, 0]
    for ax, (name, lines) in zip(axes, curves.items()):
        # A metric with only its training curve, such as the learning rate,
        # is named for itself: "training" would say it was measured on the
        # training data. One with only its validation curve stays
        # "validation", which is what it was measured on.
        for curve, (epochs, values) in lines.items():
            label = name if lines.keys() == {TRAINING} else curve
            color = _COLORS[curve]
            ax.plot(epochs, values, color=color, marker="o", markersize=3, label=label)
        ax.set_title(name)
        ax.set_xlabel("Epoch")
        ax.set_ylabel(name)
        ax.grid(True, color="#E0E0E0", linewidth=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.legend(frameon=False)
    fig.tight_layout()
    return fig
