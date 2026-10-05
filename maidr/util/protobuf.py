"""Read the fields of a protocol buffer message by hand.

The TensorBoard and Weights & Biases readers decode the few fields they need
themselves, so reading a log directory or a run file needs neither TensorFlow,
W&B nor protobuf. Only what those readers need is here: the wire format's
fields, as raw values, never a schema.
"""

from __future__ import annotations

from typing import Iterator


def fields(data: bytes) -> Iterator[tuple[int, int, object]]:
    """
    The fields of a protocol buffer message, as ``(number, wire type, value)``.

    A varint is an ``int``; a 64-bit, 32-bit or length-delimited field is its
    raw ``bytes``. A message that ends mid-field stops there.
    """
    position = 0
    end = len(data)
    while position < end:
        key, position = varint(data, position)
        if position < 0:
            return
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, position = varint(data, position)
            if position < 0:
                return
            yield number, wire, value
        elif wire == 1:
            if position + 8 > end:
                return
            yield number, wire, data[position : position + 8]
            position += 8
        elif wire == 2:
            length, position = varint(data, position)
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


def varint(data: bytes, position: int) -> tuple[int, int]:
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
