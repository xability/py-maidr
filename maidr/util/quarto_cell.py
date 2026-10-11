"""The ``#|`` options of the Quarto cell a chart is drawn in.

Quarto takes a cell's options off before the kernel runs it, so a chart drawn
in a render cannot read them from the code it was given. They are still in the
notebook Quarto executes: a ``.ipynb`` document itself, or, for a ``.qmd``,
the ``<stem>.quarto_ipynb`` Quarto writes beside the document for the length
of the render, with its includes already in place. The cell is found there by
the code the kernel was sent, which is the cell's source after its options.

r-maidr reads ``fig.alt`` from the chunk options knitr hands it. This is the
nearest the Jupyter engine comes to that.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from typing import Any, Optional

from maidr.util.environment import Environment

#: A line of a Python cell's options, as Quarto reads one: ``#|`` and at most
#: one space (``nb_cell_yaml_lines`` in Quarto's ``notebook.py``).
_OPTION_LINE = re.compile(r"^#\s*\| ?")

#: The code cells of each notebook read so far, by path, with the file's
#: modification time and size, so that a later render rereads it.
_notebooks: dict[str, tuple[tuple[int, int], list[tuple[str, dict[str, Any]]]]] = {}

#: The cell the kernel last drew a chart in -- the notebook, as of when Quarto
#: wrote it, and the execution count -- and how many charts it has drawn. The
#: notebook is part of it because a kernel kept alive between renders can
#: count the executions of a later render from 1 again.
_drawn: list[Any] = [None, 0]


def fig_alt() -> Optional[str]:
    """Return the ``fig-alt`` of the Quarto cell drawing the next chart.

    A cell that draws several charts may give a list, which they take in
    turn, as knitr recycles ``fig.alt`` over a chunk's figures.

    Returns
    -------
    str or None
        The alt text, or None outside a Quarto render, for a cell without
        ``fig-alt``, or when the cell cannot be told apart from another cell
        with the same code and a different ``fig-alt``.
    """
    try:
        return _fig_alt()
    except Exception:
        # Broad on purpose, as in Environment.quarto_writer: this reads files
        # Quarto writes, and must never be why a render fails.
        return None


def _fig_alt() -> Optional[str]:
    """:func:`fig_alt`, which may raise."""
    if not Environment.is_quarto():
        return None
    shell = _shell()
    if shell is None:
        return None
    path = _notebook_path()
    if path is None:
        return None
    index = _chart_index((path, os.stat(path).st_mtime_ns, shell.execution_count))
    code = _normalized(shell.history_manager.input_hist_raw[-1])
    values = [
        options.get("fig-alt")
        for cell_code, options in _code_cells(path)
        if cell_code == code and options.get("eval", True) is not False
    ]
    if not values or any(value != values[0] for value in values):
        return None
    return _pick(values[0], index)


def _shell() -> Any:
    """The kernel's IPython shell, or None without one."""
    if sys.modules.get("IPython") is None:
        return None
    from IPython import get_ipython

    return get_ipython()


def _chart_index(cell: tuple[Any, ...]) -> int:
    """Which chart of the running cell this is, counting from 0."""
    if cell != _drawn[0]:
        _drawn[0] = cell
        _drawn[1] = 0
    else:
        _drawn[1] += 1
    return _drawn[1]


def _notebook_path() -> Optional[str]:
    """The notebook Quarto is executing, or None when there is none to read."""
    source = _document_path()
    if source is None:
        return None
    if source.endswith(".ipynb"):
        return source if os.path.isfile(source) else None
    directory, name = os.path.split(source)
    stem = os.path.splitext(name)[0]
    # Quarto adds _1, _2 ... when an earlier one was left behind, so the one
    # this render wrote is the newest.
    candidates = glob.glob(os.path.join(directory, glob.escape(stem) + ".quarto_ipynb*"))
    return max(candidates, key=os.path.getmtime) if candidates else None


def _document_path() -> Optional[str]:
    """The document being rendered.

    Quarto 1.8 and later name it in the ``QUARTO_EXECUTE_INFO`` file, which
    the kernel is told of once, when it starts; ``QUARTO_DOCUMENT_PATH`` and
    ``QUARTO_DOCUMENT_FILE`` name it too, the directory being the one the
    render runs in.
    """
    info = os.environ.get("QUARTO_EXECUTE_INFO")
    if info:
        try:
            with open(info, encoding="utf-8") as f:
                path = json.load(f).get("document-path")
            if isinstance(path, str) and path:
                return path
        except (OSError, ValueError, AttributeError):
            pass
    directory = os.environ.get("QUARTO_DOCUMENT_PATH")
    name = os.environ.get("QUARTO_DOCUMENT_FILE")
    if directory and name:
        return os.path.join(directory, name)
    return None


def _code_cells(path: str) -> list[tuple[str, dict[str, Any]]]:
    """Each code cell of the notebook, as its code and its options."""
    stat = os.stat(path)
    stamp = (stat.st_mtime_ns, stat.st_size)
    cached = _notebooks.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    with open(path, encoding="utf-8") as f:
        notebook = json.load(f)
    cells: list[tuple[str, dict[str, Any]]] = []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        option_lines, code = _split_options(source)
        cells.append((_normalized(code), _parse_options(option_lines)))
    _notebooks[path] = (stamp, cells)
    return cells


def _split_options(source: str) -> tuple[list[str], str]:
    """A cell's option lines, and the code Quarto sends the kernel."""
    lines = source.splitlines()
    options: list[str] = []
    for line in lines:
        match = _OPTION_LINE.match(line)
        if match is None:
            break
        options.append(re.sub(r":\s+$", ":", line[match.end() :]))
    return options, "\n".join(lines[len(options) :])


def _normalized(code: str) -> str:
    """Code as it is compared: without trailing spaces or blank ends."""
    return "\n".join(line.rstrip() for line in code.splitlines()).strip()


def _parse_options(lines: list[str]) -> dict[str, Any]:
    """A cell's options, read as Quarto reads them: as YAML."""
    if not lines:
        return {}
    text = "\n".join(lines)
    try:
        import yaml  # Quarto's own Jupyter runner needs it, so it is usually there.

        parsed = yaml.safe_load(text)
        return parsed if isinstance(parsed, dict) else {}
    except ImportError:
        return _parse_simple_options(lines)
    except Exception:
        return {}


def _parse_simple_options(lines: list[str]) -> dict[str, Any]:
    """``key: value`` lines, for a kernel without PyYAML.

    A value is read as JSON when it is one -- a double-quoted string, a list
    such as ``["a", "b"]``, ``true`` or ``false`` -- as a single-quoted string
    when it is quoted so, and otherwise as the text it is.
    """
    options: dict[str, Any] = {}
    for line in lines:
        key, separator, value = line.partition(":")
        if not separator or line[:1].isspace():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == "'":
            options[key.strip()] = value[1:-1].replace("''", "'")
            continue
        try:
            options[key.strip()] = json.loads(value)
        except ValueError:
            options[key.strip()] = value
    return options


def _pick(value: Any, index: int) -> Optional[str]:
    """The alt text for the ``index``-th chart of the cell, from its option."""
    if isinstance(value, list):
        texts = [item for item in value if isinstance(item, str)]
        value = texts[index % len(texts)] if texts else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
