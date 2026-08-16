"""The declared seaborn floor has to be a version that can import (#441).

`pyproject.toml` declared `seaborn>=0.12` while `maidr/patch/boxplot.py`
reached for `_CategoricalPlotter.plot_boxes`, which arrived with the
categorical rewrite in **0.13**. So on 0.12 the import raised:

    AttributeError: type object '_CategoricalPlotter' has no attribute 'plot_boxes'

at import time, before anything the user wrote could run. A declared floor is
a promise, and someone whose resolver landed on 0.12 -- an older lockfile, a
pin elsewhere in their environment -- got an `AttributeError` with nothing
saying their seaborn version was the reason.

The guard is in two halves, because either alone can drift:

* the attribute the patch reaches for must exist on the *installed* seaborn,
  which is what catches the next rename;
* the declared floor must be at least the release that introduced it, which
  is what catches the floor being lowered back under it.

It covers every private seaborn attribute a patch reaches for at import time,
not only the one that caused #441. `maidr/patch/histogram.py` and
`maidr/patch/kdeplot.py` reach `_DistributionPlotter.plot_univariate_histogram`
and `plot_univariate_density` so that `sns.displot` reads as the distribution
it draws (#446), and `maidr/patch/violinplot.py` and
`maidr/patch/boxenplot.py`, `maidr/patch/pointplot.py` and
`maidr/patch/barplot.py` reach `_CategoricalPlotter.plot_violins`,
`plot_boxens`, `plot_points` and `plot_bars` so that `sns.catplot` reads the chart it drew rather than the
scaffolding underneath it (#448, #449). Those carry the same risk for the same
reason: an attribute that moves breaks
`import maidr` for **everyone**, not only for users of that chart type.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

sns = pytest.importorskip("seaborn")

from packaging.version import Version  # noqa: E402

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: Every *private* seaborn attribute a patch reaches for at import time, with
#: the release that introduced it: module path, class, attribute, since.
#:
#: One entry per `wrapt.wrap_function_wrapper` call on a seaborn internal. The
#: risk they share is the one #441 was filed for -- an attribute that moves
#: breaks `import maidr` for **every** user, not only users of that chart --
#: so the list has to grow whenever a patch reaches for a new one. A patch
#: added without an entry here is exactly the case this file cannot catch.
#:
#: The versions are facts about seaborn rather than preferences, which is why
#: they are written down rather than derived.
PATCHED_INTERNALS = [
    (
        "seaborn.categorical",
        "_CategoricalPlotter",
        "plot_boxes",
        Version("0.13"),
    ),
    (
        "seaborn.categorical",
        "_CategoricalPlotter",
        "plot_violins",
        Version("0.13"),
    ),
    (
        "seaborn.categorical",
        "_CategoricalPlotter",
        "plot_boxens",
        Version("0.13"),
    ),
    (
        "seaborn.categorical",
        "_CategoricalPlotter",
        "plot_points",
        Version("0.13"),
    ),
    (
        "seaborn.categorical",
        "_CategoricalPlotter",
        "plot_bars",
        Version("0.13"),
    ),
    (
        "seaborn.distributions",
        "_DistributionPlotter",
        "plot_univariate_histogram",
        Version("0.11"),
    ),
    (
        "seaborn.distributions",
        "_DistributionPlotter",
        "plot_univariate_density",
        Version("0.11"),
    ),
]

#: The highest of them, which is what the declared floor has to clear.
REQUIRED_SINCE = max(since for *_, since in PATCHED_INTERNALS)


def declared_floors() -> list[Version]:
    """Every `seaborn>=X` lower bound `pyproject.toml` states."""
    found = re.findall(r'"seaborn>=([0-9][^",]*)"', PYPROJECT.read_text())

    assert found, "no seaborn requirement found in pyproject.toml"
    return [Version(text) for text in found]


@pytest.mark.parametrize(
    "module,cls,attribute,_since",
    PATCHED_INTERNALS,
    ids=[f"{cls}.{attribute}" for _, cls, attribute, _ in PATCHED_INTERNALS],
)
def test_the_patched_attribute_exists_on_the_installed_seaborn(
    module, cls, attribute, _since
):
    # What each patch does at import time, asked directly. If seaborn renames
    # or moves one, this says so instead of `import maidr` raising -- and it
    # names which attribute, which the AttributeError does too but only for
    # whichever patch happens to import first.
    import importlib

    owner = getattr(importlib.import_module(module), cls)

    assert hasattr(owner, attribute)


def test_every_declared_floor_can_actually_import():
    # Both dependency groups declare seaborn, and they drifted apart before.
    for floor in declared_floors():
        for module, cls, attribute, since in PATCHED_INTERNALS:
            assert floor >= since, (
                f"pyproject.toml allows seaborn {floor}, but "
                f"`{cls}.{attribute}` only exists from {since} -- "
                f"`import maidr` raises below that."
            )
        assert floor >= REQUIRED_SINCE


def test_the_installed_seaborn_satisfies_what_is_declared():
    # The floor being honest is worth nothing if the version under test sits
    # below it: the suite would be proving something about a version the
    # package says it does not support.
    installed = Version(sns.__version__)

    assert all(installed >= floor for floor in declared_floors())
