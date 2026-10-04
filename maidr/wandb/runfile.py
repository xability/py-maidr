"""Read the history out of a Weights & Biases run file, ``run-<id>.wandb``.

Every run, online or offline, writes one to its directory under ``wandb/``
as it goes: the transaction log ``wandb sync`` uploads from. It is the
LevelDB log format behind a 7-byte header (``:W&B``, ``0xBEE1``, version
0): 32 KiB blocks of records, each a CRC-32 of its type and data, a length,
a type, and its data, a record too long for what is left of a block split
into a first, middle and last part. Each record's data is one ``Record``
protocol buffer, and only the few fields the history needs are decoded here,
by hand, so reading a run needs neither W&B nor protobuf:

* ``Record``: ``history`` (2) and ``run`` (17);
* ``RunRecord``: ``run_id`` (1) and ``display_name`` (8);
* ``HistoryRecord``: its repeated ``item`` (1);
* ``HistoryItem``: ``key`` (1), the repeated ``nested_key`` (2) a current
  SDK writes the name to instead, and ``value_json`` (16).
"""

from __future__ import annotations

import json
import os
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any, Iterator

from maidr.util.caller_warning import warn_at_caller
from maidr.util.protobuf import fields

_IDENT = b":W&B"
_MAGIC = 0xBEE1
_VERSION = 0
_FILE_HEADER = struct.Struct("<4sHB")
_RECORD_HEADER = struct.Struct("<IHB")
_BLOCK = 32768

_FULL, _FIRST, _MIDDLE, _LAST = 1, 2, 3, 4

_HISTORY = 2
_RUN = 17


@dataclass
class RunFile:
    """
    What one run file holds that a chart needs.

    Attributes
    ----------
    run_id : str
        The run's id, such as ``"5hio02av"``.
    name : str
        The run's display name, or its id when it has none.
    rows : list of dict
        Each step's history, as ``run.scan_history()`` returns it: a nested
        name joined with a dot, and each value as its JSON decodes.
    """

    run_id: str
    name: str
    rows: list[dict[str, Any]] = field(default_factory=list, repr=False)


def is_run_file(path: str) -> bool:
    """Whether ``path`` names a W&B run file, by its name."""
    return path.endswith(".wandb")


def find_run_files(path: str) -> list[str]:
    """
    The run files at ``path``: the file itself, or every one under a directory.

    A directory is walked without following links, so ``wandb/latest-run``,
    a link to the newest run, does not read that run twice. The files are
    sorted by path, which under ``wandb/`` is the order the runs started in.
    """
    if os.path.isfile(path):
        return [path]
    found = []
    for directory, _, names in os.walk(path):
        found.extend(
            os.path.join(directory, name) for name in names if is_run_file(name)
        )
    return sorted(found)


def read_run_file(path: str) -> RunFile:
    """
    Read a run's id, name and history rows from its run file.

    A record whose checksum does not match ends the read, with a warning, as
    does a header that is not a W&B run file's. A record cut off at the end
    of the file ends it silently: that is a run still writing.

    Parameters
    ----------
    path : str
        The ``run-<id>.wandb`` file.

    Returns
    -------
    RunFile
        The run, named after its file when no run record says otherwise.
    """
    run_id = os.path.basename(path)[len("run-") : -len(".wandb")]
    name = ""
    rows: list[dict[str, Any]] = []
    for record in _records(path):
        for number, wire, value in fields(record):
            if wire != 2:
                continue
            if number == _HISTORY:
                rows.append(_history(value))  # type: ignore[arg-type]
            elif number == _RUN:
                found_id, found_name = _run(value)  # type: ignore[arg-type]
                run_id = found_id or run_id
                name = found_name or name
    return RunFile(run_id, name or run_id, rows)


def _records(path: str) -> Iterator[bytes]:
    """The data of each record in the file, a split record joined again."""
    with open(path, "rb") as file:
        data = file.read()
    if len(data) < _FILE_HEADER.size:
        return
    ident, magic, version = _FILE_HEADER.unpack_from(data)
    if ident != _IDENT or magic != _MAGIC or version != _VERSION:
        warn_at_caller(f"maidr cannot read {path}: it is not a W&B run file.")
        return
    position = _FILE_HEADER.size
    parts: list[bytes] = []
    while True:
        left = _BLOCK - position % _BLOCK
        if left < _RECORD_HEADER.size:
            # The rest of a block too short for a header is padding.
            position += left
        if position + _RECORD_HEADER.size > len(data):
            return
        checksum, length, kind = _RECORD_HEADER.unpack_from(data, position)
        start = position + _RECORD_HEADER.size
        if start + length > len(data):
            return
        payload = data[start : start + length]
        if zlib.crc32(bytes([kind]) + payload) != checksum:
            warn_at_caller(
                f"{path} is damaged at byte {position}; it is read up to there."
            )
            return
        position = start + length
        if kind == _FULL:
            yield payload
        elif kind == _FIRST:
            parts = [payload]
        elif kind == _MIDDLE:
            parts.append(payload)
        elif kind == _LAST:
            parts.append(payload)
            yield b"".join(parts)
            parts = []


def _run(record: bytes) -> tuple[str, str]:
    """A ``RunRecord``'s id and display name."""
    run_id = name = ""
    for number, wire, value in fields(record):
        if wire != 2:
            continue
        if number == 1:
            run_id = _text(value)
        elif number == 8:
            name = _text(value)
    return run_id, name


def _history(record: bytes) -> dict[str, Any]:
    """A ``HistoryRecord`` as a row of name to value."""
    row: dict[str, Any] = {}
    for number, wire, item in fields(record):
        if number != 1 or wire != 2:
            continue
        key = ""
        nested: list[str] = []
        value_json = ""
        for item_number, item_wire, value in fields(item):  # type: ignore[arg-type]
            if item_wire != 2:
                continue
            if item_number == 1:
                key = _text(value)
            elif item_number == 2:
                nested.append(_text(value))
            elif item_number == 16:
                value_json = _text(value)
        name = ".".join(nested) if nested else key
        if not name or not value_json:
            continue
        try:
            row[name] = json.loads(value_json)
        except ValueError:
            continue
    return row


def _text(value: object) -> str:
    return bytes(value).decode("utf-8", errors="replace")  # type: ignore[arg-type]
