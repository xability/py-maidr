"""A chart in a Quarto page has the size and shape of the same figure drawn plain.

Quarto shows a plain matplotlib figure through the kernel's display
formatter: IPython's ``print_figure``, or ``retina_figure``, with
``InlineBackend.print_figure_kwargs``. That cuts the figure to what is drawn
(``bbox_inches="tight"``, padded by ``savefig.pad_inches``), growing past the
canvas where a label lies outside it, and shows a raster at the figure's dpi
in CSS pixels to the inch. :func:`size_like_plain_figure` gives the chart's
SVG the same box and size through its root ``viewBox``, ``width`` and
``height`` alone, so nothing a selector or a highlight names moves.

The expected sizes here are what IPython's own formatter makes of the same
figure, not numbers worked out by hand. Whether the page then shows the two
alike is ``tests/browser/test_quarto_render_inline.py``. Each holds with
text hinted, as matplotlib's default has it, and not.
"""

from __future__ import annotations

import copy
import io
import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from lxml import etree  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

from maidr.util import inline_chart  # noqa: E402
from maidr.util.inline_chart import size_like_plain_figure  # noqa: E402

IPython = pytest.importorskip("IPython")
PIL = pytest.importorskip("PIL.Image")

from IPython.core.formatters import DisplayFormatter  # noqa: E402
from IPython.core.pylabtools import (  # noqa: E402
    print_figure,
    retina_figure,
    select_figure_formats,
)

SVG = "{http://www.w3.org/2000/svg}"


class _Shell:
    """A kernel's shell as far as the figure formatter goes, with real formatters."""

    def __init__(self) -> None:
        self.display_formatter = DisplayFormatter()
        self.user_ns: dict = {}

    def push(self, variables: dict, interactive: bool = True) -> None:
        self.user_ns.update(variables)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture(autouse=True, params=["force_autohint", "no_hinting"])
def _hinting(request):
    """Hinted text, matplotlib's default, measures otherwise at another dpi."""
    with plt.rc_context({"text.hinting": request.param}):
        yield


@pytest.fixture
def kernel(monkeypatch):
    """Set the kernel's figure format up as Quarto's setup cell does.

    ``set_matplotlib_formats(fig_format)`` with the inline backend's
    ``print_figure_kwargs``, ``{"bbox_inches": "tight"}`` unless configured.
    """
    shell = _Shell()
    monkeypatch.setattr(IPython, "get_ipython", lambda: shell)

    def set_up(figure_format: str, **kwargs):
        keywords = {"bbox_inches": "tight", **kwargs}
        select_figure_formats(shell, {figure_format}, **keywords)
        return shell

    return set_up


def _figure(size=(4, 3), dpi=96, **kwargs):
    fig, ax = plt.subplots(figsize=size, dpi=dpi, **kwargs)
    ax.bar(["Q1", "Q2", "Q3"], [3, 7, 2])
    ax.set_xlabel("Quarter")
    ax.set_ylabel("Units")
    ax.xaxis.label.set_gid("x-label")
    return fig, ax


def _svg(fig):
    """The figure's SVG as maidr saves it: the whole canvas, in points."""
    buffer = io.StringIO()
    fig.savefig(buffer, format="svg")
    return etree.fromstring(buffer.getvalue().encode())


def _px(value: str) -> float:
    assert value.endswith("px"), value
    return float(value[:-2])


def _view(svg) -> list[float]:
    return [float(v) for v in svg.get("viewBox").split()]


def _png_size(data) -> tuple[int, int]:
    return PIL.open(io.BytesIO(data)).size


def _sized(fig):
    svg = _svg(fig)
    size_like_plain_figure(fig, svg)
    return svg


# --- The size the page shows a plain figure at -------------------------------


@pytest.mark.parametrize("dpi", [72, 96, 150])
def test_retina_is_shown_at_the_figures_dpi(kernel, dpi):
    kernel("retina")
    fig, _ = _figure(dpi=dpi)
    _, shown = retina_figure(fig)

    svg = _sized(fig)

    assert _px(svg.get("width")) == pytest.approx(shown["width"], abs=1)
    assert _px(svg.get("height")) == pytest.approx(shown["height"], abs=1)


@pytest.mark.parametrize("figure_format", ["png", "jpeg"])
@pytest.mark.parametrize("dpi", [72, 150])
def test_png_and_jpeg_are_shown_a_dot_to_a_pixel(kernel, figure_format, dpi):
    kernel(figure_format)
    fig, _ = _figure(dpi=dpi)
    width, height = _png_size(print_figure(fig, "png"))

    svg = _sized(fig)

    assert _px(svg.get("width")) == pytest.approx(width, abs=1)
    assert _px(svg.get("height")) == pytest.approx(height, abs=1)


@pytest.mark.parametrize("dpi", [72, 150])
def test_svg_is_shown_in_points_whatever_the_dpi(kernel, dpi):
    """An SVG figure is 72 points, 96 CSS pixels, to the inch; fig-dpi is moot."""
    kernel("svg")
    fig, _ = _figure(dpi=dpi)
    plain = etree.fromstring(print_figure(fig, "svg").encode())
    plain_w, plain_h = (float(plain.get(a)[:-2]) for a in ("width", "height"))

    svg = _sized(fig)

    assert _px(svg.get("width")) == pytest.approx(plain_w * 96 / 72, abs=0.5)
    assert _px(svg.get("height")) == pytest.approx(plain_h * 96 / 72, abs=0.5)
    # The same box as the plain figure's, in the same points.
    assert _view(svg)[2:] == pytest.approx(_view(plain)[2:], abs=0.1)


def test_the_dpi_the_formatter_was_given_wins(kernel):
    """``print_figure_kwargs`` passed to ``print_figure`` beat the figure's dpi."""
    kernel("png", dpi=50)
    fig, _ = _figure(dpi=96)
    width, height = _png_size(print_figure(fig, "png", dpi=50))

    svg = _sized(fig)

    assert _px(svg.get("width")) == pytest.approx(width, abs=1)


def test_a_formatter_that_does_not_cut_the_figure_shows_the_canvas(kernel):
    kernel("png", bbox_inches=None)
    fig, _ = _figure(dpi=96)
    width, height = _png_size(print_figure(fig, "png", bbox_inches=None))

    svg = _sized(fig)

    assert _view(svg) == [0, 0, 288, 216]
    assert (_px(svg.get("width")), _px(svg.get("height"))) == (width, height)
    assert svg[0].tag != f"{SVG}path", "nothing outside the canvas to paint"


def test_a_formatter_with_a_box_of_its_own_shows_that_box(kernel):
    kernel("png", bbox_inches=Bbox.from_bounds(0.5, 0.5, 2, 1))
    fig, _ = _figure(dpi=100)

    svg = _sized(fig)

    # 0.5 in from the left, and 3 - 1.5 in from the top.
    assert _view(svg) == pytest.approx([36, 108, 144, 72])
    assert (_px(svg.get("width")), _px(svg.get("height"))) == (200, 100)


def test_pad_inches_from_the_formatter_or_the_rc(kernel):
    fig, _ = _figure()
    kernel("svg")
    default = _view(_sized(fig))
    kernel("svg", pad_inches=0.5)
    wider = _view(_sized(fig))

    assert matplotlib.rcParams["savefig.pad_inches"] == 0.1
    assert wider[2] - default[2] == pytest.approx((0.5 - 0.1) * 2 * 72, abs=0.01)


def test_without_a_shell_the_format_quarto_names_is_used(monkeypatch, tmp_path):
    """The QUARTO_EXECUTE_INFO file says the format when no formatter does."""
    monkeypatch.setattr(IPython, "get_ipython", lambda: None)
    info = tmp_path / "info.json"
    fig, _ = _figure(dpi=150)
    sizes = {}
    for figure_format in ("png", "svg"):
        info.write_text(
            json.dumps(
                {
                    "format": {
                        "pandoc": {"to": "html"},
                        "execute": {"fig-format": figure_format},
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("QUARTO_EXECUTE_INFO", str(info))
        svg = _sized(fig)
        sizes[figure_format] = _px(svg.get("width")) / (_view(svg)[2] / 72)

    assert sizes == pytest.approx({"png": 150, "svg": 96}, abs=0.01)


# --- What lies outside the canvas --------------------------------------------


def _label_y(svg, gid: str) -> float:
    """Where a label written as text (``svg.fonttype: none``) sits, in points."""
    group = next(g for g in svg.iter(f"{SVG}g") if g.get("id") == gid)
    return float(next(group.iter(f"{SVG}text")).get("y"))


@pytest.mark.parametrize("size", [(4, 3), (3, 3)])
def test_an_x_label_below_the_canvas_is_in_the_box(kernel, size):
    """A small figure's x label falls below its canvas; the box grows to it."""
    kernel("retina")
    with plt.rc_context({"svg.fonttype": "none"}):
        fig, _ = _figure(size=size)
        svg = _sized(fig)
    canvas_height = size[1] * 72
    left, top, width, height = _view(svg)

    y = _label_y(svg, "x-label")

    assert "Quarter" in etree.tostring(svg, encoding="unicode")
    assert y > canvas_height, "the label was expected below the canvas"
    assert top + height > y


def test_a_legend_beside_the_axes_is_in_the_box(kernel):
    kernel("retina")
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([1, 2, 3], [2, 3, 1], label="2024 sales")
    legend = ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1))
    legend.set_gid("legend")
    fig.canvas.draw()
    extent = legend.get_window_extent().get_points()
    right = fig.transFigure.inverted().transform(extent)[1][0] * 6 * 72

    svg = _sized(fig)
    left, _, width, _ = _view(svg)

    assert right > 6 * 72, "the legend was expected past the canvas's edge"
    assert left + width >= right


# --- The colour of what the box adds -----------------------------------------


def _backdrop(svg):
    """The path painting the box past the canvas, or None."""
    first = svg[0]
    if first.tag == f"{SVG}path" and "evenodd" in first.get("style", ""):
        return first
    return None


def test_the_area_past_the_canvas_is_painted_in_the_figures_colour(kernel):
    kernel("retina")
    fig, _ = _figure(facecolor="#336699")

    svg = _sized(fig)
    backdrop = _backdrop(svg)

    assert backdrop is not None
    assert "fill: #336699" in backdrop.get("style")
    assert "fill-opacity" not in backdrop.get("style")
    # The box, less the part of the canvas inside it, so nothing is painted twice.
    left, top, width, height = _view(svg)
    subpaths = [s.split() for s in backdrop.get("d").split("Z") if s.strip()]
    assert len(subpaths) == 2
    outer = [float(subpaths[0][i]) for i in (1, 2, 4, 6)]
    assert outer == pytest.approx([left, top, left + width, top + height], abs=0.001)
    inner = [float(subpaths[1][i]) for i in (1, 2, 4, 6)]
    assert inner == pytest.approx(
        [max(left, 0), max(top, 0), min(left + width, 288), min(top + height, 216)],
        abs=0.001,
    )


def test_a_translucent_face_keeps_its_alpha(kernel):
    kernel("retina")
    fig, _ = _figure(facecolor=(1, 0, 0, 0.5))

    style = _backdrop(_sized(fig)).get("style")

    assert "fill: #ff0000" in style
    assert "fill-opacity: 0.5" in style


@pytest.mark.parametrize(
    "rc", [{"savefig.transparent": True}, {"figure.facecolor": "none"}]
)
def test_a_transparent_figure_is_not_painted(kernel, rc):
    kernel("retina")
    with plt.rc_context(rc):
        fig, _ = _figure()
        svg = _sized(fig)

    assert _backdrop(svg) is None


def test_a_hidden_figure_patch_is_not_painted(kernel):
    """``fig.patch.set_visible(False)`` leaves the plain figure's whole box bare.

    The SVG leaves its canvas unpainted too, so on a dark page a band painted
    in the (hidden) face colour would show below the canvas alone.
    """
    kernel("png")
    fig, _ = _figure()
    fig.patch.set_visible(False)

    svg = _sized(fig)
    plain = PIL.open(io.BytesIO(print_figure(fig, "png", bbox_inches="tight")))
    corner = plain.convert("RGBA").getpixel((0, plain.height - 1))

    _left, top, _width, height = _view(svg)
    assert top + height > 216, "the box must grow past the canvas to test this"
    assert corner[3] == 0
    assert _backdrop(svg) is None


def test_savefig_facecolor_is_the_colour_the_canvas_was_painted(kernel):
    kernel("retina")
    with plt.rc_context({"savefig.facecolor": "#eeeeee"}):
        fig, _ = _figure()
        svg = _sized(fig)

    assert "fill: #eeeeee" in _backdrop(svg).get("style")


def test_a_box_within_the_canvas_paints_nothing(kernel):
    """Nothing past a large figure's canvas: the tight box only cuts."""
    kernel("retina")
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot([1, 2, 3], [2, 3, 1])

    svg = _sized(fig)
    left, top, width, height = _view(svg)

    assert left > 0 and top > 0 and left + width < 576 and top + height < 432
    assert _backdrop(svg) is None


# --- What is left alone ------------------------------------------------------


def test_only_the_root_changes(kernel):
    """Every element keeps its user-space coordinates; the root gains a backdrop."""
    kernel("retina")
    fig, _ = _figure()
    before = _svg(fig)
    after = copy.deepcopy(before)
    size_like_plain_figure(fig, after)

    assert [e.attrib for e in before.iterdescendants()] == [
        e.attrib for e in after.iterdescendants() if e is not after[0]
    ]
    assert after[0].tag == f"{SVG}path"


def test_an_svg_the_save_already_cut_is_left_as_it_is(kernel):
    """``savefig.bbox: tight`` cuts maidr's own SVG, whose points are not the figure's."""
    kernel("retina")
    fig, _ = _figure()
    with plt.rc_context({"savefig.bbox": "tight"}):
        svg = _svg(fig)
        before = etree.tostring(svg)
        size_like_plain_figure(fig, svg)

    assert etree.tostring(svg) == before


def test_a_box_that_cannot_be_measured_leaves_the_svg_as_it_is(kernel, monkeypatch):
    kernel("retina")
    fig, _ = _figure()
    svg = _svg(fig)
    before = etree.tostring(svg)
    monkeypatch.setattr(
        type(fig), "get_tightbbox", lambda *a, **k: (_ for _ in ()).throw(ValueError)
    )

    size_like_plain_figure(fig, svg)

    assert etree.tostring(svg) == before


def test_numbers_are_short_and_never_negative_zero():
    assert inline_chart._number(-0.0001) == "0"
    assert inline_chart._number(12.5) == "12.5"
    assert inline_chart._number(356.20912) == "356.209"
    assert inline_chart._number(-0.757) == "-0.757"
