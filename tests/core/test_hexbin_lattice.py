"""A hexbin lattice must be read in rows without losing which bin is which.

``Axes.hexbin`` is a heatmap whose cells are hexagons, and read that way the
navigation, braille and pitch all transfer. Two things about how matplotlib
builds it do not survive a naive reading, and both are invisible until you
look at the numbers.

The first is the **emission order**. ``get_offsets()`` is built lattice by
lattice and, within each, x index by x index, so consecutive offsets walk up a
*column* and the offset rows all come after the aligned ones. Grouping the
points into rows is therefore a permutation, not a reshape -- and the selector
list has to be permuted with them. It would not have looked broken: every bin
would still announce a real centre and a real count, while the highlight sat
on someone else's hexagon. That is the same defect as #316 and #350, in the
trace where it would be hardest to notice, because a hexbin announces centres
rather than indices and so has nothing that would give it away.

The second is that the rows are **ragged**, by construction rather than by
accident: the two lattices hold different numbers of bins, and ``mincnt`` or a
``C`` argument drops the empty ones. Padding them to a rectangle would invent
bins that were never drawn.

So the selector test here resolves the emitted CSS against the real exported
SVG and checks that each match is the hexagon whose centre and count that bin
announces. Nothing weaker distinguishes a correct mapping from an off-by-a-row
one.
"""

from __future__ import annotations

import json
import unittest.mock

import matplotlib
import numpy as np
import pytest
from lxml import etree

matplotlib.use("Agg")

import matplotlib.collections  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them.

    Not housekeeping. A figure left open stays registered with
    ``FigureManager``, and a later test calling ``plt.show()`` renders every
    one of them -- so a layer this file could not read once took down two
    tests in ``test_offline_bundle.py`` that have nothing to do with hexbins.
    """
    yield
    plt.close("all")


def _points() -> tuple[np.ndarray, np.ndarray]:
    """A reproducible cloud dense enough to leave some bins empty."""
    rng = np.random.default_rng(0)
    return rng.normal(size=200), rng.normal(size=200)


@pytest.fixture
def hexbin():
    """Draw a hexbin and yield the figure, its collection and its layer."""
    created = []

    def draw(**kwargs):
        fig, ax = plt.subplots()
        ax.set_xlabel("first")
        ax.set_ylabel("second")
        x, y = _points()
        collection = ax.hexbin(x, y, gridsize=kwargs.pop("gridsize", 3), **kwargs)
        created.append(fig)

        instance = FigureManager.get_maidr(fig)
        html = instance._create_html_tag().get_html_string()
        schema = json.loads(json.dumps(instance._flatten_maidr()))
        layer = schema["subplots"][0][0]["layers"][0]
        return collection, layer, html

    yield draw

    for fig in created:
        plt.close(fig)


def _svg(html: str) -> etree._Element:
    """Parse the exported SVG out of the rendered HTML, namespaces stripped.

    ``cssselect`` translates a selector into namespace-free XPath, and the
    frontend's ``querySelectorAll`` matches on local names as well, so
    stripping is what makes the two agree.
    """
    start = html.index("<svg")
    end = html.index("</svg>", start) + len("</svg>")
    root = etree.fromstring(html[start:end].encode("utf-8"))
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    return root


def _resolve(root: etree._Element, selector: str) -> list:
    """Resolve one CSS selector against the SVG, as the frontend would."""
    from cssselect import GenericTranslator

    return root.xpath(GenericTranslator().css_to_xpath(selector, prefix="//"))


def _flat(layer: dict) -> list[dict]:
    """The layer's bins in the order the frontend flattens them."""
    return [bin for row in layer["data"] for bin in row]


def test_the_lattice_is_read_as_rows_bottom_first(hexbin) -> None:
    """Rows ascend in y, and bins ascend in x within a row.

    Bottom-first because the frontend's UPWARD steps to the *next* row index,
    the same convention a heatmap follows. Getting it inverted would flip the
    chart under the cursor while every announcement stayed true.
    """
    _, layer, _ = hexbin()

    assert layer["type"] == "hexbin"

    rows = layer["data"]
    assert len(rows) > 1

    row_y = [row[0]["y"] for row in rows]
    assert row_y == sorted(row_y)

    for row in rows:
        assert [bin["y"] for bin in row] == [row[0]["y"]] * len(row)
        assert [bin["x"] for bin in row] == sorted(bin["x"] for bin in row)


def test_the_rows_are_ragged_and_stay_that_way(hexbin) -> None:
    """The two lattices hold different numbers of bins.

    Padding to a rectangle would put bins on the chart that were never drawn.
    The frontend clamps a row change to the new row's length precisely because
    grids arrive like this.
    """
    _, layer, _ = hexbin()

    lengths = {len(row) for row in layer["data"]}
    assert len(lengths) > 1


def test_every_drawn_bin_is_announced_including_the_empty_ones(hexbin) -> None:
    """One bin per offset, counts and all.

    With no ``mincnt`` matplotlib draws the empty cells too -- there is a
    hexagon on the chart for each -- so leaving them out would announce a
    lattice with holes in it that a sighted reader does not see. It would also
    put the selector list out of step with the DOM by however many were
    dropped.
    """
    collection, layer, _ = hexbin()

    counts = np.asarray(collection.get_array(), dtype=float)
    assert (counts == 0).any(), "the fixture must leave some bins empty"

    announced = [bin["count"] for bin in _flat(layer)]
    assert sorted(announced) == sorted(counts.tolist())


def test_the_reading_order_is_not_the_emission_order(hexbin) -> None:
    """The guard that keeps the selector test below from being vacuous.

    If matplotlib happened to emit the bins row by row, the regrouping would
    be a no-op and a selector list left in document order would pass. It does
    not: it walks up each column of one lattice and then the other.
    """
    collection, layer, _ = hexbin()

    emitted = np.asarray(collection.get_offsets(), dtype=float)
    reading = [(bin["x"], bin["y"]) for bin in _flat(layer)]

    assert len(reading) == len(emitted)
    assert reading != [(x, y) for x, y in emitted]


def test_each_selector_addresses_the_bin_it_describes(hexbin) -> None:
    """The one that catches an off-by-a-row highlight.

    Resolved against the exported SVG rather than reasoned about: the claim is
    that selector *k* matches the hexagon whose centre and count bin *k*
    announces, and only walking the document can say whether it does.
    """
    collection, layer, html = hexbin()

    root = _svg(html)
    gid = collection.get_gid()
    group = root.xpath(f"//g[@id='{gid}']")
    assert len(group) == 1, "the collection must be tagged before the schema is built"

    drawn = group[0].xpath(".//use")
    offsets = np.asarray(collection.get_offsets(), dtype=float)
    counts = np.asarray(collection.get_array(), dtype=float)
    assert len(drawn) == len(offsets), "one drawn hexagon per bin"

    selectors = layer["selectors"]
    bins = _flat(layer)
    assert len(selectors) == len(bins)

    for selector, bin in zip(selectors, bins):
        matched = _resolve(root, selector)
        assert len(matched) == 1, f"{selector} matched {len(matched)}"

        emitted = drawn.index(matched[0])
        assert offsets[emitted][0] == pytest.approx(bin["x"])
        assert offsets[emitted][1] == pytest.approx(bin["y"])
        assert counts[emitted] == pytest.approx(bin["count"])


def test_mincnt_drops_the_empty_bins_and_the_lattice_still_lines_up(hexbin) -> None:
    """``mincnt`` changes what is drawn, so it changes both lists together.

    matplotlib filters the offsets and the counts through one mask, so the
    correspondence survives -- but the rows get shorter and more uneven, which
    is exactly the case a padded reading would get wrong.
    """
    collection, layer, html = hexbin(mincnt=1)

    offsets = np.asarray(collection.get_offsets(), dtype=float)
    counts = np.asarray(collection.get_array(), dtype=float)
    assert not (counts == 0).any()

    bins = _flat(layer)
    assert len(bins) == len(counts)

    root = _svg(html)
    drawn = root.xpath(f"//g[@id='{collection.get_gid()}']")[0].xpath(".//use")
    assert len(drawn) == len(offsets)

    for selector, bin in zip(layer["selectors"], bins):
        matched = _resolve(root, selector)
        assert len(matched) == 1

        emitted = drawn.index(matched[0])
        assert offsets[emitted][0] == pytest.approx(bin["x"])
        assert offsets[emitted][1] == pytest.approx(bin["y"])
        assert counts[emitted] == pytest.approx(bin["count"])


def test_the_colour_axis_is_named_for_what_the_fill_encodes(hexbin) -> None:
    """"count" is the usual answer and is wrong in two of hexbin's own modes.

    ``C`` replaces the count with a reduction of the given values, and a
    numeric ``bins`` replaces it with *which interval* the count fell in -- a
    three-point bin and a nine-point bin can both read 1. Announcing either as
    a count is the kind of wrong that nothing else in the output contradicts.

    ``bins="log"`` only installs a log norm for the colouring and leaves the
    array as raw counts, so it is not one of them.
    """
    x, _ = _points()

    _, plain, _ = hexbin()
    assert plain["axes"]["z"]["label"] == "count"

    _, logged, _ = hexbin(bins="log")
    assert logged["axes"]["z"]["label"] == "count"

    _, binned, _ = hexbin(bins=5)
    assert binned["axes"]["z"]["label"] == "count bin"

    _, reduced, _ = hexbin(C=x)
    assert reduced["axes"]["z"]["label"] == "value"

    # `bins` wins over `C`, because matplotlib applies it after the reduction
    # and overwrites the result. Measured: `C=` alone leaves float64 spanning
    # 79 to 114, and `C=` with `bins=5` leaves int64 spanning 0 to 4. Reading
    # that as the reduced value announces "value: 2" for a bin whose mean is
    # 113.8 -- a plausible number with nothing in the chart to deny it.
    #
    # It is not "count bin" either. Nothing was counted, so which quantity
    # got discretised is still worth saying.
    _, both, _ = hexbin(C=x, bins=5)
    assert both["axes"]["z"]["label"] == "value bin"

    # `bins="log"` is the exception on both paths: it installs a norm and
    # leaves the array alone, reduced values included.
    _, logged_reduction, _ = hexbin(C=x, bins="log")
    assert logged_reduction["axes"]["z"]["label"] == "value"

    _, named, _ = hexbin(z_label="density")
    assert named["axes"]["z"]["label"] == "density"


@pytest.mark.parametrize(
    "scales",
    [{"xscale": "log"}, {"yscale": "log"}, {"xscale": "log", "yscale": "log"}],
)
def test_a_log_scaled_lattice_is_declined_rather_than_mistranslated(scales) -> None:
    """``hexbin``'s own log scales are not read, and that is the honest answer.

    It bins in the transformed space, and on matplotlib 3.10 the offsets come
    back in that space as well: for data spanning 0.3 to 11.2 they run -0.52
    to 1.05. Announced as centres, a bin at x = 3.4 reads as ``0.53``. The
    structure is right, the counts are right, the coordinates are wrong, and
    nothing in the chart contradicts them -- which is worse than saying
    nothing.

    Un-transforming them would be an assumption about matplotlib's internals
    that the neighbouring release already breaks: on 3.9 the same call returns
    one path per hexagon and a single placeholder offset, so the centres are
    not in ``get_offsets()`` at all.

    So the layer is not registered and the figure keeps the static image it
    had before this patch existed. What is asserted here is that it degrades
    rather than crashes -- an `ExtractionError` from a layer takes the whole
    render down with it, including every other chart on the figure.
    """
    rng = np.random.default_rng(0)
    positive = np.abs(rng.normal(5, 2, 300)) + 0.1

    fig, ax = plt.subplots()
    ax.hexbin(positive, positive.copy(), gridsize=3, **scales)

    with pytest.raises(KeyError):
        FigureManager.get_maidr(fig)


def test_an_already_log_axis_is_still_read(hexbin) -> None:
    """The distinction the check turns on, asserted rather than only argued.

    Declining is keyed on ``hexbin``'s *own* ``xscale``/``yscale``, not on the
    axis. An axes that was already log-scaled makes matplotlib bin linearly,
    so those offsets are honest data coordinates and the chart reads.
    """
    fig, ax = plt.subplots()
    ax.set_xscale("log")
    rng = np.random.default_rng(0)
    positive = np.abs(rng.normal(5, 2, 300)) + 0.1
    collection = ax.hexbin(positive, positive.copy(), gridsize=3)

    layer = json.loads(json.dumps(FigureManager.get_maidr(fig)._flatten_maidr()))
    layer = layer["subplots"][0][0]["layers"][0]

    offsets = np.asarray(collection.get_offsets(), dtype=float)
    assert len(_flat(layer)) == len(offsets)
    assert min(bin["x"] for bin in _flat(layer)) == pytest.approx(offsets[:, 0].min())
    # Data coordinates, not log10 of them.
    assert max(bin["x"] for bin in _flat(layer)) > 1.0


def test_a_lattice_whose_counts_do_not_match_is_declined(hexbin) -> None:
    """The second way a lattice cannot be read, driven directly.

    ``mincnt`` filters the offsets and the counts through one mask, so they
    agree on every release this reads -- and matplotlib 3.9 shows that is a
    property of the representation rather than a law: under a log scale it
    returns eleven counts against a single offset. The whole scheme indexes
    one list by the other, so a mismatch has to end in no layer rather than
    in a bin wearing a stranger's count.
    """
    fig, ax = plt.subplots()
    rng = np.random.default_rng(0)

    with unittest.mock.patch.object(
        matplotlib.collections.Collection,
        "get_offsets",
        lambda self: np.zeros((1, 2)),
    ):
        ax.hexbin(rng.normal(size=200), rng.normal(size=200), gridsize=3)

    with pytest.raises(KeyError):
        FigureManager.get_maidr(fig)


def test_a_bin_with_no_value_is_emitted_without_one(hexbin) -> None:
    """A masked bin must not be announced with the number underneath the mask.

    ``get_array()`` hands back a masked array. No matplotlib release masks a
    hexbin cell today -- the empty ones are dropped before ``set_array`` --
    so this drives the case directly rather than through a chart. It is
    written because ``np.asarray`` on a masked array returns the data *under*
    the mask, which would announce a fabricated count with nothing in the
    output to contradict it.

    The bin is still emitted. The hexagon is drawn, and the frontend matches
    the selector list against the DOM by length, so dropping one bin would
    withdraw highlighting from the entire lattice.
    """
    collection, _, _ = hexbin()

    counts = np.asarray(collection.get_array(), dtype=float)
    collection.set_array(np.ma.array(counts, mask=[i == 1 for i in range(len(counts))]))

    plot = FigureManager.get_maidr(collection.axes.get_figure())._plots[0]
    rows = plot._extract_plot_data()
    bins = [bin for row in rows for bin in row]

    assert len(bins) == len(counts)
    assert sum(bin["count"] is None for bin in bins) == 1

    masked = next(bin for bin in bins if bin["count"] is None)
    assert masked["x"] == pytest.approx(float(collection.get_offsets()[1][0]))
    assert masked["y"] == pytest.approx(float(collection.get_offsets()[1][1]))

    # `None`, not `nan`: JSON has no NaN literal, and `json.dumps` would emit
    # a bare `NaN` that the browser's own parser rejects.
    assert "NaN" not in json.dumps(rows)


def test_marginals_do_not_pull_in_the_marginal_collections(hexbin) -> None:
    """``marginals=True`` draws two more PolyCollections on the same axes.

    They are not part of the lattice, and the layer is handed the call's own
    return value rather than searching the axes for a PolyCollection -- which
    would find three, and on an axes carrying a violin or a ``fill_between``
    band would find one that is not a hexbin at all.
    """
    collection, layer, _ = hexbin(marginals=True)

    assert len(_flat(layer)) == len(np.asarray(collection.get_offsets()))
