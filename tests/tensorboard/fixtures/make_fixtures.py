"""Write the TensorBoard log directories the reader is tested against.

Not run by the tests: the files it writes are checked in, so the tests need
neither TensorFlow nor PyTorch. Run it again by hand, in an environment with
``tensorflow``, ``torch`` and ``tensorboard`` installed, when a writer changes
what it writes::

    python tests/tensorboard/fixtures/make_fixtures.py [name ...]

With names, such as ``tf_histograms``, only those are written again.

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


def keras_histograms(logdir: str) -> None:
    """The ``TensorBoard`` callback with ``histogram_freq=1``: weights per epoch."""
    import keras

    keras.utils.set_random_seed(1)
    rng = np.random.default_rng(1)
    x = rng.normal(size=(128, 4)).astype("float32")
    y = (x[:, 0] > 0).astype("float32")
    model = keras.Sequential(
        [
            keras.Input((4,)),
            keras.layers.Dense(6, "relu"),
            keras.layers.Dense(1, "sigmoid"),
        ]
    )
    model.compile("adam", "binary_crossentropy")
    model.fit(
        x,
        y,
        epochs=6,
        verbose=0,
        callbacks=[
            keras.callbacks.TensorBoard(logdir, histogram_freq=1, write_graph=False)
        ],
    )


def tf_histograms(logdir: str) -> None:
    """``tf.summary.histogram``: a distribution that drifts and widens."""
    import tensorflow as tf

    rng = np.random.default_rng(2)
    writer = tf.summary.create_file_writer(os.path.join(logdir, "run"))
    with writer.as_default():
        for step in range(0, 40, 4):
            values = rng.normal(loc=step / 20, scale=1 + step / 40, size=500)
            tf.summary.histogram("activations", values, step=step)
            tf.summary.histogram("constant", np.full(50, 0.5), step=step)
    writer.close()


def torch_histograms(logdir: str) -> None:
    """PyTorch's ``add_histogram``, which writes the legacy ``histo``."""
    from torch.utils.tensorboard import SummaryWriter

    rng = np.random.default_rng(3)
    writer = SummaryWriter(logdir)
    for step in range(5):
        writer.add_histogram(
            "weights", rng.normal(scale=0.1 * (step + 1), size=300), step
        )
    writer.close()


#: The sessions ``hparams_sweep`` trains: each one's hyperparameters.
HPARAM_SESSIONS = [
    {"learning_rate": 0.1, "optimizer": "sgd", "units": 8, "dropout": True},
    {"learning_rate": 0.01, "optimizer": "adam", "units": 16, "dropout": False},
    {"learning_rate": 0.001, "optimizer": "adam", "units": 32, "dropout": True},
    {"learning_rate": 0.01, "optimizer": "sgd", "units": 32, "dropout": False},
]


def hparams_sweep(logdir: str) -> None:
    """The HParams plugin's own API: an experiment, then a run per session."""
    import tensorflow as tf
    from tensorboard.plugins.hparams import api as hp

    learning_rate = hp.HParam("learning_rate", hp.RealInterval(0.0001, 0.5))
    optimizer = hp.HParam("optimizer", hp.Discrete(["adam", "sgd"]))
    units = hp.HParam("units", hp.Discrete([8, 16, 32]))
    dropout = hp.HParam("dropout", hp.Discrete([False, True]))
    with tf.summary.create_file_writer(logdir).as_default():
        hp.hparams_config(
            hparams=[learning_rate, optimizer, units, dropout],
            metrics=[
                hp.Metric("accuracy", display_name="Accuracy"),
                hp.Metric("loss", group="validation", display_name="Validation loss"),
            ],
        )
    for index, values in enumerate(HPARAM_SESSIONS):
        session = os.path.join(logdir, f"session_{index}")
        accuracy = 0.6 + 0.08 * index - 0.4 * values["learning_rate"]
        with tf.summary.create_file_writer(session).as_default():
            hp.hparams(values, trial_id=f"session_{index}")
            for step in range(3):
                tf.summary.scalar("accuracy", accuracy - 0.1 * (2 - step), step=step)
        with tf.summary.create_file_writer(
            os.path.join(session, "validation")
        ).as_default():
            for step in range(3):
                tf.summary.scalar("loss", 1.0 - accuracy + 0.05 * (2 - step), step=step)


def hparams_view(logdir: str) -> dict:
    """What was written: each session's hyperparameters and final metrics."""
    view = {}
    for index, values in enumerate(HPARAM_SESSIONS):
        accuracy = 0.6 + 0.08 * index - 0.4 * values["learning_rate"]
        view[f"session_{index}"] = {
            "hparams": values,
            "metrics": {"accuracy": accuracy, "validation/loss": 1.0 - accuracy},
        }
    return view


def torch_embedding(logdir: str) -> None:
    """PyTorch's ``add_embedding``: vectors and labels as TSV, three clusters."""
    import torch
    from torch.utils.tensorboard import SummaryWriter

    rng = np.random.default_rng(4)
    centers = rng.normal(scale=4.0, size=(3, 8))
    vectors = np.concatenate([center + rng.normal(size=(20, 8)) for center in centers])
    labels = [name for name in ("cat", "dog", "bird") for _ in range(20)]
    writer = SummaryWriter(logdir)
    writer.add_embedding(
        torch.tensor(vectors, dtype=torch.float32),
        metadata=[[label, str(i)] for i, label in enumerate(labels)],
        metadata_header=["label", "index"],
        tag="animals",
    )
    writer.close()


def embedding_view(logdir: str) -> dict:
    """What was written: each embedding's vectors and labels."""
    rng = np.random.default_rng(4)
    centers = rng.normal(scale=4.0, size=(3, 8))
    vectors = np.concatenate([center + rng.normal(size=(20, 8)) for center in centers])
    labels = [name for name in ("cat", "dog", "bird") for _ in range(20)]
    return {
        "animals": {"vectors": vectors.astype(np.float32).tolist(), "labels": labels}
    }


def torch_pr_curves(logdir: str) -> None:
    """PyTorch's ``add_pr_curve``: two classifiers, one far better, at two steps."""
    from torch.utils.tensorboard import SummaryWriter

    rng = np.random.default_rng(5)
    labels = rng.random(400) < 0.3
    for run, noise in (("good", 0.15), ("poor", 0.45)):
        writer = SummaryWriter(os.path.join(logdir, run))
        for step in (0, 10):
            scores = np.clip(
                labels * 0.6 + 0.2 + rng.normal(scale=noise, size=400), 0, 1
            )
            writer.add_pr_curve("positive", labels, scores, global_step=step)
        writer.close()


def tensorboard_view(logdir: str, plugin: str = "scalars") -> dict:
    """
    What TensorBoard reads: run -> tag -> [[step, wall_time, value], ...].

    A scalar's value is a number, a histogram's its buckets as a list of
    ``[left, right, count]``.
    """
    from tensorboard.backend.event_processing import plugin_event_multiplexer
    from tensorboard.util import tensor_util

    mux = plugin_event_multiplexer.EventMultiplexer(tensor_size_guidance={plugin: 0})
    mux.AddRunsFromDirectory(logdir)
    mux.Reload()
    view: dict = {}
    for run, tags in sorted(mux.PluginRunToTagToContent(plugin).items()):
        for tag in sorted(tags):
            view.setdefault(run, {})[tag] = [
                [e.step, e.wall_time, tensor_util.make_ndarray(e.tensor_proto).tolist()]
                for e in mux.Tensors(run, tag)
            ]
    return view


def distributions_view(expected: dict) -> dict:
    """
    What TensorBoard's Distributions dashboard draws from the histograms read:
    run -> tag -> [[step, [value at each of its nine basis points]], ...].
    """
    from tensorboard.plugins.distribution import compressor

    return {
        run: {
            tag: [
                [step, [value for _, value in compressor.compress_histogram(buckets)]]
                for step, _, buckets in events
            ]
            for tag, events in tags.items()
        }
        for run, tags in expected.items()
    }


#: Each log directory: what writes it, and the plugin it is read for.
WRITERS = {
    "keras": (keras_fit, "scalars"),
    "tf_summary": (tf_summary, "scalars"),
    "torch": (torch_writer, "scalars"),
    "keras_histograms": (keras_histograms, "histograms"),
    "tf_histograms": (tf_histograms, "histograms"),
    "torch_histograms": (torch_histograms, "histograms"),
    "hparams_sweep": (hparams_sweep, "hparams"),
    "torch_embedding": (torch_embedding, "projector"),
    "torch_pr_curves": (torch_pr_curves, "pr_curves"),
}


def main(names: list[str]) -> None:
    """Write the log directories named, or all of them."""
    for name in names or WRITERS:
        write, plugin = WRITERS[name]
        logdir = os.path.join(HERE, name)
        shutil.rmtree(logdir, ignore_errors=True)
        write(logdir)
        if plugin == "hparams":
            expected = hparams_view(logdir)
        elif plugin == "projector":
            expected = embedding_view(logdir)
        else:
            expected = tensorboard_view(logdir, plugin)
        with open(os.path.join(HERE, f"{name}.expected.json"), "w") as out:
            # A histogram holds a few hundred numbers a step: one line each
            # would make a reviewable diff of every regeneration impossible.
            indent = 1 if plugin in ("scalars", "hparams") else None
            json.dump(_finite(expected), out, indent=indent, allow_nan=False)
            out.write("\n")
        if plugin == "histograms":
            path = os.path.join(HERE, f"{name}.distributions.json")
            with open(path, "w") as out:
                json.dump(_finite(distributions_view(expected)), out, allow_nan=False)
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
    import sys

    main(sys.argv[1:])
