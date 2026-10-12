"""A notebook shows a figure where and when the inline backend would, as its chart.

matplotlib_inline shows every figure a cell drew through pyplot when the cell
ends, without ``plt.show()``, and shows a figure that is a cell's value.
``import maidr`` replaces it with maidr's backend, which did neither: a cell
without ``plt.show()`` showed nothing and left its figure open for the next
cell's ``plt.show()`` or ``plt.plot()``, and ``fig`` on a cell's last line
showed ``<Figure size 640x480 with 1 Axes>``. :mod:`maidr.util.notebook_display`
gives the backend both.

These run cells in IPython's own shell, in this process, so its events,
display hook and formatters are IPython's; ``test_notebook_display_kernel.py``
runs the same cells in a real kernel.
"""

from __future__ import annotations

import io

import matplotlib
import matplotlib.pyplot as plt
import pytest

import maidr
from maidr.core.maidr import Maidr
from maidr.util import notebook_display
from maidr.util.environment import Environment
from maidr.util.notebook_display import (
    MAIDR_BACKEND,
    display_figure,
    flush_figures,
    install,
)

IPython = pytest.importorskip("IPython")
PIL = pytest.importorskip("PIL.Image")
pytest.importorskip("matplotlib_inline")

from IPython.core.interactiveshell import InteractiveShell  # noqa: E402
from IPython.core.pylabtools import print_figure  # noqa: E402
from IPython.utils.capture import capture_output  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib_inline.config import InlineBackend  # noqa: E402

_BARS = "fig, ax = plt.subplots()\n_ = ax.bar(['a', 'b'], [1, 2])\n"


@pytest.fixture
def kernel(monkeypatch):
    """IPython's shell with maidr's backend and notebook display, as a kernel has them."""
    shell = InteractiveShell.instance()
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))
    monkeypatch.setattr(notebook_display, "_state", notebook_display._State())
    InlineBackend.clear_instance()

    formatters = [
        *shell.display_formatter.formatters.values(),
        shell.display_formatter.ipython_display_formatter,
    ]
    printers = [(f, f.type_printers.get(Figure)) for f in formatters]
    for formatter in formatters:
        formatter.type_printers.pop(Figure, None)
    interactive = matplotlib.is_interactive()
    backend = matplotlib.get_backend()
    use_cdn = maidr.get_use_cdn()

    plt.switch_backend(MAIDR_BACKEND)
    # Each chart loads maidr.js from the CDN, so none stashes the bundle in
    # the output beside it; what is shown is then only charts and images.
    maidr.set_use_cdn(True)
    shell.user_ns.update({"plt": plt, "maidr": maidr})
    assert install(shell)
    yield shell

    # Only this one: ``plt.switch_backend`` registers pyplot's own, and
    # pyplot's ``ioff`` fails on a shell that has lost it.
    callbacks = shell.events.callbacks["post_execute"]
    while flush_figures in callbacks:
        callbacks.remove(flush_figures)
    for formatter, printer in printers:
        formatter.type_printers.pop(Figure, None)
        if printer is not None:
            formatter.type_printers[Figure] = printer
    matplotlib.interactive(interactive)
    maidr.set_use_cdn(use_cdn)
    plt.switch_backend(backend)
    InlineBackend.clear_instance()


def _run(shell, code: str):
    """Run ``code`` as a cell; return what it displayed and IPython's result."""
    with capture_output() as captured:
        result = shell.run_cell(code, store_history=False)
    return captured, result


def _charts(captured) -> list[str]:
    return [
        output.data["text/html"]
        for output in captured.outputs
        if "<iframe" in output.data.get("text/html", "")
    ]


def _images(captured) -> list[bytes]:
    return [
        output.data["image/png"]
        for output in captured.outputs
        if "image/png" in output.data
    ]


def _png_size(data) -> tuple[int, int]:
    import base64

    if isinstance(data, str):
        data = base64.b64decode(data)
    return PIL.open(io.BytesIO(data)).size


# -- the end of a cell ------------------------------------------------------


def test_a_cell_without_show_shows_its_chart_when_it_ends(kernel):
    captured, result = _run(kernel, _BARS)

    assert result.success
    assert len(_charts(captured)) == 1
    assert not _images(captured)
    assert plt.get_fignums() == []


def test_its_figure_is_not_left_for_the_next_cell_to_draw_into(kernel, monkeypatch):
    shown = []
    real_show = Maidr.show

    def show(self, *args, **kwargs):
        shown.append(self.fig)
        return real_show(self, *args, **kwargs)

    monkeypatch.setattr(Maidr, "show", show)
    _run(kernel, _BARS)
    captured, _ = _run(kernel, "plt.plot([1, 2, 3])\nplt.show()")

    assert len(_charts(captured)) == 1
    bars, line = shown
    assert line is not bars
    assert not line.axes[0].patches


def test_a_cell_that_shows_its_figure_shows_it_once(kernel):
    captured, _ = _run(kernel, _BARS + "plt.show()")

    assert len(_charts(captured)) == 1


def test_a_cell_that_opens_no_figure_shows_nothing(kernel):
    captured, _ = _run(kernel, "x = 1 + 1")

    assert captured.outputs == []


def test_a_cell_that_fails_still_shows_what_it_drew(kernel):
    """As matplotlib_inline does: the figure is drawn by the time of the error."""
    captured, result = _run(kernel, _BARS + "raise ValueError('boom')")

    assert not result.success
    assert len(_charts(captured)) == 1
    assert plt.get_fignums() == []


def test_a_chart_that_fails_is_a_traceback_and_the_others_are_shown(
    kernel, monkeypatch
):
    real_show = Maidr.show
    calls = []

    def show(self, *args, **kwargs):
        calls.append(self)
        if len(calls) == 1:
            raise RuntimeError("the first chart broke")
        return real_show(self, *args, **kwargs)

    monkeypatch.setattr(Maidr, "show", show)
    captured, result = _run(kernel, _BARS + _BARS.replace("fig,", "fig2,"))

    assert result.success
    assert "the first chart broke" in captured.stdout + captured.stderr
    assert len(_charts(captured)) == 1
    assert plt.get_fignums() == []


# -- a cell's value ---------------------------------------------------------


def test_a_figure_as_the_cells_value_is_its_chart_shown_once(kernel):
    captured, _ = _run(kernel, _BARS + "fig")

    assert len(_charts(captured)) == 1
    assert "<Figure size" not in captured.stdout
    assert not _images(captured)


def test_a_figure_shown_again_in_a_later_cell_is_still_its_chart(kernel):
    _run(kernel, _BARS)
    captured, _ = _run(kernel, "fig")

    assert len(_charts(captured)) == 1
    assert not _images(captured)


def test_display_shows_each_figure_once(kernel):
    code = (
        "figs = []\n"
        "for n in range(2):\n"
        "    f, a = plt.subplots()\n"
        "    _ = a.bar(['x', 'y'], [n + 1, 2])\n"
        "    figs.append(f)\n"
        "for f in figs:\n"
        "    display(f)\n"
    )
    captured, _ = _run(kernel, code)

    assert len(_charts(captured)) == 2


def test_display_figure_leaves_other_figures_to_ipython(kernel):
    """A figure with no chart, and any figure under another backend."""
    bare = Figure()
    with pytest.raises(NotImplementedError):
        display_figure(bare)

    _run(kernel, _BARS)
    plt.switch_backend("agg")
    try:
        with pytest.raises(NotImplementedError):
            display_figure(kernel.user_ns["fig"])
    finally:
        plt.switch_backend(MAIDR_BACKEND)


# -- shown once -------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "maidr.show(fig)",
        "maidr.show(fig, clear_fig=False)",
        "maidr.render(ax)",
        "html = maidr.render(ax)",
    ],
)
def test_a_figure_maidr_showed_or_rendered_is_not_shown_again(kernel, line):
    captured, _ = _run(kernel, _BARS + line)

    # ``render`` returns its chart; the value is the cell's to show.
    expected = 0 if "render" in line else 1
    assert len(_charts(captured)) == expected
    assert plt.get_fignums() == []


def test_a_chart_rendered_for_elsewhere_still_shows_its_figure(kernel):
    """``maidr.save_html``, MLflow and the app widgets: like a figure saved to a file."""
    kernel.user_ns["elsewhere"] = notebook_display.elsewhere
    captured, _ = _run(kernel, _BARS + "with elsewhere():\n    _ = maidr.render(ax)")

    assert len(_charts(captured)) == 1


def test_save_html_still_shows_its_figure(kernel, tmp_path):
    path = (tmp_path / "chart.html").as_posix()
    captured, _ = _run(kernel, _BARS + f"_ = maidr.save_html(ax, {path!r})")

    assert len(_charts(captured)) == 1


# -- the inline backend's settings -----------------------------------------


def test_ioff_keeps_a_figure_back(kernel):
    code = "with plt.ioff():\n    fig = plt.figure()\n    _ = fig.add_subplot().bar(['a'], [1])"
    captured, _ = _run(kernel, code)

    assert captured.outputs == []
    assert plt.get_fignums() == [kernel.user_ns["fig"].number]


def test_with_close_figures_off_each_cell_shows_its_own_and_keeps_them_open(kernel):
    InlineBackend.instance().close_figures = False

    first, _ = _run(kernel, _BARS)
    second, _ = _run(kernel, _BARS.replace("fig,", "fig2,"))

    assert len(_charts(first)) == 1
    assert len(_charts(second)) == 1
    assert len(plt.get_fignums()) == 2


def test_another_backend_shows_its_own_figures(kernel):
    plt.switch_backend("agg")
    try:
        captured, _ = _run(kernel, _BARS)
    finally:
        plt.switch_backend(MAIDR_BACKEND)

    assert captured.outputs == []


def test_a_figure_with_no_chart_is_the_image_the_notebook_shows_of_it(kernel):
    code = "fig, ax = plt.subplots()\n_ = ax.text(0.5, 0.5, 'only text')"
    with pytest.warns(UserWarning, match="not yet supported"):
        captured, _ = _run(kernel, code)

    images = _images(captured)
    assert len(images) == 1
    assert not _charts(captured)

    same, ax = plt.subplots()
    ax.text(0.5, 0.5, "only text")
    expected = print_figure(same, "png", bbox_inches="tight")
    assert _png_size(images[0]) == _png_size(expected)


# -- install ----------------------------------------------------------------


def test_install_runs_first_and_once(kernel):
    install(kernel)
    install(kernel)

    callbacks = kernel.events.callbacks["post_execute"]
    assert callbacks[0] is flush_figures
    assert callbacks.count(flush_figures) == 1


def test_install_keeps_a_registered_figure_formatter(kernel):
    from matplotlib_inline.backend_inline import set_matplotlib_formats

    set_matplotlib_formats("svg")
    install(kernel)

    formatters = kernel.display_formatter.formatters
    formatters["image/svg+xml"].lookup_by_type(Figure)
    with pytest.raises(KeyError):
        formatters["image/png"].lookup_by_type(Figure)


def test_install_registers_the_inline_backends_formatter_when_none_is(kernel):
    printer = kernel.display_formatter.formatters["image/png"].lookup_by_type(Figure)

    assert printer.keywords["fmt"] == "png"
    assert printer.keywords["bbox_inches"] == "tight"


def test_install_turns_interactive_mode_on_once(kernel):
    assert matplotlib.is_interactive()
    plt.ioff()
    install(kernel)

    assert not matplotlib.is_interactive()


def test_figures_are_not_queued_outside_a_notebook(monkeypatch):
    monkeypatch.setattr(notebook_display, "_state", notebook_display._State())
    monkeypatch.setattr(matplotlib, "is_interactive", lambda: True)
    backend = matplotlib.get_backend()
    plt.switch_backend(MAIDR_BACKEND)
    try:
        plt.subplots()
    finally:
        plt.switch_backend(backend)

    assert notebook_display._state.to_draw == []
    assert not notebook_display._state.draw_called


def test_interact_shows_the_figures_its_function_drew(kernel):
    """ipywidgets' hook for matplotlib_inline flushes maidr's figures too."""
    interaction = pytest.importorskip("ipywidgets.widgets.interaction")
    code = (
        "fig, ax = plt.subplots()\n"
        "_ = ax.bar(['a', 'b'], [1, 2])\n"
        "show_inline_matplotlib_plots()\n"
        "print(plt.get_fignums())\n"
    )
    kernel.user_ns["show_inline_matplotlib_plots"] = (
        interaction.show_inline_matplotlib_plots
    )
    captured, _ = _run(kernel, code)

    assert len(_charts(captured)) == 1
    assert "[]" in captured.stdout


@pytest.mark.parametrize("has_hook", [True, False])
def test_the_ipywidgets_hook_is_wrapped_only_where_it_exists(monkeypatch, has_hook):
    """A newer ipywidgets without it, or with other arguments, still imports."""
    import sys
    import types

    name = "maidr_test_fake_interaction"
    module = types.ModuleType(name)
    calls = []
    if has_hook:

        def show_inline_matplotlib_plots(*args, **kwargs):
            calls.append((args, kwargs))

        module.show_inline_matplotlib_plots = show_inline_matplotlib_plots
    monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(notebook_display, "_widgets_hooked", [False])
    monkeypatch.setattr(notebook_display, "_WIDGETS_MODULE", name)
    flushed = []
    monkeypatch.setattr(notebook_display, "flush_figures", lambda: flushed.append(1))

    notebook_display._hook_ipywidgets()

    if has_hook:
        module.show_inline_matplotlib_plots("any", future=True)
        assert calls == [(("any",), {"future": True})]
        assert flushed == [1]
    else:
        assert not hasattr(module, "show_inline_matplotlib_plots")
