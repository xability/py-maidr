"""Read the scalar and histogram summaries out of TensorBoard event files.

An event file is a sequence of TFRecords, each holding one ``Event`` protocol
buffer. Only the few fields a scalar or a histogram needs are decoded here, by
hand, so that reading a log directory needs neither TensorFlow nor TensorBoard
nor protobuf:

* ``Event``: ``wall_time`` (1), ``step`` (2), ``file_version`` (3),
  ``summary`` (5) and ``session_log`` (7);
* ``Summary``: its repeated ``value`` (1);
* ``Summary.Value``: ``tag`` (1), ``simple_value`` (2), ``histo`` (5),
  ``tensor`` (8) and ``metadata`` (9), whose ``plugin_data.plugin_name`` says
  what a tensor holds;
* ``TensorProto``: ``dtype`` (1), ``tensor_shape`` (2), ``tensor_content``
  (4) and the typed value lists;
* ``HistogramProto``: ``min`` (1), ``max`` (2), ``bucket_limit`` (6) and
  ``bucket`` (7).

Each is written two ways. TensorFlow 1 and PyTorch write a scalar as the
legacy ``simple_value`` and a histogram as the legacy ``histo``; TensorFlow 2
and Keras write a ``tensor`` whose metadata names the ``scalars`` or
``histograms`` plugin, on the first value of a tag only. Both are read, as
TensorBoard reads them.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import Any, Iterator

import numpy as np

from maidr.util.caller_warning import warn_at_caller

#: The plugin a TensorFlow 2 scalar summary names in its metadata.
SCALARS_PLUGIN = "scalars"
#: The plugin a TensorFlow 2 histogram summary names in its metadata.
HISTOGRAMS_PLUGIN = "histograms"

#: ``SessionLog.status`` of a run that started, or started again.
_SESSION_START = 1

#: ``DataType`` codes of the tensors a scalar summary may hold, as NumPy types.
_DTYPES = {
    1: np.dtype("<f4"),  # DT_FLOAT
    2: np.dtype("<f8"),  # DT_DOUBLE
    3: np.dtype("<i4"),  # DT_INT32
    4: np.dtype("u1"),  # DT_UINT8
    5: np.dtype("<i2"),  # DT_INT16
    6: np.dtype("i1"),  # DT_INT8
    9: np.dtype("<i8"),  # DT_INT64
    10: np.dtype("?"),  # DT_BOOL
    17: np.dtype("<u2"),  # DT_UINT16
    19: np.dtype("<f2"),  # DT_HALF
    22: np.dtype("<u4"),  # DT_UINT32
    23: np.dtype("<u8"),  # DT_UINT64
}
_BFLOAT16 = 14


@dataclass
class Run:
    """
    One run's summaries of one plugin, tag by tag, in TensorBoard's order.

    A scalar is a ``float``; a histogram is an array of shape ``(k, 3)``, each
    row a bucket's left edge, right edge and count.
    """

    #: The plugin whose summaries are kept, such as ``"scalars"``.
    plugin: str = SCALARS_PLUGIN
    steps: dict[str, list[int]] = field(default_factory=dict)
    wall_times: dict[str, list[float]] = field(default_factory=dict)
    values: dict[str, list[Any]] = field(default_factory=dict)
    #: The plugin each tag's metadata named, from the first value carrying it.
    plugins: dict[str, str] = field(default_factory=dict)
    #: The step of the last summary read, for spotting a restarted run.
    last_step: int | None = None
    #: The event format the run's files declare, such as ``2.0``.
    file_version: float | None = None
    #: Whether a ``SessionLog.START`` has been read: the next one is a restart.
    started: bool = False

    def add(self, tag: str, step: int, wall_time: float, value: Any) -> None:
        self.steps.setdefault(tag, []).append(step)
        self.wall_times.setdefault(tag, []).append(wall_time)
        self.values.setdefault(tag, []).append(value)

    def purge(self, step: int, tags: list[str] | None = None) -> None:
        """Drop the values at ``step`` or later: what a restart wrote over."""
        for tag in self.steps if tags is None else tags:
            if tag not in self.steps:
                continue
            keep = [i for i, s in enumerate(self.steps[tag]) if s < step]
            self.steps[tag] = [self.steps[tag][i] for i in keep]
            self.wall_times[tag] = [self.wall_times[tag][i] for i in keep]
            self.values[tag] = [self.values[tag][i] for i in keep]


def is_event_file(name: str) -> bool:
    """Whether TensorBoard reads a file of this name as an event file."""
    return "tfevents" in name


def find_runs(logdir: str) -> dict[str, list[str]]:
    """
    Find the runs of a log directory, as TensorBoard names them.

    Every directory holding an event file is a run, named by its path from
    ``logdir`` with ``/`` between its parts, and ``"."`` for ``logdir`` itself.

    Returns
    -------
    dict of str to list of str
        Each run's event files, in the order they are read: by name, which
        starts with the time the file was opened.
    """
    runs = {}
    for directory, subdirectories, files in os.walk(logdir):
        subdirectories.sort()
        events = sorted(name for name in files if is_event_file(name))
        if events:
            run = os.path.relpath(directory, logdir).replace(os.sep, "/")
            runs[run] = [os.path.join(directory, name) for name in events]
    return runs


def read_run(paths: list[str], plugin: str = SCALARS_PLUGIN) -> Run:
    """
    Read the summaries of one plugin of one run from its event files.

    A run restarted from a checkpoint logs some steps again. What it wrote
    over is dropped as TensorBoard drops it: from files of the current event
    format, when a second ``SessionLog.START`` says the run restarted, and from
    older files, when a tag's steps go backwards. TensorFlow 2 writes no
    ``SessionLog``, so TensorBoard keeps both passes of such a run, and so does
    this.

    Parameters
    ----------
    paths : list of str
        The run's event files, in the order they are read.
    plugin : str, default "scalars"
        ``"scalars"`` or ``"histograms"``.

    Returns
    -------
    Run
        The run's values of that plugin, tag by tag.
    """
    run = Run(plugin=plugin)
    for path in paths:
        for record in _records(path):
            _read_event(record, run)
    return run


def _records(path: str) -> Iterator[bytes]:
    """
    The TFRecords of a file.

    Each is an 8-byte little-endian length, a 4-byte checksum of that length,
    the data, and a 4-byte checksum of the data. The length's checksum is
    verified, so a damaged file stops being read where the damage starts
    rather than being misread; the data's is not, which would cost a pass of
    pure-Python CRC over every image and histogram a log directory holds. A
    record cut off at the end is a file still being written, and ends it
    silently. A length running past the end of the file is read as such a
    record, before anything is read, so that a length a file only claims is
    never allocated.
    """
    with open(path, "rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        while True:
            header = stream.read(12)
            if len(header) < 12:
                return
            (length,) = struct.unpack("<Q", header[:8])
            (checksum,) = struct.unpack("<I", header[8:])
            if checksum != _masked_crc32c(header[:8]):
                warn_at_caller(
                    f"maidr stopped reading {path} at byte {stream.tell() - 12}: "
                    "the file is damaged there."
                )
                return
            if length + 4 > size - stream.tell():
                return
            data = stream.read(length)
            if len(data) < length or len(stream.read(4)) < 4:
                return
            yield data


def _read_event(record: bytes, run: Run) -> None:
    wall_time = 0.0
    step = 0
    summary = None
    started = False
    for number, wire, value in _fields(record):
        if number == 1 and wire == 1:
            (wall_time,) = struct.unpack("<d", value)
        elif number == 2 and wire == 0:
            step = _signed(value)
        elif number == 3 and wire == 2:
            run.file_version = _file_version(value)
        elif number == 5 and wire == 2:
            summary = value
        elif number == 7 and wire == 2:
            started = any(
                n == 1 and w == 0 and v == _SESSION_START for n, w, v in _fields(value)
            )
    values = []
    if summary is not None:
        values = [v for n, w, v in _fields(summary) if n == 1 and w == 2]
    if run.file_version is not None and run.file_version >= 2:
        if started:
            if run.started:
                run.purge(step)
            run.started = True
    elif summary is not None and run.last_step is not None and step < run.last_step:
        run.purge(step, [t for t in map(_tag, values) if t is not None])
    if summary is None:
        return
    run.last_step = step
    for value in values:
        _read_value(value, step, wall_time, run)


def _file_version(value: bytes) -> float | None:
    """The version of a ``file_version`` such as ``brain.Event:2``."""
    text = value.decode("utf-8", "replace")
    try:
        return float(text.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None


def _tag(record: bytes) -> str | None:
    for number, wire, value in _fields(record):
        if number == 1 and wire == 2:
            return value.decode("utf-8", "replace")
    return None


def _read_value(record: bytes, step: int, wall_time: float, run: Run) -> None:
    tag = None
    simple = None
    histo = None
    tensor = None
    for number, wire, value in _fields(record):
        if number == 1 and wire == 2:
            tag = value.decode("utf-8", "replace")
        elif number == 2 and wire == 5:
            (simple,) = struct.unpack("<f", value)
        elif number == 5 and wire == 2:
            histo = value
        elif number == 8 and wire == 2:
            tensor = value
        elif number == 9 and wire == 2:
            plugin = _plugin_name(value)
            if tag is not None and plugin is not None:
                run.plugins.setdefault(tag, plugin)
    if tag is None:
        return
    if simple is not None:
        run.plugins.setdefault(tag, SCALARS_PLUGIN)
    elif histo is not None:
        run.plugins.setdefault(tag, HISTOGRAMS_PLUGIN)
    if run.plugins.get(tag) != run.plugin:
        return
    value: Any = None
    if run.plugin == SCALARS_PLUGIN:
        if simple is not None:
            value = float(simple)
        elif tensor is not None:
            value = _scalar(tensor)
    elif run.plugin == HISTOGRAMS_PLUGIN:
        if histo is not None:
            value = _legacy_histogram(histo)
        elif tensor is not None:
            value = _histogram(tensor)
    if value is not None:
        run.add(tag, step, wall_time, value)


def _plugin_name(metadata: bytes) -> str | None:
    for number, wire, value in _fields(metadata):
        if number == 1 and wire == 2:
            for inner, inner_wire, name in _fields(value):
                if inner == 1 and inner_wire == 2:
                    return name.decode("utf-8", "replace")
    return None


def _scalar(tensor: bytes) -> float | None:
    """The one number a scalar summary's tensor holds, or ``None``."""
    array = _tensor(tensor)
    if array is None or array.size != 1:
        return None
    return float(array.reshape(()))


def _histogram(tensor: bytes) -> np.ndarray | None:
    """A histogram summary's buckets, shape ``(k, 3)``, or ``None``."""
    array = _tensor(tensor)
    if array is None or array.ndim != 2 or array.shape[1] != 3:
        return None
    return array


def _legacy_histogram(histo: bytes) -> np.ndarray:
    """
    A legacy ``HistogramProto``'s buckets, as TensorBoard converts them.

    Its outermost limits can be the largest doubles, so TensorBoard drops the
    empty buckets at either end and puts the smallest and largest values seen
    in their place, keeping each bucket's left edge below its right. The
    result is rounded to 32-bit floats, as TensorBoard's is.
    """
    low = high = 0.0
    limits: list[float] = []
    counts: list[float] = []
    for number, wire, value in _fields(histo):
        if number == 1 and wire == 1:
            (low,) = struct.unpack("<d", value)
        elif number == 2 and wire == 1:
            (high,) = struct.unpack("<d", value)
        elif number == 6:
            limits.extend(_fixed(value, wire, "<d"))
        elif number == 7:
            counts.extend(_fixed(value, wire, "<d"))
    filled = [i for i, count in enumerate(counts) if count > 0]
    if not filled:
        return np.zeros((0, 3), dtype=float)
    start, end = filled[0], filled[-1]
    inner = limits[start:end]
    lefts = [low, *inner]
    rights = [*inner, high]
    buckets = np.array([lefts, rights, counts[start : end + 1]], dtype=np.float32)
    return buckets.T.astype(float)


def _tensor(tensor: bytes) -> np.ndarray | None:
    """
    A ``TensorProto`` as a float array of its shape, or ``None``.

    Its values are its ``tensor_content`` when it has one, else its typed
    value list, whose last value TensorFlow leaves out when it repeats to the
    end. A type that is not a number, such as a string, is ``None``.
    """
    dtype = None
    shape: list[int] = []
    content = b""
    listed: list[float] = []
    for number, wire, value in _fields(tensor):
        if number == 1 and wire == 0:
            dtype = value
        elif number == 2 and wire == 2:
            shape = _shape(value)
        elif number == 4 and wire == 2:
            content = value
        elif number == 5:  # float_val
            listed.extend(_fixed(value, wire, "<f"))
        elif number == 6:  # double_val
            listed.extend(_fixed(value, wire, "<d"))
        elif number in (7, 10, 11, 13, 16, 17):
            # int_val, int64_val, bool_val, half_val, uint32_val, uint64_val
            listed.extend(_varints(value, wire))
    if dtype == _BFLOAT16:
        raw = (
            np.frombuffer(content[: len(content) // 2 * 2], "<u2")
            if content
            else np.array([int(v) & 0xFFFF for v in listed], "<u2")
        )
        values = (raw.astype("<u4") << 16).view("<f4").astype(float)
    else:
        numpy_type = _DTYPES.get(dtype) if dtype is not None else None
        if numpy_type is None:
            return None
        if content:
            count = len(content) // numpy_type.itemsize
            values = np.frombuffer(
                content[: count * numpy_type.itemsize], numpy_type
            ).astype(float)
        elif dtype == 19:  # DT_HALF arrives as its bits in half_val
            bits = np.array([int(v) & 0xFFFF for v in listed], "<u2")
            values = bits.view("<f2").astype(float)
        elif numpy_type.kind == "i":
            values = np.array([_signed(int(v)) for v in listed], dtype=float)
        else:
            values = np.array(listed, dtype=float)
    size = int(np.prod(shape)) if shape else 1
    if 0 < values.size < size:
        values = np.concatenate([values, np.full(size - values.size, values[-1])])
    if values.size != size:
        return None
    return values.reshape(shape)


def _shape(shape: bytes) -> list[int]:
    """The sizes of a ``TensorShapeProto``'s dimensions."""
    sizes = []
    for number, wire, value in _fields(shape):
        if number == 2 and wire == 2:
            size = 0
            for inner, inner_wire, length in _fields(value):
                if inner == 1 and inner_wire == 0:
                    size = _signed(length)
            sizes.append(max(size, 0))
    return sizes


def _fields(data: bytes) -> Iterator[tuple[int, int, object]]:
    """
    The fields of a protocol buffer message, as ``(number, wire type, value)``.

    A varint is an ``int``; a 64-bit, 32-bit or length-delimited field is its
    raw ``bytes``. A message that ends mid-field stops there.
    """
    position = 0
    end = len(data)
    while position < end:
        key, position = _varint(data, position)
        if position < 0:
            return
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, position = _varint(data, position)
            if position < 0:
                return
            yield number, wire, value
        elif wire == 1:
            if position + 8 > end:
                return
            yield number, wire, data[position : position + 8]
            position += 8
        elif wire == 2:
            length, position = _varint(data, position)
            if position < 0 or position + length > end:
                return
            yield number, wire, data[position : position + length]
            position += length
        elif wire == 5:
            if position + 4 > end:
                return
            yield number, wire, data[position : position + 4]
            position += 4
        else:
            # Groups (3, 4) are not written by any summary writer.
            return


def _varint(data: bytes, position: int) -> tuple[int, int]:
    """A varint and the position after it, or ``(0, -1)`` if it is cut off."""
    result = 0
    shift = 0
    while position < len(data):
        byte = data[position]
        position += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, position
        shift += 7
    return 0, -1


def _varints(value: object, wire: int) -> list[int]:
    """A repeated varint field: one value, or a packed run of them."""
    if wire == 0:
        return [value]  # type: ignore[list-item]
    if wire != 2:
        return []
    values = []
    position = 0
    data: bytes = value  # type: ignore[assignment]
    while position < len(data):
        number, position = _varint(data, position)
        if position < 0:
            break
        values.append(number)
    return values


def _fixed(value: object, wire: int, fmt: str) -> list[float]:
    """A repeated fixed-width field: one value, or a packed run of them."""
    data: bytes = value  # type: ignore[assignment]
    if wire == 0:
        return []
    size = struct.calcsize(fmt)
    count = len(data) // size
    return list(struct.unpack(f"<{count}{fmt[1]}", data[: count * size]))


def _signed(value: int) -> int:
    """A 64-bit two's complement varint, as the signed number it encodes."""
    return value - (1 << 64) if value >= 1 << 63 else value


def _crc32c_table() -> list[int]:
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x82F63B78 if crc & 1 else crc >> 1
        table.append(crc)
    return table


_CRC32C = _crc32c_table()


def _masked_crc32c(data: bytes) -> int:
    """The CRC-32C of ``data``, masked the way TFRecord masks it."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc = _CRC32C[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    crc ^= 0xFFFFFFFF
    return (((crc >> 15) | (crc << 17)) + 0xA282EAD8) & 0xFFFFFFFF
