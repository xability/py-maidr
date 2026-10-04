"""Read the scalar summaries out of TensorBoard event files.

An event file is a sequence of TFRecords, each holding one ``Event`` protocol
buffer. Only the few fields a scalar needs are decoded here, by hand, so that
reading a log directory needs neither TensorFlow nor TensorBoard nor protobuf:

* ``Event``: ``wall_time`` (1), ``step`` (2), ``file_version`` (3),
  ``summary`` (5) and ``session_log`` (7);
* ``Summary``: its repeated ``value`` (1);
* ``Summary.Value``: ``tag`` (1), ``simple_value`` (2), ``tensor`` (8) and
  ``metadata`` (9), whose ``plugin_data.plugin_name`` says what a tensor holds;
* ``TensorProto``: ``dtype`` (1), ``tensor_content`` (4) and the typed value
  lists.

A scalar is written two ways. TensorFlow 1 and PyTorch write the legacy
``simple_value``; TensorFlow 2 and Keras write a rank-0 ``tensor`` whose
metadata names the ``scalars`` plugin, on the first value of a tag only. Both
are read, as TensorBoard reads them.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

from maidr.util.caller_warning import warn_at_caller

#: The plugin a TensorFlow 2 scalar summary names in its metadata.
SCALARS_PLUGIN = "scalars"

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
class _Scalars:
    """One run's scalars, tag by tag, in the order TensorBoard keeps them."""

    steps: dict[str, list[int]] = field(default_factory=dict)
    wall_times: dict[str, list[float]] = field(default_factory=dict)
    values: dict[str, list[float]] = field(default_factory=dict)
    #: The plugin each tag's metadata named, from the first value carrying it.
    plugins: dict[str, str] = field(default_factory=dict)
    #: The step of the last summary read, for spotting a restarted run.
    last_step: int | None = None
    #: The event format the run's files declare, such as ``2.0``.
    file_version: float | None = None
    #: Whether a ``SessionLog.START`` has been read: the next one is a restart.
    started: bool = False

    def add(self, tag: str, step: int, wall_time: float, value: float) -> None:
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


def read_run(paths: list[str]) -> _Scalars:
    """
    Read the scalars of one run from its event files.

    A run restarted from a checkpoint logs some steps again. What it wrote
    over is dropped as TensorBoard drops it: from files of the current event
    format, when a second ``SessionLog.START`` says the run restarted, and from
    older files, when a tag's steps go backwards. TensorFlow 2 writes no
    ``SessionLog``, so TensorBoard keeps both passes of such a run, and so does
    this.
    """
    scalars = _Scalars()
    for path in paths:
        for record in _records(path):
            _read_event(record, scalars)
    return scalars


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


def _read_event(record: bytes, scalars: _Scalars) -> None:
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
            scalars.file_version = _file_version(value)
        elif number == 5 and wire == 2:
            summary = value
        elif number == 7 and wire == 2:
            started = any(
                n == 1 and w == 0 and v == _SESSION_START for n, w, v in _fields(value)
            )
    values = []
    if summary is not None:
        values = [v for n, w, v in _fields(summary) if n == 1 and w == 2]
    if scalars.file_version is not None and scalars.file_version >= 2:
        if started:
            if scalars.started:
                scalars.purge(step)
            scalars.started = True
    elif (
        summary is not None
        and scalars.last_step is not None
        and step < scalars.last_step
    ):
        scalars.purge(step, [t for t in map(_tag, values) if t is not None])
    if summary is None:
        return
    scalars.last_step = step
    for value in values:
        _read_value(value, step, wall_time, scalars)


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


def _read_value(record: bytes, step: int, wall_time: float, scalars: _Scalars) -> None:
    tag = None
    simple = None
    tensor = None
    for number, wire, value in _fields(record):
        if number == 1 and wire == 2:
            tag = value.decode("utf-8", "replace")
        elif number == 2 and wire == 5:
            (simple,) = struct.unpack("<f", value)
        elif number == 8 and wire == 2:
            tensor = value
        elif number == 9 and wire == 2:
            plugin = _plugin_name(value)
            if tag is not None and plugin is not None:
                scalars.plugins.setdefault(tag, plugin)
    if tag is None:
        return
    if simple is not None:
        scalars.plugins.setdefault(tag, SCALARS_PLUGIN)
        scalars.add(tag, step, wall_time, float(simple))
    elif tensor is not None and scalars.plugins.get(tag) == SCALARS_PLUGIN:
        number = _scalar(tensor)
        if number is not None:
            scalars.add(tag, step, wall_time, number)


def _plugin_name(metadata: bytes) -> str | None:
    for number, wire, value in _fields(metadata):
        if number == 1 and wire == 2:
            for inner, inner_wire, name in _fields(value):
                if inner == 1 and inner_wire == 2:
                    return name.decode("utf-8", "replace")
    return None


def _scalar(tensor: bytes) -> float | None:
    """The one number a scalar summary's tensor holds, or ``None``."""
    dtype = None
    content = b""
    listed: list[float] = []
    for number, wire, value in _fields(tensor):
        if number == 1 and wire == 0:
            dtype = value
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
        bits = content[:2] if content else None
        if bits is None and listed:
            bits = struct.pack("<H", int(listed[0]) & 0xFFFF)
        if bits is None or len(bits) < 2:
            return None
        return float(np.frombuffer(b"\x00\x00" + bits, "<f4")[0])
    numpy_type = _DTYPES.get(dtype) if dtype is not None else None
    if numpy_type is None:
        return None
    if content:
        if len(content) < numpy_type.itemsize:
            return None
        return float(np.frombuffer(content[: numpy_type.itemsize], numpy_type)[0])
    if not listed:
        return None
    if dtype == 19:  # DT_HALF arrives as its bits in half_val
        return float(np.array([int(listed[0])], "<u2").view("<f2")[0])
    if numpy_type.kind == "i":
        return float(_signed(int(listed[0])))
    return float(listed[0])


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
