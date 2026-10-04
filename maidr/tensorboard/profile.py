"""Read a TensorBoard profile as the charts its Profile dashboard leads with.

A profile captured with ``tf.profiler`` (or Keras's ``TensorBoard`` callback
with ``profile_batch``) is written under ``plugins/profile/<session>/`` as
XPlane protocol buffers, which the profile plugin converts into the tables its
pages draw. maidr asks that converter for two of them and draws them:

* the **step-time graph**: how long each step took, split into where the time
  went -- host compute, device compute, input, compilation and the rest -- as
  stacked bars, one per step;
* the **top operations**: which kinds of operation took the most self time,
  as bars, largest first.

Converting XPlane takes the profile plugin's compiled converter: install
``xprof`` (``pip install xprof``), which TensorBoard's Profile tab needs too.
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Iterable

import numpy as np
from matplotlib.figure import Figure

from maidr.tensorboard.logdir import TensorBoardChart
from maidr.util.caller_warning import warn_at_caller

__all__ = ["CHARTS", "find_profiles", "profile_charts", "read_tensorboard_profile"]

#: What each step-time component is called, in the order the bars stack.
_COMPONENTS = {
    "deviceComputeTimeMs": "Device compute",
    "deviceToDeviceTimeMs": "Device to device",
    "deviceCollectivesTimeMs": "Device collectives",
    "hostComputeTimeMs": "Host compute",
    "kernelLaunchTimeMs": "Kernel launch",
    "infeedTimeMs": "Input",
    "outfeedTimeMs": "Output",
    "compileTimeMs": "Compilation",
    "otherTimeMs": "All others",
}

#: Operation types shown, by self time.
DEFAULT_TOP = 10

#: The charts a profile is read as, in the order they are returned.
CHARTS = ("step_time", "top_operations")


def find_profiles(logdir: str | os.PathLike) -> dict[str, list[str]]:
    """
    The profiling sessions of a log directory and their XPlane files.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with.

    Returns
    -------
    dict of str to list of str
        Each session, named by its run and timestamp directory such as
        ``"train/2026_10_04_12_28_21"``, sorted, and its ``*.xplane.pb``
        files, one per host.
    """
    root = os.fspath(logdir)
    sessions: dict[str, list[str]] = {}
    pattern = os.path.join(root, "**", "plugins", "profile", "*", "*.xplane.pb")
    for path in sorted(glob.glob(pattern, recursive=True)):
        session_dir = os.path.dirname(path)
        run = os.path.relpath(
            os.path.dirname(os.path.dirname(os.path.dirname(session_dir))), root
        )
        name = os.path.basename(session_dir)
        key = name if run == "." else f"{run.replace(os.sep, '/')}/{name}"
        sessions.setdefault(key, []).append(path)
    return dict(sorted(sessions.items()))


def read_tensorboard_profile(
    logdir: str | os.PathLike,
    *,
    session: str | None = None,
    top: int = DEFAULT_TOP,
    charts: Iterable[str] | None = None,
) -> list[TensorBoardChart]:
    """
    Read a profiling session as its step-time graph and top operations.

    Parameters
    ----------
    logdir : str or os.PathLike
        The directory TensorBoard would be started with.
    session : str, optional
        Which session, as :func:`find_profiles` names it. By default the
        latest.
    top : int, default 10
        How many operation types the second chart shows.
    charts : iterable of str, optional
        Only these of ``"step_time"`` and ``"top_operations"``; the profile
        is converted only for the tables they need. By default both.

    Returns
    -------
    list of TensorBoardChart
        The step-time graph, tagged ``profile/step_time``, then the top
        operations, tagged ``profile/top_operations``; either is left out
        when the profile holds no data for it. Their ``runs`` name the
        session.

    Raises
    ------
    FileNotFoundError
        If ``logdir`` holds no profile, or no session of that name.
    ValueError
        If ``charts`` names a chart other than those above.
    ImportError
        If ``xprof`` is not installed.

    Examples
    --------
    >>> import maidr
    >>> step_time, top_ops = maidr.read_tensorboard_profile("logs/fit")
    >>> maidr.show(step_time)
    """
    sessions = find_profiles(logdir)
    if not sessions:
        raise FileNotFoundError(f"{os.fspath(logdir)} holds no TensorBoard profile.")
    wanted = _wanted(charts)
    if session is None:
        # The latest timestamp; two runs profiled in the same second are told
        # apart by their whole names, so the choice does not depend on order.
        session = max(sessions, key=lambda name: (name.rsplit("/", 1)[-1], name))
    if session not in sessions:
        known = ", ".join(f"'{name}'" for name in sessions)
        raise FileNotFoundError(f"No profile session '{session}'; there are {known}.")
    paths = sessions[session]
    return profile_charts(
        _convert(paths, "input_pipeline_analyzer") if "step_time" in wanted else [],
        _convert(paths, "framework_op_stats") if "top_operations" in wanted else [],
        session=session,
        top=top,
        charts=wanted,
    )


def profile_charts(
    input_pipeline: str | list,
    op_stats: str | list,
    *,
    session: str = "",
    top: int = DEFAULT_TOP,
    charts: Iterable[str] | None = None,
) -> list[TensorBoardChart]:
    """
    Draw the charts from the profile plugin's converted tables.

    Parameters
    ----------
    input_pipeline : str or list
        The ``input_pipeline_analyzer`` tool's JSON, as text or parsed.
    op_stats : str or list
        The ``framework_op_stats`` tool's JSON, as text or parsed.
    session : str, optional
        The session's name, for the charts' titles.
    top : int, default 10
        How many operation types to show.
    charts : iterable of str, optional
        Only these of ``"step_time"`` and ``"top_operations"``; the table
        of one left out is not read. By default both.

    Returns
    -------
    list of TensorBoardChart
        As :func:`read_tensorboard_profile` returns.
    """
    wanted = _wanted(charts)
    drawn = []
    if "step_time" in wanted:
        steps = _step_table(_tables(input_pipeline))
        if steps is None:
            warn_at_caller(
                "The profile records no steps; the step-time graph is left out."
            )
        else:
            names, components = steps
            figure = _draw_steps(names, components, session)
            drawn.append(TensorBoardChart("profile/step_time", (session,), figure))
    if "top_operations" in wanted:
        ops = _op_types(_tables(op_stats), top)
        if not ops:
            warn_at_caller("The profile records no operations; they are left out.")
        else:
            figure = _draw_ops(ops, session)
            drawn.append(TensorBoardChart("profile/top_operations", (session,), figure))
    return drawn


def _wanted(charts: Iterable[str] | None) -> tuple[str, ...]:
    """The charts asked for, checked, in :data:`CHARTS` order."""
    if charts is None:
        return CHARTS
    asked = set(charts)
    unknown = asked - set(CHARTS)
    if unknown:
        raise ValueError(
            f"A profile is read as {' and '.join(CHARTS)}, not {sorted(unknown)}."
        )
    return tuple(name for name in CHARTS if name in asked)


def _convert(paths: list[str], tool: str) -> str:
    """One tool's JSON for the XPlane files, from the profile plugin's converter."""
    try:
        from xprof.convert import raw_to_tool_data
    except ImportError:
        try:
            from tensorboard_plugin_profile.convert import raw_to_tool_data
        except ImportError as error:
            raise ImportError(
                "Reading a TensorBoard profile takes the profile plugin's "
                "converter: pip install xprof"
            ) from error
    data, _ = raw_to_tool_data.xspace_to_tool_data(paths, tool, {})
    return data.decode("utf-8") if isinstance(data, bytes) else data


def _tables(data: str | list) -> list[dict]:
    """A tool's JSON as a list of DataTables, whether text or parsed."""
    parsed = json.loads(data) if isinstance(data, str) else data
    return parsed if isinstance(parsed, list) else [parsed]


def _cells(table: dict) -> tuple[list[str], list[list[Any]]]:
    """A DataTable's column ids and its rows' values."""
    columns = [column.get("id", "") for column in table.get("cols", [])]
    rows = [
        [cell.get("v") if isinstance(cell, dict) else None for cell in row.get("c", [])]
        for row in table.get("rows", [])
    ]
    return columns, rows


def _step_table(tables: list[dict]) -> tuple[list[str], dict[str, np.ndarray]] | None:
    """
    Each step's name, and each component's milliseconds per step.

    The step-time graph is the ``input_pipeline_analyzer`` table with a
    ``stepnum`` column. A component that is zero at every step is left out,
    so the legend lists only where the time went.
    """
    for table in tables:
        columns, rows = _cells(table)
        if "stepnum" not in columns or not rows:
            continue
        index = {column: i for i, column in enumerate(columns)}
        names = [str(row[index["stepnum"]]) for row in rows]
        components = {}
        for column, label in _COMPONENTS.items():
            if column not in index:
                continue
            values = np.array([float(row[index[column]] or 0) for row in rows])
            if values.any():
                components[label] = values
        return (names, components) if components else None
    return None


def _op_types(tables: list[dict], top: int) -> list[tuple[str, float]]:
    """
    The operation types with the most total self time, in milliseconds.

    ``framework_op_stats`` gives the same operations twice, with and without
    the ``IDLE`` row, for the dashboard's toggle; host and device operations
    share each table. Only the first is read, so nothing is counted twice,
    and ``IDLE`` is left out.
    """
    totals: dict[str, float] = {}
    for table in tables:
        columns, rows = _cells(table)
        if "type" not in columns or "total_self_time" not in columns:
            continue
        index = {column: i for i, column in enumerate(columns)}
        for row in rows:
            kind = str(row[index["type"]])
            if kind == "IDLE":
                continue
            totals[kind] = totals.get(kind, 0.0) + float(
                row[index["total_self_time"]] or 0
            )
        break
    ranked = sorted(totals.items(), key=lambda item: -item[1])[:top]
    return [(kind, round(micro / 1000, 3)) for kind, micro in ranked if micro > 0]


def _draw_steps(
    names: list[str], components: dict[str, np.ndarray], session: str
) -> Figure:
    """One stacked bar per step, a segment per component, in legend order."""
    fig = Figure(figsize=(max(6.0, 0.5 * len(names) + 3), 4.5))
    ax = fig.add_subplot()
    bottom = np.zeros(len(names))
    for label, values in components.items():
        ax.bar(names, values, bottom=bottom, label=label)
        bottom = bottom + values
    ax.set_xlabel("Step")
    ax.set_ylabel("Step time (ms)")
    ax.set_title(f"Step-time graph {session}".strip())
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    return fig


def _draw_ops(ops: list[tuple[str, float]], session: str) -> Figure:
    """One horizontal bar per operation type, the largest at the top."""
    fig = Figure(figsize=(7.0, 0.4 * len(ops) + 1.6))
    ax = fig.add_subplot()
    kinds = [kind for kind, _ in ops][::-1]
    times = [time for _, time in ops][::-1]
    ax.barh(kinds, times, color="C0")
    ax.set_xlabel("Total self time (ms)")
    ax.set_ylabel("Operation type")
    ax.set_title(f"Top operations by self time {session}".strip())
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    return fig
