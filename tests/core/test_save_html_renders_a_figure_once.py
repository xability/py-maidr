"""`maidr.save_html(fig)` renders the figure once, however many axes it has.

Handed a `Figure` -- which includes the default, `plt.gcf()` -- `save_html`
walked `fig.axes` and built a complete HTML document for every axes, then
wrote the last one. Every axes of a figure resolves to the same `Maidr`,
so a `subplots(3, 3)` grid was rendered nine times for one file; `render`
and `show` only looked the `Maidr` up in that loop (#694).
"""

from __future__ import annotations

import html
import json
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402
from maidr.core.maidr import Maidr  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture
def renders(monkeypatch):
    """Count how many times the chart is rendered to markup."""
    calls = []
    original = Maidr._build_html_tag

    def counting(self, *args, **kwargs):
        calls.append(None)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Maidr, "_build_html_tag", counting)
    return calls


def _two_by_two():
    fig, axs = plt.subplots(2, 2)
    for ax in axs.flat:
        ax.bar(["a", "b"], [1, 2])
    return fig


def _subplot_count(page: str) -> int:
    match = re.search(r'maidr="([^"]*)"', page)
    assert match, "no MAIDR schema in the saved page"
    schema = json.loads(html.unescape(match.group(1)))
    return sum(len(row) for row in schema["subplots"])


def test_a_figure_is_rendered_once(renders, tmp_path):
    fig = _two_by_two()
    target = tmp_path / "o.html"

    maidr.save_html(fig, file=str(target), use_cdn=False)

    assert len(renders) == 1
    assert _subplot_count(target.read_text(encoding="utf-8")) == 4


def test_the_current_figure_is_rendered_once(renders, tmp_path):
    _two_by_two()
    target = tmp_path / "o.html"

    maidr.save_html(file=str(target), use_cdn=False)

    assert len(renders) == 1
    assert _subplot_count(target.read_text(encoding="utf-8")) == 4
