"""Tests for the Gradio integration in ``maidr.widget.gradio``.

``render_maidr`` needs no Gradio at all, so most of these run anywhere; the
component tests skip without it. What a reader does with the frame in a real
Gradio app is driven in ``tests/browser/test_gradio_chart.py``.
"""

from __future__ import annotations

import html
import re
import warnings

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from maidr.util.dependencies import read_bundled_js  # noqa: E402
from maidr.widget.gradio import output_maidr, render_maidr  # noqa: E402

#: A slice of the real bundle, so "is the bundle inlined?" is answered by
#: looking for the bundle rather than by a size threshold.
_BUNDLE_HEAD = read_bundled_js()[:200]


@pytest.fixture
def bar_axes():
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    ax.set_title("Sales")
    yield ax
    plt.close(fig)


def _srcdoc(markup: str) -> str:
    found = re.search(r'srcdoc="([^"]*)"', markup)
    assert found, "the markup carries no srcdoc"
    return html.unescape(found.group(1))


def test_the_chart_is_an_iframe_named_after_it(bar_axes):
    markup = render_maidr(bar_axes)

    assert markup.startswith("<iframe")
    assert 'title="Sales, accessible chart"' in markup
    assert "data-maidr-chart" in markup
    assert 'allow="bluetooth; serial; hid"' in markup
    assert "maidr" in _srcdoc(markup)


def test_the_bundle_goes_inside_when_asked_to_work_offline(bar_axes):
    assert _BUNDLE_HEAD in _srcdoc(render_maidr(bar_axes, use_cdn=False))
    assert _BUNDLE_HEAD not in _srcdoc(render_maidr(bar_axes, use_cdn=True))


def test_no_chart_is_refused_rather_than_read_from_pyplot(bar_axes):
    with pytest.raises(TypeError, match="takes the chart to render"):
        render_maidr(None)


def test_a_chart_a_reader_returned_renders(tmp_path):
    from maidr.wandb import read_wandb_history

    rows = [{"_step": step, "loss": 1 / (step + 1)} for step in range(5)]
    (chart,) = read_wandb_history({"run": rows})
    assert 'title="loss, accessible chart"' in render_maidr(chart)


def test_a_warning_points_at_the_callers_line(monkeypatch, bar_axes):
    # Any warning the render raises -- here, the one for a chart that loads
    # maidr.js from nowhere -- should name this file, not maidr's.
    import maidr.widget._document as document

    monkeypatch.setattr(document, "inline_bundle_tags", lambda: None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        render_maidr(bar_axes, use_cdn=False)
    assert caught, "the render raised no warning to point anywhere"
    assert {w.filename for w in caught} == {__file__}


def test_the_component_holds_the_chart(bar_axes):
    gr = pytest.importorskip("gradio")
    with gr.Blocks():
        component = output_maidr(bar_axes, elem_id="sales")
    assert isinstance(component, gr.HTML)
    assert component.elem_id == "sales"
    assert component.value.startswith("<iframe")


def test_an_empty_component_waits_for_a_handler():
    gr = pytest.importorskip("gradio")
    with gr.Blocks():
        component = output_maidr()
    assert not component.value


def test_without_gradio_the_extra_is_named(monkeypatch, bar_axes):
    import builtins
    import sys

    # Where the extra installs Gradio; below it the advice is to install
    # Gradio itself (tests/widget/test_extras.py).
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))

    real_import = builtins.__import__

    def no_gradio(name, *args, **kwargs):
        if name == "gradio" or name.startswith("gradio."):
            raise ModuleNotFoundError("No module named 'gradio'", name="gradio")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_gradio)
    with pytest.raises(ImportError, match=r'pip install "maidr\[gradio\]"'):
        output_maidr(bar_axes)
