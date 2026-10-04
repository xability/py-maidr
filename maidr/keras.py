"""Read the training curves of a Keras model into maidr.

>>> from maidr.keras import plot_history
>>> history = model.fit(x, y, validation_split=0.2, epochs=20)
>>> maidr.show(plot_history(history))

:func:`plot_history` draws what ``model.fit`` returns, one chart per metric
with its training and validation curves, and :class:`MaidrCallback` keeps an
accessible page of the same charts up to date while the model trains.

``import maidr`` does not import this module, and this module imports Keras
only to subclass its ``Callback``: :func:`plot_history` reads a plain
``History.history`` dictionary as well, with no Keras installed.
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

try:
    from keras.callbacks import Callback as _Callback
except ImportError:  # pragma: no cover - depends on the environment
    _Callback = None

__all__ = ["MaidrCallback", "plot_history"]

#: What a metric's two curves are called, in the legend and when read.
TRAINING = "training"
VALIDATION = "validation"

_VALIDATION_PREFIX = "val_"
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
        partial = os.path.join(directory, f".{name}.partial")
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
        for color, (curve, (epochs, values)) in zip(("C0", "C1"), lines.items()):
            label = name if lines.keys() == {TRAINING} else curve
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
