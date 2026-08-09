"""The warnings a patched plot suppresses stay inside that plot's call.

Every patched plotting function is drawn through
``maidr.patch.common._draw_quietly``, which silences matplotlib's own warnings
so they do not reach a screen-reader user mid-render. That suppression used to
be installed process-wide and never removed, so the first plot of a session
muted every ``warnings.warn`` raised afterwards — anywhere, arbitrarily far
from any figure, including MAIDR's own diagnostics, which are raised while the
schema is built rather than while the figure is drawn.

``common`` is the path every plot type but pie takes, so it is pinned here
rather than only through the one type that has its own patch.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import warnings  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402  # activates patches


def _draw(kind: str, ax) -> None:
    """Draw one patched plot of the named kind on ``ax``."""
    if kind == "bar":
        ax.bar(["a", "b"], [1, 2])
    elif kind == "barh":
        ax.barh(["a", "b"], [1, 2])
    elif kind == "plot":
        ax.plot([1, 2, 3], [4, 5, 6])
    elif kind == "scatter":
        ax.scatter([1, 2, 3], [4, 5, 6])
    elif kind == "hist":
        ax.hist([1, 1, 2, 3, 3, 3])
    else:  # pragma: no cover - guards a typo in the parametrisation
        raise AssertionError(f"unknown plot kind: {kind}")


@pytest.mark.parametrize("kind", ["bar", "barh", "plot", "scatter", "hist"])
def test_a_warning_raised_after_the_plot_still_reaches_the_caller(kind):
    fig, ax = plt.subplots()
    try:
        _draw(kind, ax)

        # Deliberately no `simplefilter` here: the recorder inherits whatever
        # filters are installed, which is the whole point. Forcing "always"
        # would override a leaked "ignore" and the test would pass either way.
        with warnings.catch_warnings(record=True) as caught:
            warnings.warn(f"heard after the {kind}", UserWarning)

        assert [str(w.message) for w in caught] == [f"heard after the {kind}"]
    finally:
        plt.close(fig)


def test_the_plot_call_leaves_the_filter_list_as_it_found_it():
    # `catch_warnings` restores what it saved, so drawing must be neutral --
    # the leak this guards against was a filter that outlived the call.
    fig, ax = plt.subplots()
    try:
        before = list(warnings.filters)
        ax.bar(["a", "b"], [1, 2])

        assert warnings.filters == before
    finally:
        plt.close(fig)


def test_repeated_plots_do_not_accumulate_filters():
    # Not a growth guard -- CPython's `warnings._add_filter` de-duplicates, so
    # even the old process-wide call could not accumulate. This pins that
    # drawing is neutral however many times it happens.
    fig, ax = plt.subplots()
    try:
        before = len(warnings.filters)
        for _ in range(25):
            ax.bar(["a", "b"], [1, 2])

        assert len(warnings.filters) == before
    finally:
        plt.close(fig)
