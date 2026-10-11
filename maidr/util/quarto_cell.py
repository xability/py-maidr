"""The ``#|`` options of the Quarto cell a chart is drawn in.

Quarto takes a cell's options off before the kernel runs it, so a chart drawn
in a render cannot read them from the code it was given. They are still in the
notebook Quarto executes: a ``.ipynb`` document itself, or, for a ``.qmd``,
the ``<stem>.quarto_ipynb`` Quarto writes beside the document for the length
of the render, with its includes already in place. The cell is found there by
the code the kernel was sent, which is the cell's source after its options.
Of cells with the same code, the running one is told by the kernel's place in
the render: Quarto runs the document's cells in order, each once.

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

#: The header of a YAML block scalar: ``|`` or ``>``, then its chomping and
#: indentation indicators, if any.
_BLOCK_SCALAR = re.compile(r"^[|>][1-9+-]*$")

#: The code cells of each notebook read so far, by path, with the file's
#: modification time and size, so that a later render rereads it.
_notebooks: dict[str, tuple[tuple[int, int], list[tuple[str, dict[str, Any]]]]] = {}

#: The cell the kernel last drew a chart in -- the notebook, as of when Quarto
#: wrote it, and the execution count -- and how many charts it has drawn. The
#: notebook is part of it because a kernel kept alive between renders can
#: count the executions of a later render from 1 again.
_drawn: list[Any] = [None, 0]

#: How many cells the kernel had stored in its history when this render
#: started. Quarto runs its setup cell ahead of the document's, and its
#: cleanup cell after them, without storing either, in a kernel it keeps
#: alive between renders as in a new one: :func:`_watch_renders` notes the
#: count when one runs. A new kernel has stored none.
_stored_before_render: list[int] = [0]

#: The kernel :func:`_watch_renders` watches.
_watched: list[Any] = [None]


def fig_alt() -> Optional[str]:
    """Return the ``fig-alt`` of the Quarto cell drawing the next chart.

    A cell that draws several charts may give a list, which they take in
    turn, as knitr recycles ``fig.alt`` over a chunk's figures.

    Returns
    -------
    str or None
        The alt text, or None outside a Quarto render, for a cell without
        ``fig-alt``, and for alt text that is the caption Quarto shows under
        the chart, which describes it already, as r-maidr leaves it out.
        None too when cells with the same code give different alt text and
        the render cannot be placed in the notebook.
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
    _watch_renders(shell)
    path = _notebook_path()
    if path is None:
        return None
    index = _chart_index((path, os.stat(path).st_mtime_ns, shell.execution_count))
    history = shell.history_manager.input_hist_raw
    code = _normalized(history[-1])
    run = _run_cells(path)
    alts = {_alt(options, index) for cell_code, options in run if cell_code == code}
    if len(alts) <= 1:
        return alts.pop() if alts else None
    # Cells with this code give different alt text. Quarto runs the cells it
    # evaluates in order and the kernel stores each before running it, so the
    # running one is the cell at the kernel's place in this render. The
    # history, not the execution count, gives the place: IPython 9 counts a
    # cell before running it, IPython 8 after.
    place = len(history) - 1 - _stored_before_render[0] - 1
    if 0 <= place < len(run) and run[place][0] == code:
        return _alt(run[place][1], index)
    return None


def _run_cells(path: str) -> list[tuple[str, dict[str, Any]]]:
    """The code cells of the notebook Quarto runs, in order."""
    default = _evaluated_by_default()
    return [
        (code, options)
        for code, options in _code_cells(path)
        if code and options.get("eval", default) is True
    ]


def _alt(options: dict[str, Any], index: int) -> Optional[str]:
    """The alt text a cell's options give its ``index``-th chart.

    None for alt text that is the caption Quarto shows under the chart,
    which describes it already: r-maidr leaves it out the same way.
    """
    alt = _pick(options.get("fig-alt"), index)
    if alt is not None and alt == _caption(options, index):
        return None
    return alt


def _evaluated_by_default() -> bool:
    """Whether Quarto runs a cell with no ``eval``, by the document's."""
    document_format = _execute_info().get("format")
    execute = (
        document_format.get("execute") if isinstance(document_format, dict) else None
    )
    return not isinstance(execute, dict) or execute.get("eval", True) is True


def _caption(options: dict[str, Any], index: int) -> Optional[str]:
    """The caption Quarto shows under the ``index``-th chart, if any.

    Quarto captions the charts of a figure's cell, one labelled ``fig-``,
    and of no other: each by its ``fig-subcap`` when the cell gives them,
    or by its ``fig-cap``. inline.js describes the chart by the caption.
    """
    if not str(options.get("label", "")).startswith("fig-"):
        return None
    return _pick(options.get("fig-subcap"), index) or _pick(
        options.get("fig-cap"), index
    )


def _watch_renders(shell: Any) -> None:
    """Note in :data:`_stored_before_render` where each render starts."""
    events = getattr(shell, "events", None)
    if _watched[0] is shell or events is None:
        return
    _watched[0] = shell

    def started(info: Any = None) -> None:
        # Quarto's setup and cleanup cells, which it does not store: the next
        # cell stored is a render's first.
        if info is not None and not getattr(info, "store_history", True):
            _stored_before_render[0] = len(shell.history_manager.input_hist_raw) - 1

    events.register("pre_run_cell", started)


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
    candidates = glob.glob(
        os.path.join(directory, glob.escape(stem) + ".quarto_ipynb*")
    )
    return max(candidates, key=os.path.getmtime) if candidates else None


def _document_path() -> Optional[str]:
    """The document being rendered.

    Quarto 1.8 and later name it in the ``QUARTO_EXECUTE_INFO`` file, which
    the kernel is told of once, when it starts; ``QUARTO_DOCUMENT_PATH`` and
    ``QUARTO_DOCUMENT_FILE`` name it too, the directory being the one the
    render runs in.
    """
    path = _execute_info().get("document-path")
    if isinstance(path, str) and path:
        return path
    directory = os.environ.get("QUARTO_DOCUMENT_PATH")
    name = os.environ.get("QUARTO_DOCUMENT_FILE")
    if directory and name:
        return os.path.join(directory, name)
    return None


def _execute_info() -> dict[str, Any]:
    """The ``QUARTO_EXECUTE_INFO`` file of Quarto 1.8 and later, or {}.

    It names the document and holds its format, ``execute`` options
    included.
    """
    path = os.environ.get("QUARTO_EXECUTE_INFO")
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return {}
    return info if isinstance(info, dict) else {}


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

    As in YAML, a value goes on over the lines after its key that are
    indented or are items of a list. Those of a block scalar (``>`` or
    ``|``) are its text, ``- item`` lines are a list, and any other value
    is one line with the lines that go on folded into it by spaces, read
    by :func:`_simple_value`.
    """
    entries: list[tuple[str, list[str]]] = []
    for line in lines:
        if entries and (line[:1].isspace() or _is_list_item(line)):
            entries[-1][1].append(line.strip())
        elif ":" in line and not line[:1].isspace():
            key, _, value = line.partition(":")
            entries.append((key.strip(), [value.strip()]))
    options: dict[str, Any] = {}
    for key, (value, *rest) in entries:
        rest = [text for text in rest if text]
        if _BLOCK_SCALAR.match(value):
            options[key] = ("\n" if value[0] == "|" else " ").join(rest)
        elif not value and rest and _is_list_item(rest[0]):
            options[key] = _list_items(rest)
        else:
            options[key] = _simple_value(" ".join([value, *rest]))
    return options


def _is_list_item(line: str) -> bool:
    """Whether a line starts an item of a block list."""
    return line == "-" or line.startswith("- ")


def _list_items(lines: list[str]) -> list[Any]:
    """The items of a block list, each with the lines folded into it."""
    items: list[list[str]] = []
    for line in lines:
        if _is_list_item(line):
            items.append([line[1:].strip()])
        elif items:
            items[-1].append(line)
    return [_simple_value(" ".join(item)) for item in items]


def _simple_value(text: str) -> Any:
    """A value written on one line.

    It is read as JSON when it is JSON -- a double-quoted string, a list
    such as ``["a", "b"]``, ``true`` or ``false`` -- as a single-quoted
    string when it is quoted so, and otherwise as the text it is.
    """
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    try:
        return json.loads(text)
    except ValueError:
        return text


def _pick(value: Any, index: int) -> Optional[str]:
    """The alt text for the ``index``-th chart of the cell, from its option."""
    if isinstance(value, list):
        texts = [item for item in value if isinstance(item, str)]
        value = texts[index % len(texts)] if texts else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
