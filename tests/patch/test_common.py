"""``_argument`` reads a positional argument at the index its name binds to.

wrapt hands an unbound call, ``Axes.bar(ax, ...)``, to a patch through its
partial proxy: the instance is already out of ``args`` while the signature
``_argument`` inspects still opens with ``self``. Read naively, every index
landed one argument early, so a positional ``width`` was found in the
baseline's slot and a positional baseline was not found at all (#758).
"""

from __future__ import annotations

import wrapt

from maidr.patch.common import _argument


def _patched(name: str):
    """A class whose ``bar`` is patched the way ``Axes.bar`` is.

    Returns the class and the dict the patch records ``_argument``'s reading
    of ``name`` into, so a test can call ``bar`` bound or unbound and see
    what the patch saw.
    """
    seen = {}

    class Plotter:
        def bar(self, x, height, width=0.8, bottom=None):
            return x, height, width, bottom

    def patch(wrapped, instance, args, kwargs):
        seen["value"] = _argument(name, wrapped, args, kwargs)
        return wrapped(*args, **kwargs)

    wrapt.wrap_function_wrapper(Plotter, "bar", patch)
    return Plotter, seen


def test_a_bound_call_reads_a_positional_argument_by_its_index() -> None:
    Plotter, seen = _patched("bottom")
    Plotter().bar([0, 1], [2, 3], 0.4, [5, 6])

    assert seen["value"] == [5, 6]


def test_an_unbound_call_reads_the_same_argument_at_the_same_index() -> None:
    Plotter, seen = _patched("bottom")
    Plotter.bar(Plotter(), [0, 1], [2, 3], 0.4, [5, 6])

    assert seen["value"] == [5, 6]


def test_an_unbound_call_does_not_read_the_width_as_the_baseline() -> None:
    # The shape #758 measured: one slot early, the width landed on the
    # baseline's index and two side-by-side calls stopped reading as dodged.
    Plotter, seen = _patched("width")
    Plotter.bar(Plotter(), [0, 1], [2, 3], 0.4)

    assert seen["value"] == 0.4


def test_a_keyword_wins_over_the_position() -> None:
    Plotter, seen = _patched("width")
    Plotter().bar([0, 1], [2, 3], width=0.2)

    assert seen["value"] == 0.2


def test_an_argument_the_caller_left_out_is_none() -> None:
    Plotter, seen = _patched("bottom")
    Plotter().bar([0, 1], [2, 3])

    assert seen["value"] is None
