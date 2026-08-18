"""Clearing an axes forgets the layers drawn on it, and nothing else.

``Figure.clear`` was patched to drop a figure's registered layers;
``Axes.clear`` was not. Re-plotting into a cleared axes therefore *appended*
a layer, and the reader was offered one describing artists no longer drawn --
announced with confident values, and with a highlight resolving to nothing
because those artists never reach ``HighlightContextManager``. It accumulated:
five clear cycles left six layers (#499).

``ax.clear()`` is the ordinary way to redraw into a reused axes, so the two
spellings of the same intent behaved differently, and the correct one was the
less common for a single-axes figure.

The tests assert on the emitted layer count rather than on ``_plots``, because
the layer count is what a reader is offered. They also pin the neighbour cases
-- a second panel, and a ``twinx`` twin at the same grid cell -- since the fix
narrows ``clear()`` and the way to get that wrong is to take too much.

``selector_ids`` is checked alongside, because it is paired with ``_plots`` by
index in both directions and ``clear()`` used to empty only one of them. See
``Maidr._drop_superseded_layers`` for the invariant.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def layer_count(maidr_obj) -> int:
    """How many layers the emitted schema offers for the first subplot."""
    schema = maidr_obj._flatten_maidr()
    return len(schema["subplots"][0][0]["layers"])


def paired(maidr_obj) -> bool:
    """``_plots`` and ``selector_ids`` still line up by index."""
    return len(maidr_obj._plots) == len(maidr_obj.selector_ids)


@pytest.mark.parametrize("clear_it", [lambda ax: ax.clear(), lambda ax: plt.cla()])
def test_replotting_a_cleared_axes_replaces_the_layer(clear_it):
    """Both spellings reach the same ``Axes`` method and both were affected."""
    fig, ax = plt.subplots()
    ax.bar(["a", "b", "c"], [1, 2, 3])
    maidr_obj = FigureManager.get_maidr(fig)

    clear_it(ax)
    fig.gca().bar(["a", "b", "c"], [9, 9, 9])

    assert layer_count(maidr_obj) == 1, (
        "the cleared layer is still offered alongside the redrawn one"
    )
    layer = maidr_obj._flatten_maidr()["subplots"][0][0]["layers"][0]
    assert [point["y"] for point in layer["data"]] == [9.0, 9.0, 9.0], (
        "the surviving layer must be the redrawn one, not the discarded one"
    )


def test_repeated_clear_cycles_do_not_accumulate_layers():
    """The count is the point: it grew by one per cycle, unbounded."""
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    maidr_obj = FigureManager.get_maidr(fig)

    for i in range(5):
        ax.clear()
        ax.bar(["a", "b"], [i, i])

    assert layer_count(maidr_obj) == 1
    assert paired(maidr_obj)


def test_clearing_one_panel_leaves_the_other_registered():
    """``clear_axes`` is narrower than ``clear`` -- this is why."""
    fig, (first, second) = plt.subplots(1, 2)
    first.bar(["a", "b"], [1, 2])
    second.bar(["c", "d"], [3, 4])
    maidr_obj = FigureManager.get_maidr(fig)
    assert len(maidr_obj._plots) == 2

    first.clear()

    assert [plot.ax for plot in maidr_obj._plots] == [second], (
        "clearing one panel unregistered the other"
    )
    assert paired(maidr_obj)


def test_clearing_a_twin_leaves_the_axes_it_was_twinned_from():
    """``twinx`` puts a second axes at the same grid cell.

    Keyed by position rather than by axes, this pair collapses -- the same
    trap ``_layer_axes_key`` records for the supersede rules.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    twin = ax.twinx()
    twin.plot([0, 1], [5, 6])
    maidr_obj = FigureManager.get_maidr(fig)
    assert len(maidr_obj._plots) == 2

    twin.clear()

    assert [plot.ax for plot in maidr_obj._plots] == [ax], (
        "clearing the twin took the axes it was twinned from with it"
    )
    assert paired(maidr_obj)


def test_clearing_an_axes_that_holds_no_layers_is_a_no_op():
    """``Axes.clear`` and ``Axes.cla`` delegate to each other.

    Both are patched, so a single call can fire the hook twice. The second
    firing has to find nothing to do rather than disturb what the first left.
    """
    fig, (first, second) = plt.subplots(1, 2)
    first.bar(["a", "b"], [1, 2])
    maidr_obj = FigureManager.get_maidr(fig)
    before = list(maidr_obj._plots)

    second.clear()
    second.clear()

    assert maidr_obj._plots == before
    assert paired(maidr_obj)


def test_clearing_a_brand_new_axes_does_not_raise():
    """``Axes.__init__`` calls ``cla()``, so the hook fires before anything exists.

    An earlier version of this test used ``ax.plot()`` and claimed nothing
    was registered, which is wrong -- ``plot`` registers a LINE layer. The
    guard being pinned here is the one that keeps every axes construction
    from raising on a figure that has no maidr entry yet, so the test must
    not draw anything at all.
    """
    fig = plt.figure()
    ax = fig.add_subplot()  # `cla()` already fired here, unregistered

    ax.clear()  # must not raise
    fig.clear()  # the pre-existing guard, kept


@pytest.mark.parametrize("draw", ["plot", "step"])
def test_a_line_layer_is_registered_again_after_its_axes_is_cleared(draw):
    """The regression this fix could have shipped, and the worse failure.

    ``lineplot`` latches "this axes already has a layer" onto the axes
    itself. matplotlib does not reset it -- it does not own it -- so
    dropping the layers while leaving the latch set makes the redraw
    register nothing, and the chart is **undescribed** rather than
    mis-described: ``subplots: [[{}]]``.

    Worth both spellings: ``ax.step`` delegates to ``Axes.plot`` and goes
    through the same latch.
    """
    fig, ax = plt.subplots()
    getattr(ax, draw)([0, 1, 2], [1, 2, 3])
    maidr_obj = FigureManager.get_maidr(fig)
    assert len(maidr_obj._plots) == 1

    ax.clear()
    getattr(ax, draw)([0, 1, 2], [9, 8, 7])

    assert len(maidr_obj._plots) == 1, (
        "the redrawn line registered no layer; the chart is undescribed"
    )
    assert layer_count(maidr_obj) == 1
    assert paired(maidr_obj)


def test_clearing_an_axes_drops_the_accumulated_line_series():
    """The series list holds ``Line2D`` objects the clear detached.

    Left in place they are both stale and unbounded -- a redraw appends to
    the same list, so the layer would describe lines that are no longer
    drawn alongside the ones that are.
    """
    from maidr.patch.lineplot import DRAWN_SERIES, PLOT_CREATED

    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    assert len(getattr(ax, DRAWN_SERIES)) == 1
    assert hasattr(ax, PLOT_CREATED)

    ax.clear()

    assert not hasattr(ax, DRAWN_SERIES)
    assert not hasattr(ax, PLOT_CREATED)

    ax.plot([0, 1], [5, 6])
    assert len(getattr(ax, DRAWN_SERIES)) == 1, (
        "the redrawn layer is carrying lines from before the clear"
    )


def test_figure_clear_empties_every_axes_on_a_multi_axes_figure():
    """The cascade: ``Figure.clear`` clears its axes, and those are patched.

    So ``clear_axes`` runs per axes *and* ``clear()`` runs at the figure
    level. Both lists have to end up empty however the two interleave.
    """
    fig, (first, second) = plt.subplots(1, 2)
    first.bar(["a", "b"], [1, 2])
    second.bar(["c", "d"], [3, 4])
    maidr_obj = FigureManager.get_maidr(fig)
    assert len(maidr_obj._plots) == 2

    fig.clear()

    assert maidr_obj._plots == []
    assert maidr_obj.selector_ids == []


def test_clear_drops_the_selector_ids_with_the_layers():
    """The second half of #499, and the one that raised nothing.

    ``clear()`` emptied ``_plots`` and left ``selector_ids`` behind. The two
    are paired by index, so the next layer registered was tagged with the id
    minted for a layer that no longer existed, and its own id was never used.

    Called directly rather than through ``fig.clear()``, because ``clear()``
    is a *public method* that can be called on its own, and only calling it
    on its own pins what it does.

    That is the durable reason. There is also a version-dependent one: on
    the matplotlib this was written against (3.10.9), ``Figure.clear``
    clears its axes through ``Axes.clear``, which is patched, so the figure
    route reaches ``clear_axes`` first and drops both lists in step --
    measured, two axes giving two firings. Whether that holds is not a
    thing to rely on: some matplotlib versions detach a figure's axes with
    ``ax.remove()``, which would not route through the patch at all.
    Correctness does not depend on it either way, since ``Figure.clear``'s
    own patch calls ``maidr.clear()`` unconditionally -- but the test does,
    which is why it does not go that way round.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    maidr_obj = FigureManager.get_maidr(fig)
    discarded = list(maidr_obj.selector_ids)
    assert discarded, "the layer should have been registered with an id"

    maidr_obj.clear()

    assert maidr_obj._plots == []
    assert maidr_obj.selector_ids == [], (
        "the ids outlived the layers they were minted for"
    )

    ax.bar(["a", "b"], [9, 9])

    assert paired(maidr_obj)
    assert maidr_obj.selector_ids[0] not in discarded, (
        "the re-plotted layer is wearing the discarded layer's selector id"
    )


def _maidr_state_stashed_in(source_file):
    """Every place ``source_file`` puts maidr-owned state on another object.

    Yields ``(lineno, target, attribute)``. "maidr-owned" means the
    attribute name starts with ``_maidr`` -- either written literally, or
    named by a module-level constant holding such a string, which is how
    ``lineplot`` spells ``DRAWN_SERIES`` and ``PLOT_CREATED``.

    Both spellings of the assignment count: ``setattr(target, name, value)``
    and ``target.attr = value``. An earlier version of this guard looked
    only for ``setattr`` calls whose target was literally named ``ax`` or
    ``axes``, which missed direct assignment entirely and missed every
    module that binds its axes to ``instance`` or to a local of another
    name. Both idioms are already used elsewhere in ``maidr/patch``.
    """
    import ast

    tree = ast.parse(source_file.read_text())

    # Module-level string constants, so `setattr(ax, DRAWN_SERIES, ...)`
    # is read as the name it stands for rather than skipped.
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value

    def resolve(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return constants.get(node.id)
        return None

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 2
        ):
            name = resolve(node.args[1])
            if name and name.startswith("_maidr"):
                yield node.lineno, ast.unparse(node.args[0]), name

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Attribute):
                    continue
                if target.attr.startswith("_maidr"):
                    yield node.lineno, ast.unparse(target.value), target.attr


def test_no_new_module_stashes_maidr_state_on_an_axes():
    """``forget_axes_state`` only knows about the attributes it was told.

    Nothing makes a *future* patch module that stashes its own state on an
    axes register the cleanup there, and the failure would be the quiet one
    this file exists for: the layers are dropped, the new module's latch
    survives the clear, and the redraw registers nothing at all.

    Keyed on the *attribute* being maidr-owned rather than on the target
    being named ``ax``, because the target's name is the part that varies
    -- ``instance`` in a wrapt wrapper, or any local. What does not vary is
    that maidr's own state is spelled ``_maidr...``.

    State on an **artist** needs no cleanup: ``ax.clear()`` discards the
    artists, so it goes with them. Only state on the axes survives, which
    is what makes the target worth recording per entry.

    **Not a complete guarantee, and should not be leaned on as one.** It
    sees an attribute stashed under a name it can read statically -- a
    literal, or a module-level string constant. It does not see a name
    built at runtime (an f-string, a ``getattr`` result), and it does not
    see state kept *outside* the object at all, such as a module-level
    ``WeakKeyDictionary`` keyed by axes. Those would need the same cleanup
    and would pass here. What this catches is the shape the bug actually
    took, which is the shape a future module is most likely to repeat.
    """
    import pathlib

    #: (module, target) -> why it is safe. A new entry is a decision:
    #: on an axes, it must be removed in `forget_axes_state`; on an
    #: artist, the clear discards it.
    allowed = {
        ("lineplot.py", "ax"): "latch and series; forget_axes_state removes both",
        ("mplfinance.py", "line"): "on a Line2D; the clear discards the artist",
    }

    patch_dir = pathlib.Path(__file__).resolve().parents[2] / "maidr" / "patch"
    found = {}
    for source_file in sorted(patch_dir.glob("*.py")):
        for lineno, target, attribute in _maidr_state_stashed_in(source_file):
            found.setdefault((source_file.name, target), []).append((lineno, attribute))

    unexpected = {key: sites for key, sites in found.items() if key not in allowed}

    assert not unexpected, (
        f"{unexpected} stashes maidr-owned state on another object. If the "
        "target is an Axes, matplotlib will not reset it -- clearing the "
        "axes leaves it behind, and the next draw registers nothing. "
        "Remove it in `maidr.patch.lineplot.forget_axes_state` and add an "
        "entry to `allowed` here saying so. If the target is an artist, the "
        "clear discards it; add the entry saying that instead. See #499."
    )

    # The allowlist must not outlive what it describes: an entry for
    # something no longer there would quietly widen the guard.
    assert set(allowed) == set(found), (
        f"`allowed` lists {set(allowed) - set(found)}, which no longer exists"
    )
