"""Write the TensorBoard log directories the reader is tested against.

Not run by the tests: the files it writes are checked in, so the tests need
neither TensorFlow nor PyTorch. Run it again by hand, in an environment with
``tensorflow``, ``torch`` and ``tensorboard`` installed, when a writer changes
what it writes::

    python tests/tensorboard/fixtures/make_fixtures.py

Each log directory is written by the library a user would write it with, and
``expected.json`` beside it records what TensorBoard itself reads from it --
through its own ``EventMultiplexer``, which is what its Scalars dashboard
plots -- so the tests compare maidr's reader against TensorBoard rather than
against a writer of maidr's own.
"""

from __future__ import annotations

import json
import os
import shutil

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def keras_fit(logdir: str) -> None:
    """``model.fit`` with the ``TensorBoard`` callback: train and validation."""
    import keras

    keras.utils.set_random_seed(0)
    rng = np.random.default_rng(0)
    x = rng.normal(size=(256, 4)).astype("float32")
    y = (x @ np.array([1.0, -2.0, 0.5, 0.0]) > 0).astype("float32")
    model = keras.Sequential(
        [
            keras.Input((4,)),
            keras.layers.Dense(8, "relu"),
            keras.layers.Dense(1, "sigmoid"),
        ]
    )
    model.compile("adam", "binary_crossentropy", metrics=["accuracy"])
    model.fit(
        x,
        y,
        epochs=12,
        batch_size=32,
        validation_split=0.25,
        verbose=0,
        callbacks=[
            keras.callbacks.TensorBoard(
                logdir, histogram_freq=0, write_graph=False, update_freq="epoch"
            )
        ],
    )


def tf_summary(logdir: str) -> None:
    """``tf.summary.scalar`` in two runs, one with a NaN and a gap in steps."""
    import tensorflow as tf

    for run, rate in (("lr_0.1", 0.1), ("lr_0.01", 0.01)):
        writer = tf.summary.create_file_writer(os.path.join(logdir, run))
        with writer.as_default():
            for step in range(0, 60, 3):
                loss = float(np.exp(-rate * step) + 0.05 * np.sin(step))
                if run == "lr_0.01" and step == 30:
                    loss = float("nan")
                tf.summary.scalar("loss", loss, step=step)
                tf.summary.scalar("metrics/lr", rate, step=step)
        writer.close()


def torch_writer(logdir: str) -> None:
    """PyTorch's ``SummaryWriter``, which writes the legacy ``simple_value``."""
    from torch.utils.tensorboard import SummaryWriter

    writer = SummaryWriter(logdir)
    for step in range(25):
        writer.add_scalar("Loss/train", 1.0 / (step + 1), step)
        writer.add_scalar("Loss/test", 1.2 / (step + 1) + 0.01, step)
    writer.close()


def tensorboard_view(logdir: str) -> dict:
    """What TensorBoard reads: run -> tag -> [[step, wall_time, value], ...]."""
    from tensorboard.backend.event_processing import plugin_event_multiplexer
    from tensorboard.util import tensor_util

    mux = plugin_event_multiplexer.EventMultiplexer(tensor_size_guidance={"scalars": 0})
    mux.AddRunsFromDirectory(logdir)
    mux.Reload()
    view: dict = {}
    for run, tags in sorted(mux.PluginRunToTagToContent("scalars").items()):
        for tag in sorted(tags):
            view.setdefault(run, {})[tag] = [
                [e.step, e.wall_time, float(tensor_util.make_ndarray(e.tensor_proto))]
                for e in mux.Tensors(run, tag)
            ]
    return view


def main() -> None:
    for name, write in (
        ("keras", keras_fit),
        ("tf_summary", tf_summary),
        ("torch", torch_writer),
    ):
        logdir = os.path.join(HERE, name)
        shutil.rmtree(logdir, ignore_errors=True)
        write(logdir)
        expected = tensorboard_view(logdir)
        with open(os.path.join(HERE, f"{name}.expected.json"), "w") as out:
            json.dump(_finite(expected), out, indent=1, allow_nan=False)
            out.write("\n")


def _finite(value):
    """``value`` with each NaN written as ``"nan"``, which JSON has no number for."""
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    if isinstance(value, float) and value != value:
        return "nan"
    return value


if __name__ == "__main__":
    main()
