"""A colour probe is not a chart, and MAIDR was registering it as one.

``seaborn.utils._default_color`` resolves a default colour by *drawing* a
throwaway artist, reading its face colour, and removing it again. Every
branch ends in ``scout.remove()``::

    elif method.__name__ == "fill_between":
        kws = normalize_kwargs(kws, mpl.collections.PolyCollection)
        scout = method([], [], **kws)
        facecolor = scout.get_facecolor()
        color = to_rgb(facecolor[0])
        scout.remove()

It draws through ``Axes.fill_between``, ``Axes.plot``, ``Axes.scatter`` and
``Axes.bar`` -- all patched -- and it runs *before* any seaborn-level patch
has set a recursion context, so nothing suppressed it. Since #339 taught
MAIDR to read ``fill_between`` as an area chart, the probe registered a
layer describing a fill of two empty arrays (#373).

Measured across seaborn, before and after:

    rugplot     ExtractionError -> renders     (the probe's empty layer was
                                                fatal to the whole figure)
    ecdfplot    line            -> step        (same data, wrong chart)
    stripplot   4 layers        -> 3           (one per group, and one more)
    boxenplot   area, line, ... -> line, ...   (a real `boxen` layer
                                                since #253)

The `ecdfplot` row is the one worth reading twice. The layer count was
already right and the numbers were already right; the probe simply got
registered first and its ``ax.plot([], [])`` carried no ``drawstyle``, so
the shared line pass settled on ``line``. An ECDF announced as a line chart
rather than a step chart, with nothing in the output to catch.

The `rugplot` row is the #369 shape exactly: the phantom layer did not just
add noise, it raised ``ExtractionError`` when its data was read, and that is
fatal to the whole render rather than to its own layer. A scatter with a rug
over it -- which is how ``rugplot`` is actually used -- produced no HTML at
all.
"""

from __future__ import annotations

import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.patch.seaborn_probe import _patch_default_color  # noqa: E402

#: The modules that pull the probe in by name, plus the one that defines it.
CALL_SITES = [
    "seaborn.utils",
    "seaborn.categorical",
    "seaborn.distributions",
    "seaborn.relational",
]


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Three groups and a numeric column, enough for a categorical plot."""
    rng = np.random.default_rng(20260814)
    return pd.DataFrame({"group": list("abc") * 8, "value": rng.normal(size=24)})


def _is_wrapped(function) -> bool:
    """Whether wrapt has a wrapper installed on this object."""
    return type(function).__name__ == "FunctionWrapper"


def _layers(fig) -> list:
    """The plot types registered for a figure, or an empty list."""
    try:
        return [plot.type for plot in FigureManager.get_maidr(fig).plots]
    except KeyError:
        return []


def test_no_seaborn_module_holds_an_unwrapped_probe() -> None:
    """The binding, swept rather than listed.

    ``_default_color`` is a private helper imported by name into three
    modules, so ``__module__`` names one binding out of four and the call
    sites take the other three. This is the check that fails if seaborn adds
    a fourth importer -- which a hard-coded table would not notice, and which
    nothing downstream would report, since the symptom is a phantom layer in
    one function nobody thought to re-measure.
    """
    unwrapped = [
        name
        for name, module in sys.modules.items()
        if (name == "seaborn" or name.startswith("seaborn."))
        and getattr(module, "_default_color", None) is not None
        and not _is_wrapped(module._default_color)
    ]

    assert unwrapped == [], f"unwrapped probe bindings: {unwrapped}"


@pytest.mark.parametrize("module_name", CALL_SITES)
def test_the_known_call_sites_are_covered(module_name) -> None:
    """The sweep found the modules it was written for.

    The test above passes vacuously if the sweep wrapped *nothing*, so the
    four bindings that exist today are named here as well.
    """
    module = sys.modules[module_name]

    assert _is_wrapped(module._default_color)


def test_a_renamed_probe_warns(monkeypatch) -> None:
    """The one branch that cannot wrap anything, driven rather than assumed.

    If seaborn renames or drops ``_default_color`` there is nothing to
    suppress, and the phantom layer comes back with no other signal -- so the
    branch says so. Exercised by deleting the attribute, since it is
    unreachable on any seaborn this has been measured against.

    Safe to re-run ``_patch_default_color`` here: with the attribute gone it
    returns after warning, so nothing is double-wrapped, and ``monkeypatch``
    puts the probe back.
    """
    import seaborn.utils

    monkeypatch.delattr(seaborn.utils, "_default_color")

    with pytest.warns(UserWarning, match="_default_color is gone"):
        _patch_default_color()


def test_a_rug_over_a_scatter_renders() -> None:
    """The phantom layer was fatal, not merely noisy.

    ``rugplot`` draws its ticks as a ``LineCollection`` MAIDR does not read,
    so the only layer it registered was the probe -- and reading that layer's
    data raised ``ExtractionError``, which takes the whole figure with it
    rather than just its own layer. A scatter that would have read perfectly
    well produced nothing at all.
    """
    frame = _frame()
    fig, ax = plt.subplots()

    sns.scatterplot(data=frame, x="value", y="value", ax=ax)
    sns.rugplot(data=frame, x="value", ax=ax)

    assert _layers(fig) == [PlotType.SCATTER]

    # The render itself, because the layer list alone would not have caught
    # it: extraction is where the old failure happened.
    html = maidr.render(fig)
    assert html is not None


def test_an_ecdf_is_announced_as_a_step() -> None:
    """Right data, right layer count, wrong chart.

    The probe registered first, and its ``ax.plot([], [])`` carried no
    ``drawstyle``, so the shared line pass settled on ``line`` for a curve
    that is drawn ``steps-post``. Nothing about the reading looked wrong --
    which is what makes it worth a test rather than a comment.
    """
    fig, ax = plt.subplots()
    sns.ecdfplot(data=_frame(), x="value", ax=ax)

    assert _layers(fig) == [PlotType.STEP]


def test_a_strip_plot_registers_one_layer_per_group() -> None:
    """Three groups, three layers. It was four.

    ``_default_color`` probes through ``ax.scatter`` here, so the extra layer
    carried the *point* type -- indistinguishable from a real one in the
    layer list, and a fourth series to page through that the chart does not
    have.
    """
    fig, ax = plt.subplots()
    sns.stripplot(data=_frame(), x="group", y="value", ax=ax)

    assert _layers(fig) == [PlotType.SCATTER] * 3


def test_a_boxen_plot_carries_no_phantom_area() -> None:
    """The reproduction from the issue.

    The leading ``area`` was a fill of two empty arrays, and it is gone.

    When this was written ``boxenplot`` was not a supported plot type, so the
    case could only say what the layer is *not*. #253 gave it a real one, and
    the assertion is unchanged by that: a phantom area is wrong whether or not
    the layer beside it is now a letter-value ladder.
    """
    fig, ax = plt.subplots()
    sns.boxenplot(data=_frame(), x="group", y="value", ax=ax)

    assert PlotType.AREA not in _layers(fig)


def test_a_real_fill_between_is_untouched() -> None:
    """The control, and the thing that would be worst to break.

    Suppression is scoped to the probe's extent, so a fill a user actually
    asked for still registers. Without this, "no phantom areas" would be
    satisfiable by reading no areas at all.
    """
    fig, ax = plt.subplots()
    x = np.linspace(0, 10, 50)
    ax.fill_between(x, np.sin(x) + 2)

    assert _layers(fig) == [PlotType.AREA]
