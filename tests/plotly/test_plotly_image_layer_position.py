"""Two image-drawing traces on one subplot both highlighted the first (#647).

`PlotlyHeatmapPlot._get_selector` returned `.heatmaplayer image`, and
`Svg.selectElement` takes `document.querySelector`, which answers with the
first match. So a subplot holding two images had both layers naming the same
one: a highlight that resolves to a real element and the wrong one. The
reading, the sonification and the braille were all correct either way.

It is reachable two ways. Two `go.Heatmap` traces on one subplot always were;
a `go.Heatmap` beside a `go.Histogram2d` became reachable with #645, which
reads a `histogram2d` as a heatmap and inherited the selector.

## What plotly actually writes

Measured in Chromium, each `g.hm` read back through its own `__data__` so the
pairing is plotly's rather than inferred from where the image landed:

```
Heatmap, Histogram2d           hm[0] heatmap      hm[1] histogram2d
Histogram2d, Heatmap           hm[0] histogram2d  hm[1] heatmap
Heatmap, Histogram2d, Heatmap  hm[0..2] in declaration order
Histogram2d, Histogram2d       hm[0..1] in declaration order
```

So the two types are numbered together, in declaration order -- which is what
`layer_position` answers once `{heatmap, histogram2d}` is declared as a shared
DOM layer beside `{box, candlestick}` and `{contour, histogram2dcontour}`.

## The group carries the position, not the image

The obvious selector does not work. `image:nth-of-type(N)` counts among an
element's *siblings*, and each image is the only one inside its own `g.hm`:

```
g.heatmaplayer image                    2 matches
g.heatmaplayer image:nth-of-type(1)     2   <- both, being each its own first
g.heatmaplayer image:nth-of-type(2)     0
g.heatmaplayer g.hm:nth-of-type(1) image   1
g.heatmaplayer g.hm:nth-of-type(2) image   1
```

Two further types look like they should join the group and do not: a
`contour` under `coloring: "heatmap"` paints inside its own `contourlayer`
and adds no `g.hm`, and a `go.Image` has an `imagelayer` of its own.

Every selector below was resolved in Chromium and its element's `g.hm` read
back through `__data__`: five figures, every one resolving to exactly one
element, and to the trace its layer was built from.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

#: Samples that fall in two bins on each axis, so a `histogram2d` draws a
#: grid rather than a single cell.
SAMPLES = {"x": [1, 2, 2, 3], "y": [1, 2, 2, 3]}

#: A 2x2 grid, and a second one holding different numbers so that a layer
#: read from the wrong trace would be visible in the data as well.
FIRST = [[1.0, 2.0], [3.0, 4.0]]
SECOND = [[9.0, 8.0], [7.0, 6.0]]


def _layers(figure: go.Figure) -> list[dict]:
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell["layers"]]


def _image_selector(position: int, prefix: str = ".subplot.xy") -> str:
    return f"{prefix} .heatmaplayer > g.hm:nth-of-type({position}) image"


class TestEachImageIsNamedByItsOwnGroup:
    def test_two_heatmaps_name_different_images(self) -> None:
        layers = _layers(
            go.Figure([go.Heatmap(z=FIRST), go.Heatmap(z=SECOND)])
        )

        assert [layer["selectors"] for layer in layers] == [
            _image_selector(1),
            _image_selector(2),
        ]

    def test_a_heatmap_counts_the_histogram2d_beside_it(self) -> None:
        """The half #645 made reachable, and the direction that was wrong.

        A `histogram2d` draws into the same `heatmaplayer`, so a heatmap
        declared after one is the *second* image on the subplot.
        """
        layers = _layers(
            go.Figure([go.Histogram2d(**SAMPLES), go.Heatmap(z=FIRST)])
        )

        assert [layer["selectors"] for layer in layers] == [
            _image_selector(1),
            _image_selector(2),
        ]

    def test_a_histogram2d_counts_the_heatmap_beside_it(self) -> None:
        """And the other direction, which is not the same assertion.

        #395 is the reason this is written twice: counting only same-typed
        traces was symmetric-looking and wrong one way round, with a
        candlestick counting the boxes beside it while a box ignored the
        candlestick and claimed the group it had already taken.
        """
        layers = _layers(
            go.Figure([go.Heatmap(z=FIRST), go.Histogram2d(**SAMPLES)])
        )

        assert [layer["selectors"] for layer in layers] == [
            _image_selector(1),
            _image_selector(2),
        ]

    def test_three_images_run_in_declaration_order(self) -> None:
        layers = _layers(
            go.Figure(
                [
                    go.Heatmap(z=FIRST),
                    go.Histogram2d(**SAMPLES),
                    go.Heatmap(z=SECOND),
                ]
            )
        )

        assert [layer["selectors"] for layer in layers] == [
            _image_selector(1),
            _image_selector(2),
            _image_selector(3),
        ]

    def test_one_image_is_still_the_first(self) -> None:
        """The case every heatmap chart is, and the one that must not move."""
        (layer,) = _layers(go.Figure(go.Heatmap(z=FIRST)))

        assert layer["type"] is PlotType.HEAT
        assert layer["selectors"] == _image_selector(1)


class TestWhatDoesNotShareTheLayer:
    def test_a_scatter_does_not_shift_the_image(self) -> None:
        """`g.scatterlayer` is elsewhere, so it takes no `g.hm`."""
        layers = _layers(
            go.Figure([go.Scatter(x=[1, 2], y=[1, 2]), go.Heatmap(z=FIRST)])
        )

        assert layers[1]["selectors"] == _image_selector(1)

    def test_a_heatmap_coloured_contour_does_not_shift_it_either(self) -> None:
        """It looks like it should and it does not.

        `contours.coloring = "heatmap"` fills the whole field, so the trace
        paints a raster the way a heatmap does -- but measured in Chromium it
        paints inside its own `contourlayer` and adds no `g.hm`. Counting it
        would push the heatmap onto a group that does not exist, and the
        highlight would resolve to nothing at all.
        """
        layers = _layers(
            go.Figure(
                [
                    go.Contour(
                        z=[[1, 2, 3], [4, 5, 6], [7, 8, 9]],
                        contours={"coloring": "heatmap"},
                    ),
                    go.Heatmap(z=FIRST),
                ]
            )
        )

        assert layers[-1]["selectors"] == _image_selector(1)


class TestTheLayersStayInTheOrderTheyWereDeclared:
    def test_an_image_does_not_move_ahead_of_what_precedes_it(self) -> None:
        """Reading order is what a reader walks, so it follows the figure.

        Both image types are built inside `_extract_plots`, because only the
        figure-wide pass knows a trace's position among the subplot's images.
        Building them in a block of their own -- which is what the
        `histogram2d` did before this change -- hoists their layers ahead of
        every trace declared before them.
        """
        layers = _layers(
            go.Figure([go.Scatter(x=[1, 2], y=[1, 2]), go.Heatmap(z=FIRST)])
        )

        assert [layer["type"] for layer in layers] == [
            PlotType.SCATTER,
            PlotType.HEAT,
        ]

    def test_a_histogram2d_does_not_either(self) -> None:
        layers = _layers(
            go.Figure([go.Scatter(x=[1, 2], y=[1, 2]), go.Histogram2d(**SAMPLES)])
        )

        assert [layer["type"] for layer in layers] == [
            PlotType.SCATTER,
            PlotType.HEAT,
        ]


class TestEachSubplotCountsItsOwn:
    def test_an_image_on_a_second_subplot_is_its_first(self) -> None:
        """Every subplot holds a `heatmaplayer` of its own, so the position
        is within the subplot rather than within the figure."""
        from plotly.subplots import make_subplots

        figure = make_subplots(rows=1, cols=2)
        figure.add_trace(go.Heatmap(z=FIRST, showscale=False), row=1, col=1)
        figure.add_trace(go.Heatmap(z=SECOND, showscale=False), row=1, col=2)

        grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]

        (left,) = grid[0][0]["layers"]
        (right,) = grid[0][1]["layers"]
        assert left["selectors"] == _image_selector(1)
        assert right["selectors"] == _image_selector(1, ".subplot.x2y2")
