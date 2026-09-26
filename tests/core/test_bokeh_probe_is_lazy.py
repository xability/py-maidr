"""The Bokeh probe must not import Bokeh to say a figure is not one.

``render``, ``show``, ``save_html`` and ``close`` each ask whether the plot
is a Bokeh model. An instance of one cannot exist unless the package is
loaded, so ``sys.modules`` settles the negative case without an import --
the same reasoning ``test_altair_probe_is_lazy.py`` pins for Altair. The
positive case is covered by ``tests/bokeh``.
"""

from __future__ import annotations

import builtins
import os
import subprocess
import sys

import pytest

import maidr


def _exploding_import(real_import):
    def exploding_import(name, *args, **kwargs):
        if name == "bokeh" or name.startswith("bokeh."):
            raise AssertionError(f"the probe imported {name}")
        return real_import(name, *args, **kwargs)

    return exploding_import


def test_bokeh_probe_does_not_import_bokeh(monkeypatch):
    for name in [m for m in sys.modules if m == "bokeh" or m.startswith("bokeh.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(builtins, "__import__", _exploding_import(builtins.__import__))

    assert maidr.api._is_bokeh_model(object()) is False
    assert "bokeh" not in sys.modules


def test_a_blocked_bokeh_import_is_not_a_model(monkeypatch):
    """``sys.modules["bokeh"] = None`` is how an import is blocked."""
    monkeypatch.setitem(sys.modules, "bokeh", None)
    monkeypatch.setattr(builtins, "__import__", _exploding_import(builtins.__import__))

    assert maidr.api._is_bokeh_model(object()) is False


_RENDER_A_BAR_CHART = """
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import maidr

fig, ax = plt.subplots()
ax.bar(["a", "b", "c"], [1, 2, 3])
maidr.render(ax, use_cdn=False).get_html_string()
maidr.close(ax)
print("bokeh" in sys.modules)
"""


def test_a_matplotlib_render_leaves_bokeh_unloaded():
    """The whole render path, in a process where the import would succeed."""
    pytest.importorskip("bokeh")

    completed = subprocess.run(
        [sys.executable, "-c", _RENDER_A_BAR_CHART],
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "MAIDR_USE_CDN": "false"},
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert completed.stdout.strip().splitlines()[-1] == "False", (
        "a render of a matplotlib figure imported bokeh"
    )
