"""The plotnine probe must not import plotnine to say a figure is not a ggplot.

``render``, ``show``, ``save_html`` and ``close`` each ask whether the plot is
a ``ggplot``. One cannot exist unless the package is loaded, so
``sys.modules`` settles the negative case without an import -- the reasoning
``test_bokeh_probe_is_lazy.py`` pins for Bokeh. The positive case is covered
by ``tests/plotnine``.
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
        if name == "plotnine" or name.startswith("plotnine."):
            raise AssertionError(f"the probe imported {name}")
        return real_import(name, *args, **kwargs)

    return exploding_import


def test_plotnine_probe_does_not_import_plotnine(monkeypatch):
    for name in [
        m for m in sys.modules if m == "plotnine" or m.startswith("plotnine.")
    ]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(builtins, "__import__", _exploding_import(builtins.__import__))

    assert maidr.api._is_plotnine_plot(object()) is False
    assert "plotnine" not in sys.modules


def test_a_blocked_plotnine_import_is_not_a_ggplot(monkeypatch):
    """``sys.modules["plotnine"] = None`` is how an import is blocked."""
    monkeypatch.setitem(sys.modules, "plotnine", None)
    monkeypatch.setattr(builtins, "__import__", _exploding_import(builtins.__import__))

    assert maidr.api._is_plotnine_plot(object()) is False


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
print("plotnine" in sys.modules)
"""


def test_a_matplotlib_render_leaves_plotnine_unloaded():
    """The whole render path, in a process where the import would succeed."""
    pytest.importorskip("plotnine")

    completed = subprocess.run(
        [sys.executable, "-c", _RENDER_A_BAR_CHART],
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "MAIDR_USE_CDN": "false"},
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert completed.stdout.strip().splitlines()[-1] == "False", (
        "a render of a matplotlib figure imported plotnine"
    )
