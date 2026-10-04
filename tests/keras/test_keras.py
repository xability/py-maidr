"""Keras training curves, drawn by ``maidr.keras.plot_history`` and ``MaidrCallback``.

``plot_history`` reads a plain ``History.history`` dictionary, so most of this
needs no Keras. ``MaidrCallback`` subclasses Keras's ``Callback``; where Keras
is not installed, as in CI, the ``callback`` fixture stands in a bare one, and
``test_a_real_fit_keeps_the_page_up_to_date`` runs a real ``model.fit``
wherever Keras is installed.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
import warnings

import numpy as np
import pytest

import maidr
import maidr.keras
from maidr.core.figure_manager import FigureManager
from maidr.keras import plot_history

HISTORY = {
    "loss": [0.9, 0.6, 0.5, 0.45],
    "accuracy": [0.5, 0.6, 0.7, 0.75],
    "val_loss": [1.0, 0.7, 0.65, 0.66],
    "val_accuracy": [0.45, 0.55, 0.6, 0.62],
    "learning_rate": [1e-3, 1e-3, 5e-4, 5e-4],
}


def _layers(figure) -> list[dict]:
    """Every layer, top to bottom, as the schema maidr.js receives carries it."""
    schema = json.loads(json.dumps(FigureManager.get_maidr(figure)._flatten_maidr()))
    return [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]


def _lines(layer: dict) -> dict[str, list[tuple[float, float | None]]]:
    assert layer["type"] == "line"
    return {line[0]["z"]: [(p["x"], p["y"]) for p in line] for line in layer["data"]}


# -- plot_history -------------------------------------------------------------


def test_one_chart_per_metric_with_training_and_validation_lines():
    layers = _layers(plot_history(HISTORY))
    assert [layer["title"] for layer in layers] == ["loss", "accuracy", "learning_rate"]
    loss = layers[0]
    assert loss["axes"]["x"]["label"] == "Epoch"
    assert loss["axes"]["y"]["label"] == "loss"
    lines = _lines(loss)
    assert list(lines) == ["training", "validation"]
    assert lines["training"] == [(1, 0.9), (2, 0.6), (3, 0.5), (4, 0.45)]
    assert [y for _, y in lines["validation"]] == HISTORY["val_loss"]


def test_a_metric_with_no_validation_is_one_line_named_for_itself():
    (learning_rate,) = [
        layer
        for layer in _layers(plot_history(HISTORY))
        if layer["title"] == "learning_rate"
    ]
    assert list(_lines(learning_rate)) == ["learning_rate"]


def test_a_metric_with_only_validation_values_is_named_validation():
    (layer,) = _layers(plot_history({"val_acc": [0.5, 0.6]}))
    assert layer["title"] == "acc"
    assert list(_lines(layer)) == ["validation"]


def test_a_history_object_is_read_with_its_epochs():
    history = types.SimpleNamespace(history={"loss": [1.0, 0.5]}, epoch=[5, 6])
    (layer,) = _layers(plot_history(history))
    assert _lines(layer)["loss"] == [(6, 1.0), (7, 0.5)]


def test_the_metrics_asked_for_are_drawn_in_that_order():
    layers = _layers(plot_history(HISTORY, metrics=["accuracy", "loss"]))
    assert [layer["title"] for layer in layers] == ["accuracy", "loss"]


def test_a_metric_not_logged_is_warned_about_by_name():
    with pytest.warns(UserWarning, match="No metric 'auc'.*'loss', 'accuracy'"):
        plot_history(HISTORY, metrics=["loss", "auc"])


def test_a_nan_loss_is_a_gap():
    (layer,) = _layers(plot_history({"loss": [1.0, float("nan"), 0.5]}))
    assert [y for _, y in _lines(layer)["loss"]] == [1.0, None, 0.5]


def test_numpy_values_are_read_as_numbers():
    (layer,) = _layers(plot_history({"loss": [np.float32(0.5), np.array(0.25)]}))
    assert [y for _, y in _lines(layer)["loss"]] == [0.5, 0.25]


def test_a_metric_that_is_not_one_number_per_epoch_is_left_out():
    history = {"loss": [1.0, 0.5], "f1": [np.array([0.1, 0.2]), np.array([0.3, 0.4])]}
    with pytest.warns(UserWarning, match="'f1' is not a single number"):
        layers = _layers(plot_history(history))
    assert [layer["title"] for layer in layers] == ["loss"]


def test_validation_on_fewer_epochs_is_left_out_with_a_warning():
    history = {"loss": [1.0, 0.8, 0.6, 0.5], "val_loss": [0.9, 0.7]}
    with pytest.warns(UserWarning, match="'val_loss' has 2 values for 4 epochs"):
        (layer,) = _layers(plot_history(history))
    assert list(_lines(layer)) == ["loss"]


def test_nothing_to_draw_raises():
    with pytest.raises(ValueError, match="no metric"):
        plot_history({})


def test_something_other_than_a_history_raises():
    with pytest.raises(TypeError, match="model.fit"):
        plot_history([0.9, 0.6])


def test_the_figure_is_rendered_like_any_other(tmp_path):
    figure = plot_history(HISTORY)
    out = tmp_path / "training.html"
    maidr.save_html(figure, str(out), use_cdn=False)
    assert "validation" in out.read_text()
    maidr.close(figure)


def test_importing_maidr_does_not_import_maidr_keras():
    import subprocess

    code = "import sys, maidr; print('maidr.keras' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"


# -- MaidrCallback ------------------------------------------------------------


@pytest.fixture
def callback(monkeypatch):
    """``MaidrCallback``, on a bare stand-in for Keras's ``Callback`` if need be."""
    if maidr.keras._Callback is not None:
        yield maidr.keras.MaidrCallback
        return
    keras = types.ModuleType("keras")
    keras.callbacks = types.ModuleType("keras.callbacks")

    class Callback:
        def __init__(self):
            self.model = None

    keras.callbacks.Callback = Callback
    monkeypatch.setitem(sys.modules, "keras", keras)
    monkeypatch.setitem(sys.modules, "keras.callbacks", keras.callbacks)
    module = importlib.reload(maidr.keras)
    yield module.MaidrCallback
    monkeypatch.undo()
    importlib.reload(maidr.keras)


def _train(cb, epochs: int, start: int = 0, validate_every: int = 1) -> None:
    cb.on_train_begin()
    for epoch in range(start, start + epochs):
        logs = {"loss": 1.0 / (epoch + 1), "accuracy": epoch / 10}
        if (epoch + 1) % validate_every == 0:
            logs.update(val_loss=1.1 / (epoch + 1), val_accuracy=epoch / 12)
        cb.on_epoch_end(epoch, logs)
    cb.on_train_end()


def test_the_page_is_written_every_n_epochs_and_at_the_end(callback, tmp_path):
    page = tmp_path / "training.html"
    cb = callback(page, every=2)
    written = []
    cb.on_train_begin()
    for epoch in range(5):
        cb.on_epoch_end(epoch, {"loss": 1.0 / (epoch + 1)})
        written.append(page.exists() and page.stat().st_mtime_ns)
    assert written[0] is False and written[1] and written[2] == written[1]
    assert written[3] and written[4] == written[3]
    cb.on_train_end()
    assert "maidr" in page.read_text()
    (layer,) = _layers(cb.figure())
    assert [x for x, _ in _lines(layer)["loss"]] == [1, 2, 3, 4, 5]
    assert not list(tmp_path.glob(".*partial"))


def test_a_page_that_cannot_be_written_warns_and_training_goes_on(callback, tmp_path):
    # A file where its directory should be: nothing can be written there.
    blocked = tmp_path / "blocked"
    blocked.write_text("")
    cb = callback(blocked / "training.html")
    cb.on_train_begin()
    with pytest.warns(UserWarning, match="could not write.*after epoch 1"):
        cb.on_epoch_end(0, {"loss": 1.0})
    with pytest.warns(UserWarning, match="after epoch 2"):
        cb.on_epoch_end(1, {"loss": 0.5})
    assert [x for x, _ in cb.history["loss"]] == [1, 2]


def test_a_value_numpy_cannot_read_is_skipped_and_training_goes_on(callback):
    class GpuTensor:
        def __array__(self, *args, **kwargs):
            raise RuntimeError("can't convert cuda tensor to numpy")

    cb = callback()
    cb.on_train_begin()
    cb.on_epoch_end(0, {"loss": 1.0, "odd": GpuTensor()})
    assert list(cb.history) == ["loss"]


def test_validation_on_some_epochs_is_placed_on_those_epochs(callback):
    cb = callback()
    _train(cb, 6, validate_every=3)
    loss = _layers(cb.figure())[0]
    assert [x for x, _ in _lines(loss)["validation"]] == [3, 6]
    assert [x for x, _ in _lines(loss)["training"]] == [1, 2, 3, 4, 5, 6]


def test_a_new_fit_starts_a_new_history_counting_from_its_initial_epoch(callback):
    cb = callback()
    _train(cb, 3)
    _train(cb, 2, start=3)
    (loss, _) = _layers(cb.figure())
    assert [x for x, _ in _lines(loss)["training"]] == [4, 5]


def test_without_a_path_and_outside_a_notebook_nothing_is_shown(callback, mocker):
    show = mocker.patch("maidr.show")
    cb = callback()
    _train(cb, 2)
    show.assert_not_called()


def test_without_a_path_in_a_notebook_the_charts_are_shown(callback, mocker):
    mocker.patch("maidr.util.environment.Environment.is_notebook", return_value=True)
    show = mocker.patch("maidr.show")
    cb = callback(metrics=["loss"])
    _train(cb, 2)
    (figure,) = show.call_args.args
    assert [layer["title"] for layer in _layers(figure)] == ["loss"]


def test_every_below_one_raises(callback):
    with pytest.raises(ValueError, match="every"):
        callback(every=0)


def test_a_real_fit_keeps_the_page_up_to_date(tmp_path):
    keras = pytest.importorskip("keras")
    if maidr.keras._Callback is None:
        importlib.reload(maidr.keras)
    rng = np.random.default_rng(0)
    x = rng.normal(size=(64, 3)).astype("float32")
    y = (x.sum(axis=1) > 0).astype("float32")
    model = keras.Sequential(
        [
            keras.Input((3,)),
            keras.layers.Dense(4, "relu"),
            keras.layers.Dense(1, "sigmoid"),
        ]
    )
    model.compile("adam", "binary_crossentropy", metrics=["accuracy"])
    page = tmp_path / "fit.html"
    cb = maidr.keras.MaidrCallback(page)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        history = model.fit(
            x, y, epochs=3, validation_split=0.25, verbose=0, callbacks=[cb]
        )
    assert page.exists()
    from_callback = _layers(cb.figure())
    from_history = _layers(maidr.keras.plot_history(history))
    assert [layer["title"] for layer in from_callback] == [
        layer["title"] for layer in from_history
    ]
    assert _lines(from_callback[0]) == _lines(from_history[0])
    assert list(_lines(from_history[0])) == ["training", "validation"]
