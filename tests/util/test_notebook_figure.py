"""A chart in a notebook's frame has the size and shape of the inline backend's image.

A notebook shows a plain matplotlib figure as the image matplotlib_inline
makes of it: IPython's ``print_figure`` (or ``retina_figure``) with
``InlineBackend.print_figure_kwargs``, in the first of
``InlineBackend.figure_formats`` the frontend shows. ``import maidr`` takes
the backend over before matplotlib_inline registers anything, so
:mod:`maidr.util.notebook_figure` registers the ``InlineBackend``
configuration with the shell, so that ``%config`` reaches it, and reads the
figure's display formatter when there is one and the configuration when
there is not. The chart's SVG is then given that image's box and size by
``size_like_plain_figure``, which ``tests/util/test_inline_figure_size.py``
holds to IPython's own output; here the sizes are held to it again through
a whole render, in a notebook and out of one.

Whether a browser then shows the two alike is
``tests/browser/test_notebook_figure_size.py``.
"""

from __future__ import annotations

import sys

import io
import json
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from lxml import etree  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402
from maidr.util.notebook_figure import (  # noqa: E402
    in_notebook_frame,
    notebook_figure_format,
    register_inline_backend,
)

IPython = pytest.importorskip("IPython")
PIL = pytest.importorskip("PIL.Image")
matplotlib_inline = pytest.importorskip("matplotlib_inline")

from IPython.core.formatters import DisplayFormatter  # noqa: E402
from IPython.core.interactiveshell import InteractiveShellABC  # noqa: E402
from IPython.core.pylabtools import (  # noqa: E402
    print_figure,
    retina_figure,
    select_figure_formats,
)
from matplotlib_inline.config import InlineBackend  # noqa: E402
from traitlets.config import Config, Configurable  # noqa: E402

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class _Shell(Configurable):
    """A kernel's shell, as far as ``%config`` and the figure formatter go."""

    def __init__(self) -> None:
        super().__init__()
        self.display_formatter = DisplayFormatter()
        self.configurables: list = []
        self.user_ns: dict = {}


InteractiveShellABC.register(_Shell)


@pytest.fixture
def shell(monkeypatch):
    """A notebook kernel's shell, with no inline backend set up, as maidr leaves it."""
    InlineBackend.clear_instance()
    kernel = _Shell()
    monkeypatch.setattr(IPython, "get_ipython", lambda: kernel)
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))
    yield kernel
    InlineBackend.clear_instance()


def _config(kernel, line: str) -> None:
    """Run ``%config <line>`` in the kernel, as IPython's magic runs it.

    ``ConfigMagics.config`` builds a ``Config`` from the line and hands it to
    every configurable the shell lists, and to nothing else.
    """
    cfg = Config()
    exec("cfg." + line, {}, {"cfg": cfg})
    for configurable in kernel.configurables:
        configurable.update_config(cfg)


def _figure(size=(4, 3), dpi=100, **kwargs):
    fig, ax = plt.subplots(figsize=size, dpi=dpi, **kwargs)
    ax.bar(["Q1", "Q2", "Q3"], [3, 7, 2])
    ax.set_xlabel("Quarter")
    ax.set_ylabel("Units")
    return fig


def _png_size(data) -> tuple[int, int]:
    return PIL.open(io.BytesIO(data)).size


def _chart_svg(html: str):
    """The chart's ``<svg>`` in a render's output, in a frame's ``srcdoc`` or not."""
    import html as html_module

    for text in (html, html_module.unescape(html)):
        for match in re.finditer(r"<svg\b[^>]*>", text):
            if " maidr=" in match.group(0):
                end = text.index("</svg>", match.start()) + len("</svg>")
                return etree.fromstring(text[match.start() : end].encode())
    raise AssertionError("no chart svg in the output")


def _render(fig, **kwargs) -> str:
    try:
        return str(FigureManager.get_maidr(fig).render(**kwargs))
    finally:
        plt.close(fig)


def _px(value: str) -> float:
    assert value.endswith("px"), value
    return float(value[:-2])


def _view(svg) -> list[float]:
    return [float(v) for v in svg.get("viewBox").split()]


# --- What the inline backend is set to ---------------------------------------


def test_without_a_shell_the_inline_backends_defaults(monkeypatch):
    monkeypatch.setattr(IPython, "get_ipython", lambda: None)

    assert notebook_figure_format() == ("png", {"bbox_inches": "tight"})


def test_a_fresh_kernel_reads_the_configurations_defaults(shell):
    assert notebook_figure_format() == ("png", {"bbox_inches": "tight"})


def test_the_configuration_is_listed_with_the_shell(shell):
    config = register_inline_backend()

    assert config is InlineBackend.instance()
    assert config in shell.configurables
    assert config.shell is shell
    # Once, however often it is asked for.
    register_inline_backend()
    assert shell.configurables.count(config) == 1


def test_without_matplotlib_inline_the_defaults_are_read(shell, monkeypatch):
    """Nothing to register: the chart takes the inline backend's defaults."""
    monkeypatch.setitem(sys.modules, "matplotlib_inline.config", None)

    assert register_inline_backend() is None
    assert shell.configurables == []
    assert notebook_figure_format() == ("png", {"bbox_inches": "tight"})


def test_config_magic_went_nowhere_before_the_configuration_was_listed(shell):
    """The bug: with maidr's backend, ``%config InlineBackend`` reached nothing."""
    _config(shell, "InlineBackend.figure_formats = ['svg']")

    assert notebook_figure_format()[0] == "png"


@pytest.mark.parametrize(
    "formats, shown",
    [
        (["retina"], "retina"),
        (["png2x"], "retina"),
        (["png"], "png"),
        (["jpeg"], "jpeg"),
        (["jpg"], "jpeg"),
        (["svg"], "svg"),
        (["pdf"], "pdf"),
        # The one the frontend shows: JupyterLab and nbconvert rank an SVG
        # first, and a retina formatter replaces the plain PNG one.
        (["png", "svg"], "svg"),
        (["png", "retina"], "retina"),
        (["jpeg", "png"], "png"),
        (["pdf", "png"], "png"),
    ],
)
def test_config_magic_sets_the_format(shell, formats, shown):
    register_inline_backend()
    _config(shell, f"InlineBackend.figure_formats = {formats!r}")

    assert notebook_figure_format()[0] == shown


def test_config_magic_registers_the_formatter_as_without_maidr(shell):
    """A ``%config`` registers the figure's display formatter, as matplotlib_inline's would."""
    from matplotlib.figure import Figure

    register_inline_backend()
    _config(shell, "InlineBackend.figure_formats = ['retina']")

    printer = shell.display_formatter.formatters["image/png"].lookup_by_type(Figure)
    assert getattr(printer, "func", printer) is retina_figure


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bbox_inches": None},
        {"bbox_inches": "tight", "pad_inches": 0.5},
        {"bbox_inches": "tight", "dpi": 150},
        {"dpi": 72},
    ],
)
def test_config_magic_sets_the_print_figure_kwargs(shell, kwargs):
    register_inline_backend()
    _config(shell, f"InlineBackend.print_figure_kwargs = {kwargs!r}")

    figure_format, keywords = notebook_figure_format()
    assert figure_format == "png"
    assert {k: keywords[k] for k in kwargs} == kwargs


def test_the_configuration_is_read_when_no_formatter_is_registered(shell):
    """Settings the configuration took without a shell to register a formatter on."""
    config = register_inline_backend()
    config.shell = None
    config.figure_formats = {"svg"}
    config.print_figure_kwargs = {"bbox_inches": None}

    assert notebook_figure_format() == ("svg", {"bbox_inches": None})


def test_no_format_at_all_keeps_the_default(shell):
    config = register_inline_backend()
    config.shell = None
    config.figure_formats = set()

    assert notebook_figure_format() == ("png", {"bbox_inches": "tight"})


def test_a_registered_formatter_is_the_last_word(shell):
    """``set_matplotlib_formats`` registers a formatter the configuration never sees."""
    register_inline_backend()
    select_figure_formats(shell, {"svg"}, bbox_inches="tight", pad_inches=0.3)

    assert InlineBackend.instance().figure_formats == {"png"}
    figure_format, keywords = notebook_figure_format()
    assert figure_format == "svg"
    assert keywords["pad_inches"] == 0.3


def test_a_shell_that_cannot_hold_the_configuration_keeps_the_defaults(monkeypatch):
    class Bare:
        """A shell with nothing a configuration can be listed on."""

    monkeypatch.setattr(IPython, "get_ipython", lambda: Bare())
    InlineBackend.clear_instance()
    try:
        assert register_inline_backend() is None
        assert notebook_figure_format() == ("png", {"bbox_inches": "tight"})
    finally:
        InlineBackend.clear_instance()


# --- Which charts are sized so --------------------------------------------------


def test_only_a_frame_in_a_notebook_is_a_notebook_frame(monkeypatch, shell):
    from maidr.util.inline_chart import standalone_document

    assert in_notebook_frame(True)
    assert not in_notebook_frame(False), "save_html is a document of its own"
    with standalone_document():
        assert not in_notebook_frame(True)
    for host in ("is_shiny", "is_flask"):
        with monkeypatch.context() as patch:
            patch.setattr(Environment, host, staticmethod(lambda: True))
            assert not in_notebook_frame(True)
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: False))
    assert not in_notebook_frame(True)


# --- The chart's size in a notebook ------------------------------------------


def test_a_chart_in_a_notebook_has_the_png_images_size(shell):
    """The default: a PNG, cut to what is drawn, a pixel to a dot."""
    fig = _figure(dpi=100)
    width, height = _png_size(print_figure(fig, "png", bbox_inches="tight"))

    svg = _chart_svg(_render(fig))

    assert FRAME_CLASS in svg.get("class").split()
    assert _px(svg.get("width")) == pytest.approx(width, abs=1)
    assert _px(svg.get("height")) == pytest.approx(height, abs=1)
    # The x label of a 4x3 figure lies below the canvas, and is in the box.
    left, top, view_width, view_height = _view(svg)
    assert top + view_height > 216


@pytest.mark.parametrize("dpi", [72, 150])
def test_the_figures_dpi_sizes_it(shell, dpi):
    fig = _figure(dpi=dpi)
    width, height = _png_size(print_figure(fig, "png", bbox_inches="tight"))

    svg = _chart_svg(_render(fig))

    assert _px(svg.get("width")) == pytest.approx(width, abs=1)
    assert _px(svg.get("height")) == pytest.approx(height, abs=1)


def test_retina_is_shown_at_half_its_pixels(shell):
    register_inline_backend()
    _config(shell, "InlineBackend.figure_formats = ['retina']")
    fig = _figure(dpi=100)
    _, shown = retina_figure(fig, bbox_inches="tight")

    svg = _chart_svg(_render(fig))

    assert _px(svg.get("width")) == pytest.approx(shown["width"], abs=1)
    assert _px(svg.get("height")) == pytest.approx(shown["height"], abs=1)


def test_svg_is_shown_in_points(shell):
    register_inline_backend()
    _config(shell, "InlineBackend.figure_formats = ['svg']")
    fig = _figure(dpi=150)
    plain = etree.fromstring(print_figure(fig, "svg", bbox_inches="tight").encode())
    plain_width = float(plain.get("width")[:-2])

    svg = _chart_svg(_render(fig))

    assert _px(svg.get("width")) == pytest.approx(plain_width * 96 / 72, abs=0.5)


@pytest.mark.parametrize("dpi", [100, 150])
def test_an_svg_savefig_bbox_cut_is_sized_by_the_figures_dpi(shell, dpi):
    """``savefig.bbox: tight`` in ``rcParams`` cuts maidr's SVG as it saves it.

    It kept its size in points then, 96 pixels to the inch whatever the
    figure's dpi: at 150, two thirds of the plain figure's image.
    """
    fig = _figure(dpi=dpi)
    with plt.rc_context({"savefig.bbox": "tight"}):
        width, height = _png_size(print_figure(fig, "png", bbox_inches="tight"))
        svg = _chart_svg(_render(fig))

    assert _px(svg.get("width")) == pytest.approx(width, abs=1.5)
    assert _px(svg.get("height")) == pytest.approx(height, abs=1.5)


def test_bbox_inches_none_shows_the_canvas(shell):
    register_inline_backend()
    _config(shell, "InlineBackend.print_figure_kwargs = {'bbox_inches': None}")
    fig = _figure(dpi=100)

    svg = _chart_svg(_render(fig))

    assert _view(svg) == [0, 0, 288, 216]
    assert (_px(svg.get("width")), _px(svg.get("height"))) == (400, 300)


def test_a_box_of_the_kwargs_own(shell):
    config = register_inline_backend()
    config.print_figure_kwargs = {"bbox_inches": Bbox.from_bounds(0.5, 0.5, 2, 1)}
    fig = _figure(dpi=100)

    svg = _chart_svg(_render(fig))

    assert _view(svg) == pytest.approx([36, 108, 144, 72])
    assert (_px(svg.get("width")), _px(svg.get("height"))) == (200, 100)


def test_the_kwargs_dpi_and_pad(shell):
    register_inline_backend()
    _config(
        shell,
        "InlineBackend.print_figure_kwargs = "
        "{'bbox_inches': 'tight', 'pad_inches': 0.5, 'dpi': 50}",
    )
    fig = _figure(dpi=100)
    width, height = _png_size(
        print_figure(fig, "png", bbox_inches="tight", pad_inches=0.5, dpi=50)
    )

    svg = _chart_svg(_render(fig))

    assert _px(svg.get("width")) == pytest.approx(width, abs=1)
    assert _px(svg.get("height")) == pytest.approx(height, abs=1)


@pytest.mark.parametrize("call", ["figsize", "rc", "set_size_inches"])
def test_the_figures_size_in_inches(shell, call):
    with plt.rc_context({"figure.figsize": (9, 3)} if call == "rc" else {}):
        if call == "figsize":
            fig = _figure(size=(9, 3))
        elif call == "rc":
            fig, ax = plt.subplots(dpi=100)
            ax.bar(["Q1", "Q2"], [1, 2])
        else:
            fig = _figure()
            fig.set_size_inches(9, 3)
    width, height = _png_size(print_figure(fig, "png", bbox_inches="tight"))

    svg = _chart_svg(_render(fig))

    assert _px(svg.get("width")) == pytest.approx(width, abs=1)
    assert _px(svg.get("height")) == pytest.approx(height, abs=1)


def test_a_seaborn_figure_level_chart(shell):
    sns = pytest.importorskip("seaborn")
    import pandas as pd

    data = pd.DataFrame({"cat": ["a", "b", "c"], "val": [1.0, 3.0, 2.0]})
    grid = sns.catplot(data=data, x="cat", y="val", kind="bar", height=3, aspect=2)
    fig = grid.figure
    width, height = _png_size(print_figure(fig, "png", bbox_inches="tight"))

    svg = _chart_svg(_render(fig))

    assert _px(svg.get("width")) == pytest.approx(width, abs=1)
    assert _px(svg.get("height")) == pytest.approx(height, abs=1)


# --- Outside a notebook's frame, the canvas in points --------------------------


def test_save_html_keeps_the_canvas_in_points(shell, tmp_path):
    fig = _figure()
    try:
        FigureManager.get_maidr(fig).save_html(str(tmp_path / "chart.html"))
    finally:
        plt.close(fig)
    svg = _chart_svg((tmp_path / "chart.html").read_text(encoding="utf-8"))

    assert (svg.get("width"), svg.get("height"), svg.get("viewBox")) == (
        "288pt",
        "216pt",
        "0 0 288 216",
    )
    assert FRAME_CLASS not in (svg.get("class") or "")


def test_show_outside_a_notebook_keeps_the_canvas_in_points(monkeypatch):
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: False))
    fig = _figure()

    svg = _chart_svg(_render(fig))

    assert (svg.get("width"), svg.get("height"), svg.get("viewBox")) == (
        "288pt",
        "216pt",
        "0 0 288 216",
    )


def test_a_frame_in_a_shiny_app_is_the_plain_figure_with_the_defaults(
    shell, monkeypatch
):
    """Sized as the notebook shows the plain figure, whatever the kernel says.

    A Shiny server has no kernel whose inline backend could say otherwise;
    one that runs in a notebook's still shows its charts in its own page.
    """
    monkeypatch.setattr(Environment, "is_shiny", staticmethod(lambda: True))
    _config(shell, "InlineBackend.figure_formats = ['svg']")
    _config(shell, "InlineBackend.print_figure_kwargs = {'bbox_inches': None}")
    fig = _figure()

    svg = _chart_svg(_render(fig))

    # Cut to what is drawn, at the figure's dpi: the inline backend's
    # defaults, not the whole canvas the kernel asks for.
    assert svg.get("viewBox") != "0 0 288 216"
    assert svg.get("class") and FRAME_CLASS in svg.get("class")
    width = float(svg.get("width").removesuffix("px"))
    view_width = float(svg.get("viewBox").split()[2])
    assert width == pytest.approx(view_width / 72 * 100, abs=0.01)


# --- A layout of the user's own ---------------------------------------------------


def test_a_violin_keeps_the_layout_it_was_given(shell):
    """In a frame that shows what lies past the canvas, nothing is re-laid out."""
    sns = pytest.importorskip("seaborn")
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    data = pd.DataFrame(
        {"cat": np.repeat(["a", "b"], 30), "val": rng.normal(10, 3, 60)}
    )
    fig, ax = plt.subplots()
    sns.violinplot(data=data, x="cat", y="val", ax=ax)
    before = ax.get_position().bounds

    _render(fig)

    assert ax.get_position().bounds == pytest.approx(before)


# --- plotnine shows its own plot, uncut ---------------------------------------------


def test_plotnine_is_sized_at_its_dpi_and_not_cut(shell):
    pytest.importorskip("plotnine")
    import pandas as pd
    from plotnine import aes, geom_col, ggplot, theme

    data = pd.DataFrame({"q": ["Q1", "Q2", "Q3"], "units": [3, 7, 2]})
    plot = (
        ggplot(data, aes("q", "units"))
        + geom_col()
        + theme(figure_size=(4, 3), dpi=150)
    )

    svg = _chart_svg(str(maidr.render(plot)))

    assert _view(svg) == [0, 0, 288, 216]
    assert (_px(svg.get("width")), _px(svg.get("height"))) == (600, 450)


def test_plotnine_in_svg_is_shown_in_points(shell, monkeypatch):
    pytest.importorskip("plotnine")
    import pandas as pd
    from plotnine import aes, geom_col, ggplot, options, theme

    monkeypatch.setattr(options, "figure_format", "svg")
    data = pd.DataFrame({"q": ["Q1", "Q2", "Q3"], "units": [3, 7, 2]})
    plot = (
        ggplot(data, aes("q", "units"))
        + geom_col()
        + theme(figure_size=(4, 3), dpi=150)
    )

    svg = _chart_svg(str(maidr.render(plot)))

    assert (_px(svg.get("width")), _px(svg.get("height"))) == (384, 288)


FRAME_CLASS = "maidr-frame-svg"


def test_the_frame_class_is_the_one_the_frame_looks_for():
    from maidr.util.iframe_utils import FRAME_SVG_CLASS

    assert FRAME_SVG_CLASS == FRAME_CLASS


def test_the_schema_is_unchanged_by_the_size(shell, monkeypatch):
    """Only the root's box and size change: the selectors and points are the same."""
    fig = _figure()
    framed = _chart_svg(_render(fig))
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: False))
    fig = _figure()
    plain = _chart_svg(_render(fig))

    def strip(svg) -> str:
        return UUID.sub("", json.dumps(json.loads(svg.get("maidr"))))

    assert strip(framed) == strip(plain)
    assert len(list(framed.iter())) >= len(list(plain.iter()))
