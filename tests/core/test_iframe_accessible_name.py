"""Every iframe maidr emits must carry an accessible name.

A frame with no ``title`` is announced as "frame" and nothing else, so a
notebook or dashboard of several charts gives a screen-reader user several
identical, indistinguishable landmarks -- the navigation problem this
library exists to solve. WCAG 2.2 4.1.2.
"""

from __future__ import annotations

import html as html_module
import re

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402
from maidr.util.iframe_utils import (  # noqa: E402
    DEFAULT_IFRAME_TITLE,
    iframe_title,
)


@pytest.fixture
def iframed(monkeypatch):
    """Force the iframe path, which only some environments take."""
    monkeypatch.setattr(Environment, "is_shiny", staticmethod(lambda: True))


def _title_of(tag) -> str | None:
    """Return the ``title`` attribute of a rendered iframe, unescaped."""
    match = re.search(r'title="(.*?)"', str(tag.get_html_string()))
    return html_module.unescape(match.group(1)) if match else None


@pytest.fixture
def bar_axes():
    """Yield the axes of a two-bar chart, closed afterwards."""
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    yield ax
    plt.close(fig)


# ---------------------------------------------------------------------------
# The name itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("Tips by day", "Tips by day"),
        # Unauthored in every shape the schema also treats as unauthored.
        ("   ", DEFAULT_IFRAME_TITLE),
        ("", DEFAULT_IFRAME_TITLE),
        (None, DEFAULT_IFRAME_TITLE),
    ],
)
def test_a_name_is_always_produced(given, expected):
    """Never empty: an unnamed frame is the failure being fixed."""
    assert iframe_title(given) == expected


# ---------------------------------------------------------------------------
# matplotlib
# ---------------------------------------------------------------------------


def test_a_titled_chart_is_named_by_its_title(iframed, bar_axes):
    """The chart's own title is the name the reader is looking for."""
    bar_axes.set_title("Tips by day")
    assert _title_of(maidr.render(bar_axes, use_cdn=True)) == "Tips by day"


def test_an_untitled_chart_still_gets_a_name(iframed, bar_axes):
    assert _title_of(maidr.render(bar_axes, use_cdn=True)) == DEFAULT_IFRAME_TITLE


def test_the_figure_title_outranks_a_panel_title(iframed):
    """The frame holds the whole figure, so the whole figure names it.

    Naming a multi-panel frame after one of its panels would announce a
    part as though it were the whole.
    """
    fig, (left, right) = plt.subplots(1, 2)
    left.bar(["a"], [1])
    right.bar(["b"], [2])
    left.set_title("Panel A")
    fig.suptitle("Whole figure")
    try:
        assert _title_of(maidr.render(left, use_cdn=True)) == "Whole figure"
    finally:
        plt.close(fig)


def test_a_panel_title_does_not_name_a_multi_panel_figure(iframed):
    """With no figure title, a generic name beats a misleading one."""
    fig, (left, right) = plt.subplots(1, 2)
    left.bar(["a"], [1])
    right.bar(["b"], [2])
    left.set_title("Panel A")
    try:
        assert _title_of(maidr.render(left, use_cdn=True)) == DEFAULT_IFRAME_TITLE
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# Plotly and Altair
# ---------------------------------------------------------------------------


def test_a_plotly_chart_is_named_by_its_layout_title(iframed):
    px = pytest.importorskip("plotly.express")
    figure = px.bar(x=["a", "b"], y=[1, 2], title="Plotly titled")
    assert _title_of(maidr.render(figure, use_cdn=True)) == "Plotly titled"


def test_an_untitled_plotly_chart_still_gets_a_name(iframed):
    px = pytest.importorskip("plotly.express")
    figure = px.bar(x=["a", "b"], y=[1, 2])
    assert _title_of(maidr.render(figure, use_cdn=True)) == DEFAULT_IFRAME_TITLE


def test_an_altair_chart_is_named_by_its_title(iframed):
    alt = pytest.importorskip("altair")
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"a": ["x", "y"], "b": [1, 2]})
    chart = alt.Chart(frame, title="Altair titled").mark_bar().encode(x="a", y="b")
    assert _title_of(maidr.render(chart)) == "Altair titled"


def test_an_untitled_altair_chart_still_gets_a_name(iframed):
    alt = pytest.importorskip("altair")
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"a": ["x", "y"], "b": [1, 2]})
    chart = alt.Chart(frame).mark_bar().encode(x="a", y="b")
    assert _title_of(maidr.render(chart)) == DEFAULT_IFRAME_TITLE


def test_an_altair_title_object_is_read_rather_than_stringified(iframed):
    """Altair accepts a ``TitleParams``, not only a plain string.

    Stringifying one would produce a repr as the accessible name.
    """
    alt = pytest.importorskip("altair")
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"a": ["x", "y"], "b": [1, 2]})
    chart = (
        alt.Chart(frame, title=alt.TitleParams(text="Structured title"))
        .mark_bar()
        .encode(x="a", y="b")
    )
    assert _title_of(maidr.render(chart)) == "Structured title"


# ---------------------------------------------------------------------------
# The guarantee
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("use_cdn", [True, "auto", False])
def test_no_cdn_mode_emits_an_unnamed_frame(iframed, bar_axes, use_cdn):
    """The name must not depend on how the runtime is delivered."""
    title = _title_of(maidr.render(bar_axes, use_cdn=use_cdn))
    assert title
