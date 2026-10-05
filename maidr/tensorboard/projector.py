"""Read the embeddings of TensorBoard's Embedding Projector as a 2D scatter.

The Projector shows high-dimensional vectors -- word embeddings, a layer's
activations -- projected to two or three dimensions, coloured by a label from
their metadata, so one can see which classes the model keeps apart. maidr
reads the projection in two dimensions, one scatter layer per label, so a
reader can hear where each class sits and which ones overlap. A 3D projection
has no maidr reading and is not offered.

The vectors are read as the log directory's ``projector_config.pbtxt`` says:
from the TSV file its ``tensor_path`` names, which PyTorch's ``add_embedding``
writes, or, with TensorFlow installed, from the checkpoint variable its
``tensor_name`` names, which the Keras and TensorFlow tutorials write.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field

import numpy as np
from matplotlib.figure import Figure

from maidr.tensorboard.logdir import TensorBoardChart
from maidr.util.metric_chart import thin
from maidr.util.caller_warning import warn_at_caller

__all__ = [
    "Embedding",
    "load_embeddings",
    "project",
    "read_tensorboard_projector",
]

#: Points drawn per chart at most; beyond it the points are evenly sampled.
DEFAULT_MAX_POINTS = 2000

_CONFIG = "projector_config.pbtxt"
_BLOCK = re.compile(r"embeddings\s*\{", re.MULTILINE)
_FIELD = re.compile(r'^\s*(\w+)\s*:\s*"((?:[^"\\]|\\.)*)"', re.MULTILINE)


@dataclass(frozen=True, eq=False)
class Embedding:
    """
    One embedding of a Projector log directory.

    Attributes
    ----------
    name : str
        The ``tensor_name`` it was logged under.
    vectors : numpy.ndarray
        One row per point, shape ``(points, dimensions)``.
    metadata : dict of str to list of str
        Each metadata column, one value per point, such as ``{"label": [...]}``.
        A metadata file with one column and no header is called ``label``.
    """

    name: str
    vectors: np.ndarray = field(repr=False)
    metadata: dict[str, list[str]] = field(default_factory=dict, repr=False)


def load_embeddings(logdir: str | os.PathLike) -> list[Embedding]:
    """
    Read the embeddings a Projector log directory configures.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory holding ``projector_config.pbtxt``.

    Returns
    -------
    list of Embedding
        One per ``embeddings`` block of the config whose vectors could be
        read. One that cannot be -- a checkpoint without TensorFlow
        installed, or a file that is missing -- is warned about and left out.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` holds no ``projector_config.pbtxt``.
    """
    path = os.fspath(logdir)
    config = os.path.join(path, _CONFIG)
    if not os.path.isfile(config):
        raise FileNotFoundError(
            f"maidr reads the Embedding Projector from {_CONFIG}, and {path} has "
            "none."
        )
    with open(config, encoding="utf-8") as stream:
        text = stream.read()
    checkpoint = _top_level(text, "model_checkpoint_path")
    embeddings = []
    for block in _blocks(text):
        name = block.get("tensor_name", "embedding")
        vectors = _vectors(path, block, checkpoint)
        if vectors is None:
            continue
        metadata = {}
        if "metadata_path" in block:
            metadata = _metadata(
                os.path.join(path, block["metadata_path"]), len(vectors)
            )
            short = [k for k, column in metadata.items() if len(column) < len(vectors)]
            if short:
                warn_at_caller(
                    f"'{name}' has {len(vectors)} points and its metadata labels "
                    f"fewer; the points without one are labelled ''."
                )
                for key in short:
                    metadata[key] += [""] * (len(vectors) - len(metadata[key]))
        embeddings.append(Embedding(name, vectors, metadata))
    return embeddings


def project(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Project vectors onto their first two principal components.

    Parameters
    ----------
    vectors : numpy.ndarray
        One row per point.

    Returns
    -------
    coordinates : numpy.ndarray
        Shape ``(points, 2)``.
    explained : numpy.ndarray
        The share of the variance each component explains.
    """
    centered = vectors - vectors.mean(axis=0)
    _, singular, components = np.linalg.svd(centered, full_matrices=False)
    variance = singular**2
    total = variance.sum() or 1.0
    components = components[:2]
    if components.shape[0] < 2:
        components = np.vstack([components, np.zeros_like(components)])[:2]
        variance = np.concatenate([variance, [0.0]])
    return centered @ components.T, variance[:2] / total


def read_tensorboard_projector(
    logdir: str | os.PathLike,
    *,
    label: str | None = None,
    coordinates: np.ndarray | None = None,
    max_points: int | None = DEFAULT_MAX_POINTS,
) -> list[TensorBoardChart]:
    """
    Read the embeddings of a Projector log directory as 2D scatter plots.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory holding ``projector_config.pbtxt``, such as the
        ``log_dir`` of PyTorch's ``SummaryWriter.add_embedding``.
    label : str, optional
        The metadata column the points are grouped by. By default ``label``
        when there is one, else the first column.
    coordinates : numpy.ndarray, optional
        Two coordinates per point to draw instead of the principal
        components, such as a t-SNE or UMAP projection computed elsewhere.
        Only for a directory holding one embedding.
    max_points : int or None, default 2000
        At most this many points per chart, evenly sampled, with a warning.

    Returns
    -------
    list of TensorBoardChart
        One per embedding, tagged with its ``tensor_name``; ``runs`` names
        the label groups, in the order their layers are drawn.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` holds no ``projector_config.pbtxt``.
    ValueError
        If ``coordinates`` is not two per point, or the directory holds more
        than one embedding for it.

    Notes
    -----
    Each label group is one scatter layer, named in the legend, so a reader
    moves between classes with Page Up and Page Down and along one class's
    points with the arrow keys. The axes are the first two principal
    components, each named with the share of the variance it explains.

    Examples
    --------
    >>> import maidr
    >>> (chart,) = maidr.read_tensorboard_projector("runs/embeddings")
    >>> maidr.show(chart)
    """
    embeddings = load_embeddings(logdir)
    if coordinates is not None:
        coordinates = np.asarray(coordinates, dtype=float)
        if len(embeddings) != 1:
            raise ValueError(
                "coordinates are for one embedding, and the directory holds "
                f"{len(embeddings)}."
            )
        if coordinates.shape != (len(embeddings[0].vectors), 2):
            raise ValueError(
                "coordinates need two values for each of the "
                f"{len(embeddings[0].vectors)} points, not shape {coordinates.shape}."
            )
    if not embeddings:
        warn_at_caller(
            f"maidr found no embedding it could read in {os.fspath(logdir)}."
        )
    charts = []
    for embedding in embeddings:
        if coordinates is not None:
            points, axes = coordinates, ("Dimension 1", "Dimension 2")
        else:
            points, explained = project(embedding.vectors)
            axes = tuple(
                f"Component {i + 1} ({share:.1%} of variance)"
                for i, share in enumerate(explained)
            )
        groups = _groups(embedding, label)
        keep = thin(len(points), max_points)
        if len(keep) < len(points):
            warn_at_caller(
                f"'{embedding.name}' has {len(points)} points; {len(keep)} of them, "
                "evenly sampled, are drawn."
            )
        figure, names = _draw(embedding.name, points[keep], groups[keep], axes)
        charts.append(TensorBoardChart(embedding.name, names, figure))
    return charts


def _groups(embedding: Embedding, label: str | None) -> np.ndarray:
    """Each point's group: its value in the label column, or one group."""
    columns = embedding.metadata
    if label is not None and label not in columns:
        known = ", ".join(f"'{name}'" for name in columns) or "none"
        warn_at_caller(
            f"'{embedding.name}' has no metadata column '{label}'; its columns are "
            f"{known}."
        )
        label = None
    if label is None and columns:
        label = "label" if "label" in columns else next(iter(columns))
    if label is None:
        return np.array(["points"] * len(embedding.vectors), dtype=object)
    return np.array(columns[label], dtype=object)


def _draw(
    name: str, points: np.ndarray, groups: np.ndarray, axes: tuple[str, ...]
) -> tuple[Figure, tuple[str, ...]]:
    """One scatter per group, in order of first appearance."""
    fig = Figure(figsize=(7.0, 5.5))
    ax = fig.add_subplot()
    names = tuple(dict.fromkeys(str(group) for group in groups))
    for group in names:
        mask = groups == group
        ax.scatter(points[mask, 0], points[mask, 1], s=14, alpha=0.8, label=group)
    ax.set_xlabel(axes[0])
    ax.set_ylabel(axes[1])
    ax.set_title(name)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if len(names) > 1:
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)
    fig.tight_layout()
    return fig, names


def _blocks(text: str) -> list[dict[str, str]]:
    """The fields of each ``embeddings { ... }`` block of a config."""
    blocks = []
    for match in _BLOCK.finditer(text):
        depth, end = 1, match.end()
        while end < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[end], 0)
            end += 1
        body = text[match.end() : end - 1]
        # Nested messages, such as a sprite, are not this block's own fields.
        body = re.sub(r"\w+\s*\{[^{}]*\}", "", body)
        blocks.append({key: _unescape(value) for key, value in _FIELD.findall(body)})
    return blocks


def _top_level(text: str, key: str) -> str | None:
    """A field of the config outside its ``embeddings`` blocks."""
    outside = _BLOCK.split(text)[0]
    for name, value in _FIELD.findall(outside):
        if name == key:
            return _unescape(value)
    return None


_ESCAPES = {"n": 10, "t": 9, "r": 13, "\\": 92, '"': 34, "'": 39, "a": 7, "b": 8}


def _unescape(value: str) -> str:
    """
    A protobuf text-format string's value.

    Escapes stand for bytes -- ``\\303\\251`` is the UTF-8 of an e with an
    acute -- and the bytes are UTF-8, so they are gathered before decoding.
    """
    out = bytearray()
    i = 0
    while i < len(value):
        char = value[i]
        if char != "\\" or i + 1 == len(value):
            out += char.encode("utf-8")
            i += 1
            continue
        nxt = value[i + 1]
        if nxt in "01234567":
            digits = re.match(r"[0-7]{1,3}", value[i + 1 :]).group()
            out.append(int(digits, 8) & 0xFF)
            i += 1 + len(digits)
        elif nxt in "xX" and re.match(r"[0-9a-fA-F]{1,2}", value[i + 2 :]):
            digits = re.match(r"[0-9a-fA-F]{1,2}", value[i + 2 :]).group()
            out.append(int(digits, 16))
            i += 2 + len(digits)
        elif nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            i += 2
        else:
            out += nxt.encode("utf-8")
            i += 2
    return out.decode("utf-8", errors="replace")


def _vectors(
    path: str, block: dict[str, str], checkpoint: str | None
) -> np.ndarray | None:
    """An embedding's vectors, or ``None`` with a warning when they cannot be read."""
    name = block.get("tensor_name", "embedding")
    if "tensor_path" in block:
        file = os.path.join(path, block["tensor_path"])
        if not os.path.isfile(file):
            warn_at_caller(f"'{name}' names {file}, which does not exist; left out.")
            return None
        try:
            return np.loadtxt(file, delimiter="\t", ndmin=2, dtype=float)
        except ValueError as error:
            warn_at_caller(
                f"maidr could not read '{name}' from {file} ({error}); left out."
            )
            return None
    try:
        import tensorflow as tf
    except ImportError:
        warn_at_caller(
            f"'{name}' is stored in a TensorFlow checkpoint, which maidr reads "
            "only with TensorFlow installed; left out."
        )
        return None
    where = checkpoint or tf.train.latest_checkpoint(path) or path
    if not os.path.isabs(where):
        where = os.path.join(path, where)
    try:
        return np.asarray(tf.train.load_variable(where, name), dtype=float)
    except Exception as error:  # noqa: BLE001 - any reason costs this embedding
        warn_at_caller(
            f"maidr could not read '{name}' from {where} ({error}); left out."
        )
        return None


def _metadata(file: str, count: int) -> dict[str, list[str]]:
    """
    A metadata TSV's columns.

    The Projector reads a file with one column as labels with no header, and
    one with several as having a header row.
    """
    if not os.path.isfile(file):
        return {}
    with open(file, encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream, delimiter="\t"))
    if not rows:
        return {}
    if len(rows[0]) == 1:
        return {"label": [row[0] if row else "" for row in rows][:count]}
    header, body = rows[0], rows[1:]
    return {
        column: [row[i] if i < len(row) else "" for row in body][:count]
        for i, column in enumerate(header)
    }
