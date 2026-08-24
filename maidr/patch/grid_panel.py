"""
Name the panels of a seaborn ``PairGrid`` or ``JointGrid``.

seaborn titles neither grid's cells, so every panel of a pairplot announced
as ``Subplot N`` and a reader arrowing a 3x3 grid had to enter each panel and
read a data point to find out which pair of variables it was about (#660).

Both grids declare what each panel is, so the name is looked up rather than
guessed -- see :mod:`maidr.util.panel_title` for why that distinction is the
whole basis for doing this at all.
"""

from __future__ import annotations

from typing import Any, Callable

import wrapt

from maidr.util.panel_title import remember_panel_title


def _pair_title(row_var: str, col_var: str) -> str:
    """
    What an off-diagonal pair panel is called.

    ``"y vs x"``, in the order the panel's own axis labels announce once a
    reader is inside it -- so the lobby and the panel agree about which
    variable is which.

    Parameters
    ----------
    row_var : str
        The variable on y.
    col_var : str
        The variable on x.

    Returns
    -------
    str
        The panel's name, or ``""`` when either variable is unnamed.
    """
    if not row_var or not col_var:
        return ""
    return f"{row_var} vs {col_var}"


def _name_pair_cells(grid: Any) -> None:
    """
    Name every cell of a ``PairGrid``.

    Called after ``__init__``, when the grid knows its variables and its
    cells exist but nothing has been drawn into them yet -- which is early
    enough, because a layer's title is read at schema time rather than at
    registration.

    The diagonal is **not** named here even when a cell sits on it: with a
    univariate diagonal the data goes on a twin axes created later, and with
    no diagonal at all (``diag_kind=None``, or a bare ``PairGrid`` mapped
    with ``map``) the cell really does hold one variable against itself, and
    ``"x vs x"`` is what that draws.

    Parameters
    ----------
    grid : Any
        The ``PairGrid``.
    """
    axes = getattr(grid, "axes", None)
    x_vars = list(getattr(grid, "x_vars", ()) or ())
    y_vars = list(getattr(grid, "y_vars", ()) or ())
    if axes is None or not x_vars or not y_vars:
        return

    # `corner=True` leaves the upper triangle's cells as None, which
    # `remember_panel_title` skips -- the grid is always exactly
    # len(y_vars) x len(x_vars), so there is no index to guard against.
    for r, row in enumerate(axes):
        for c, cell in enumerate(row):
            remember_panel_title(cell, _pair_title(y_vars[r], x_vars[c]))


def _name_diagonal(grid: Any) -> None:
    """
    Name the univariate panels down a ``PairGrid``'s diagonal.

    ``map_diag`` is what creates them, and it creates **twin** axes rather
    than using the grid cells: measured on seaborn 0.13.2,
    ``diag_axes[0] is axes[0][0]`` is False, and a title set on the cell
    never reaches the histogram drawn on the twin. So this runs after
    ``map_diag`` and addresses the twins.

    Each is one variable's distribution, so it is named by that variable --
    the same shape the off-diagonals use, with one name instead of two.

    Parameters
    ----------
    grid : Any
        The ``PairGrid``, after ``map_diag``.
    """
    diag_axes = getattr(grid, "diag_axes", None)
    diag_vars = list(getattr(grid, "diag_vars", ()) or ())
    if diag_axes is None:
        return
    for i, ax in enumerate(diag_axes):
        if i < len(diag_vars):
            remember_panel_title(ax, diag_vars[i])


def _name_joint_panels(grid: Any) -> None:
    """
    Name a ``JointGrid``'s three panels.

    The grid names them structurally -- ``ax_joint`` is the bivariate panel,
    ``ax_marg_x`` and ``ax_marg_y`` the two marginals -- so which variable
    each is about is declared rather than read off the layout.

    Parameters
    ----------
    grid : Any
        The ``JointGrid``.
    """
    joint = getattr(grid, "ax_joint", None)
    if joint is None:
        return
    # ``JointGrid.__init__`` labels the joint axes from the variable names it
    # was given, so the label is the name. Measured across five spellings --
    # ``data=`` plus column names, two named Series, both through
    # ``jointplot``, and bare arrays -- ``grid.x.name`` and
    # ``ax_joint.get_xlabel()`` never disagreed, including on the arrays,
    # where both are empty. Reading the Series as well would be a second
    # source for one fact.
    x_name = joint.get_xlabel()
    y_name = joint.get_ylabel()

    remember_panel_title(joint, _pair_title(y_name, x_name))
    # A marginal is one variable's distribution, named the way a pair grid's
    # diagonal is: the top marginal draws x, the right marginal draws y.
    remember_panel_title(getattr(grid, "ax_marg_x", None), x_name)
    remember_panel_title(getattr(grid, "ax_marg_y", None), y_name)


def _after(name: Callable[[Any], None]) -> Callable:
    """
    Build a wrapper that runs ``name`` on the grid once the wrapped call
    returns.

    Both wrapped methods are asked about state the call itself produces --
    the cells, or the diagonal twins -- so naming has to happen afterwards.
    A failure to name a panel must not take the chart down with it, so
    anything raised here is swallowed: the cost is a panel announced by its
    position, which is exactly what it did before.

    Parameters
    ----------
    name : callable
        Given the grid, records its panels' titles.

    Returns
    -------
    callable
        A ``wrapt`` wrapper.
    """

    def wrapper(wrapped, instance, args, kwargs):
        result = wrapped(*args, **kwargs)
        try:
            name(instance)
        except Exception:
            pass
        return result

    return wrapper


wrapt.wrap_function_wrapper(
    "seaborn.axisgrid", "PairGrid.__init__", _after(_name_pair_cells)
)
wrapt.wrap_function_wrapper(
    "seaborn.axisgrid", "PairGrid.map_diag", _after(_name_diagonal)
)
wrapt.wrap_function_wrapper(
    "seaborn.axisgrid", "JointGrid.__init__", _after(_name_joint_panels)
)
