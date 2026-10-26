"""A heatmap drawn as an image names its image, placed as maidr.js reads it.

``ax.imshow`` draws a heatmap as one ``<image>``, and the layer was emitted
with no selectors at all: every cell was announced and none was outlined
(py-example-a#7). maidr.js outlines a cell of a single ``<image>`` by laying a
rectangle over it, worked out from the image's ``x``, ``y``, ``width`` and
``height``, the first row of ``data.points`` along the top. matplotlib places
the image with its ``transform`` -- the default image drawn upside down and
flipped into place, an ``interpolation="none"`` one scaled up from its own
pixels -- so those attributes do not give its box; ``HeatPlot.finish_svg``
restates them so they do, drawing the same picture in the same place.

A grid whose cells the overlay would not land on -- ``origin="lower"``, an
inverted axis, a view cut short of the image, an image written in a form
``finish_svg`` does not know -- keeps no highlight, as before.
The outline itself is measured in a browser by
``tests/browser/test_image_heatmap_highlight.py``.
"""

from __future__ import annotations

import io
import re

import numpy as np
import pytest

pytest.importorskip("lxml")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from lxml import etree  # noqa: E402
from lxml.cssselect import CSSSelector  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

GRID = np.arange(12.0).reshape(3, 4)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _tree(svg: str):
    parser = etree.XMLParser(recover=True, huge_tree=True)
    root = etree.fromstring(svg.encode(), parser)
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    return root


def _render(draw):
    """Draw, render, and return the figure, axes, heat layer, rendered SVG
    and the SVG matplotlib writes for the same figure without maidr."""
    figure, ax = plt.subplots()
    image = draw(ax)
    html = maidr.render(figure)._repr_html_()
    (layer,) = [plot.schema for plot in FigureManager.get_maidr(figure)._plots]
    plain = io.StringIO()
    figure.savefig(plain, format="svg")
    rendered = _tree(re.search(r"<svg.*?</svg>", html, re.S).group(0))
    return figure, ax, image, layer, rendered, _tree(plain.getvalue())


def _affine(transform: str) -> np.ndarray:
    """The matrix of an SVG transform list of ``scale``, ``translate`` and
    ``matrix``, applied right to left as SVG applies a list."""
    matrix = np.eye(3)
    for name, arguments in re.findall(r"(\w+)\(([^)]*)\)", transform):
        v = [float(a) for a in re.split(r"[\s,]+", arguments.strip()) if a]
        if name == "scale":
            step = np.diag([v[0], v[1] if len(v) > 1 else v[0], 1.0])
        elif name == "translate":
            dy = v[1] if len(v) > 1 else 0.0
            step = np.array([[1, 0, v[0]], [0, 1, dy], [0, 0, 1]])
        else:
            a, b, c, d, e, f = v
            step = np.array([[a, c, e], [b, d, f], [0, 0, 1]])
        matrix = matrix @ step
    return matrix


def _picture_corners(image) -> np.ndarray:
    """Where the picture's top-left and bottom-right corners are drawn."""
    x, y = float(image.get("x", 0)), float(image.get("y", 0))
    width, height = float(image.get("width")), float(image.get("height"))
    corners = np.array([[x, y, 1.0], [x + width, y + height, 1.0]]).T
    return (_affine(image.get("transform", "")) @ corners)[:2].T


def _image(root, gid: str):
    (image,) = root.xpath("//image[@id=$gid]", gid=gid)
    return image


DRAWN = {
    "imshow": lambda ax: ax.imshow(GRID),
    "imshow interpolation none": lambda ax: ax.imshow(GRID, interpolation="none"),
    "imshow extent": lambda ax: ax.imshow(GRID, extent=(0, 8, 0, 3)),
    "imshow aspect auto": lambda ax: ax.imshow(GRID, aspect="auto"),
    "matshow": lambda ax: ax.matshow(GRID),
    "imshow zoomed out": lambda ax: (ax.imshow(GRID), ax.set_xlim(-2, 6))[0],
}


@pytest.mark.parametrize("chart", list(DRAWN))
def test_the_selector_names_the_image(chart):
    _, _, image, layer, rendered, _ = _render(DRAWN[chart])

    found = CSSSelector(layer["selectors"])(rendered)
    assert [element.tag for element in found] == ["image"]
    assert found[0].get("id") == image.get_gid()


@pytest.mark.parametrize("chart", list(DRAWN))
def test_the_picture_is_drawn_where_matplotlib_drew_it(chart):
    _, _, image, _, rendered, plain = _render(DRAWN[chart])

    assert np.allclose(
        _picture_corners(_image(rendered, image.get_gid())),
        _picture_corners(_image(plain, image.get_gid())),
        atol=1e-3,
    )


@pytest.mark.parametrize("chart", list(DRAWN))
def test_the_images_attributes_are_its_box_on_the_page(chart):
    # What maidr.js lays the cells out from.
    figure, ax, image, _, rendered, _ = _render(DRAWN[chart])
    drawn = _image(rendered, image.get_gid())

    corners = _picture_corners(drawn)
    x, y = float(drawn.get("x")), float(drawn.get("y"))
    width, height = float(drawn.get("width")), float(drawn.get("height"))
    assert np.allclose(corners.min(axis=0), [x, y], atol=1e-3)
    assert np.allclose(corners.max(axis=0), [x + width, y + height], atol=1e-3)

    # And the box is the grid's: its extent, in the SVG's points, to within
    # the pixel matplotlib rounds a resampled picture up to.
    left, right, bottom, top = image.get_extent()
    extent = ax.transData.transform([(left, top), (right, bottom)]) * 72 / figure.dpi
    extent[:, 1] = figure.get_figheight() * 72 - extent[:, 1]
    assert np.allclose([x, y], extent.min(axis=0), atol=1.0)
    assert np.allclose([x + width, y + height], extent.max(axis=0), atol=1.0)


NOT_OUTLINED = {
    "origin lower": lambda ax: ax.imshow(GRID, origin="lower"),
    "inverted y": lambda ax: (ax.imshow(GRID), ax.invert_yaxis())[0],
    "inverted x": lambda ax: (ax.imshow(GRID), ax.invert_xaxis())[0],
    "zoomed in": lambda ax: (ax.imshow(GRID), ax.set_xlim(0, 2))[0],
}


@pytest.mark.parametrize("chart", list(NOT_OUTLINED))
def test_a_grid_the_overlay_would_misplace_keeps_no_highlight(chart):
    # The overlay puts data.points[0] along the top of the picture and its
    # first column at the left; these draw the grid another way round, or
    # only part of it.
    _, _, image, layer, _, _ = _render(NOT_OUTLINED[chart])

    assert "selectors" not in layer
    # Not named, so not restated: the image is written as matplotlib wrote it.
    assert image.get_gid() is None


@pytest.mark.parametrize(
    "transform",
    ["rotate(90)", "matrix(0 1 -1 0 5 6)", "scale(2 -1) translate(0 -20)"],
)
def test_an_image_in_another_form_loses_its_id_not_its_place(transform):
    # matplotlib writes an image in one of two forms. In any other, the
    # attributes maidr.js reads would not be the image's box, and the outline
    # would land on cells the image does not draw there; the image stays
    # where it is but goes unnamed, so its cells are announced without one.
    figure, _, image, _, _, _ = _render(lambda ax: ax.imshow(GRID))
    (plot,) = FigureManager.get_maidr(figure)._plots
    tree = etree.fromstring(
        '<svg xmlns="http://www.w3.org/2000/svg"><g><image/></g></svg>'
    )
    (drawn,) = tree.xpath("//*[local-name()='image']")
    written = {"x": "1", "y": "2", "width": "30", "height": "20"}
    for name, value in {**written, "transform": transform}.items():
        drawn.set(name, value)
    drawn.set("id", image.get_gid())

    plot.finish_svg(tree)

    assert dict(drawn.attrib) == {**written, "transform": transform}
