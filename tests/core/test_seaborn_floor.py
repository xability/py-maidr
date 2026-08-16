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
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

sns = pytest.importorskip("seaborn")

from packaging.version import Version  # noqa: E402

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: The release that introduced `_CategoricalPlotter.plot_boxes`, and so the
#: earliest seaborn `maidr/patch/boxplot.py` can import against. A fact about
#: seaborn rather than a preference, which is why it is written down rather
#: than derived.
PLOT_BOXES_SINCE = Version("0.13")


def declared_floors() -> list[Version]:
    """Every `seaborn>=X` lower bound `pyproject.toml` states."""
    found = re.findall(r'"seaborn>=([0-9][^",]*)"', PYPROJECT.read_text())

    assert found, "no seaborn requirement found in pyproject.toml"
    return [Version(text) for text in found]


def test_the_patched_attribute_exists_on_the_installed_seaborn():
    # What the patch does at import time, asked directly. If seaborn renames
    # or moves it, this says so instead of `import maidr` raising.
    from seaborn.categorical import _CategoricalPlotter

    assert hasattr(_CategoricalPlotter, "plot_boxes")


def test_every_declared_floor_can_actually_import():
    # Both dependency groups declare seaborn, and they drifted apart before.
    for floor in declared_floors():
        assert floor >= PLOT_BOXES_SINCE, (
            f"pyproject.toml allows seaborn {floor}, but "
            f"`_CategoricalPlotter.plot_boxes` only exists from "
            f"{PLOT_BOXES_SINCE} -- `import maidr` raises below that."
        )


def test_the_installed_seaborn_satisfies_what_is_declared():
    # The floor being honest is worth nothing if the version under test sits
    # below it: the suite would be proving something about a version the
    # package says it does not support.
    installed = Version(sns.__version__)

    assert all(installed >= floor for floor in declared_floors())
