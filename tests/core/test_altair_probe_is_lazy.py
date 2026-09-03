"""The Altair probe must not import Altair to say a figure is not one.

``render``, ``show`` and ``save_html`` each open by asking whether the
plot is an Altair chart.  Answering by importing altair costs ~1.6 s of
lark grammar compilation on every process's first render of a matplotlib
figure (#707).  An instance of ``alt.Chart`` cannot exist unless the
package is loaded, so ``sys.modules`` settles the negative case without
an import; the positive case is covered by ``tests/altair``.
"""

from __future__ import annotations

import builtins
import os
import subprocess
import sys

import pytest

import maidr


def test_altair_probe_does_not_import_altair(monkeypatch):
    """Mirrors ``test_is_shiny_survives_a_broken_shiny_install``."""
    real_import = builtins.__import__

    def exploding_import(name, *args, **kwargs):
        if name.startswith("altair"):
            raise AssertionError(f"the probe imported {name}")
        return real_import(name, *args, **kwargs)

    for name in [m for m in sys.modules if m == "altair" or m.startswith("altair.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(builtins, "__import__", exploding_import)

    assert maidr.api._is_altair_chart(object()) is False
    assert "altair" not in sys.modules


def test_a_blocked_altair_import_is_not_a_chart(monkeypatch):
    """``sys.modules["altair"] = None`` is how an import is blocked.

    The entry exists but is not a package, so it must read as "not
    loaded" -- the probe must not reach the import statement at all.
    """
    real_import = builtins.__import__

    def exploding_import(name, *args, **kwargs):
        if name.startswith("altair"):
            raise AssertionError(f"the probe imported {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setitem(sys.modules, "altair", None)
    monkeypatch.setattr(builtins, "__import__", exploding_import)

    assert maidr.api._is_altair_chart(object()) is False


_RENDER_A_BAR_CHART = """
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import maidr

fig, ax = plt.subplots()
ax.bar(["a", "b", "c"], [1, 2, 3])
maidr.render(ax, use_cdn=False).get_html_string()
print("altair" in sys.modules, "shiny" in sys.modules, "flask" in sys.modules)
"""


def test_a_bar_render_leaves_altair_shiny_and_flask_unloaded():
    """The whole render path, in a process where the imports would succeed.

    The unit test above pins the probe; this pins that nothing else on the
    matplotlib render path pulls either package in behind it.
    """
    pytest.importorskip("altair")
    pytest.importorskip("shiny")
    pytest.importorskip("flask")

    completed = subprocess.run(
        [sys.executable, "-c", _RENDER_A_BAR_CHART],
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "MAIDR_USE_CDN": "false"},
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert completed.stdout.strip().splitlines()[-1] == "False False False", (
        f"a render of a matplotlib figure imported altair, shiny or flask: "
        f"{completed.stdout.strip()!r}"
    )
