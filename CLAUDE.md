# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

py-maidr (`maidr`) is a Python library that makes matplotlib/seaborn visualizations accessible to blind and low-vision users. It monkey-patches plotting functions at import time via `wrapt`, so users just `import maidr` and their existing code automatically generates interactive HTML with sonification, braille, and tactile support. It is the Python binding for the maidr JavaScript library.

## Commands

| Task | Command |
|------|---------|
| Install (all extras + dev) | `uv sync --locked --all-extras --dev` |
| Run all tests | `uv run pytest -vvv` |
| Run single test file | `uv run pytest tests/core/test_figure_manager.py -vvv` |
| Run single test by name | `uv run pytest tests/core/test_figure_manager.py::test_get_axes_from_none -vvv` |
| Lint (check) | `ruff check --diff` |
| Lint (auto-fix) | `ruff check --fix` |
| Check lockfile | `uv lock --check` |

## Architecture

### Core Mechanism: Monkey-Patching

The `maidr/patch/` modules use `wrapt` to intercept matplotlib/seaborn plot calls (e.g., `Axes.bar`, `seaborn.barplot`) at import time. Each patch:
1. Calls the original function
2. Extracts axes/figure from the result
3. Registers the plot with `FigureManager`

`ContextManager` (using `contextvars.ContextVar`) prevents infinite recursion when patched functions call other patched functions internally.

### Key Components

- **`maidr/api.py`** — Public API: `render()`, `show()`, `save_html()`, `stacked()`, `close()`
- **`maidr/core/figure_manager.py`** — Thread-safe singleton mapping matplotlib `Figure` objects to `Maidr` instances
- **`maidr/core/maidr.py`** — `Maidr` class: holds a Figure + list of `MaidrPlot` objects, handles SVG extraction (via `lxml`), MAIDR JSON schema generation, and HTML rendering
- **`maidr/core/plot/`** — Factory pattern: `MaidrPlotFactory` dispatches to concrete `MaidrPlot` subclasses (BarPlot, BoxPlot, HeatPlot, etc.) based on `PlotType` enum. Each subclass implements `_extract_plot_data()`
- **`maidr/patch/`** — One module per plot type (barplot.py, boxplot.py, etc.) plus `highlight.py` (injects maidr attributes into SVG elements) and `clear.py` (cleanup on `plt.clf`/`plt.cla`)
- **`maidr/util/mixin/`** — Reusable extraction logic: `ContainerExtractorMixin`, `LevelExtractorMixin`, `LineExtractorMixin`, `CollectionExtractorMixin`, `FormatExtractorMixin`
- **`maidr/widget/shiny.py`** — Shiny framework integration (`output_maidr`, `@render_maidr`)
- **`maidr/widget/streamlit.py`** — Streamlit integration (`render_maidr`, `maidr_html`)

### Supported Plot Types

Defined in `maidr/core/enum/plot_type.py`, which has **41** members. They do
not all carry the same promise -- see `docs/stability.qmd`, and keep that page
in step when adding one (`tests/core/test_plot_type_stability.py` enforces it).

**Stable** (15) -- predate the plot coverage roadmap (#345) and have been
exercised by real readers:

BAR, BOX, CANDLESTICK, COUNT, DODGED, HEAT, HIST, LINE, PIE, SCATTER,
SMOOTH, STACKED, STEP, VIOLIN_BOX, VIOLIN_KDE

**Experimental** (26) -- added by that roadmap or after it, none validated
with a reader, and subject to change without a deprecation period:

ALLUVIAL, AREA, BOXEN, CHOROPLETH, CONTOUR, ERRORBAR, FUNNEL, GANTT, GAUGE,
HEXBIN, ICICLE, LOLLIPOP, NORMALIZED, NORMALIZED_AREA, PARALLEL, POLAR_AREA,
RADAR, RIDGELINE, ROC, RUG, SANKEY, STACKED_AREA, SUNBURST, TREEMAP, WATERFALL,
WORD_CLOUD

Docs convention: wherever user docs name a plot type as a heading, nav/sidebar
label, list item or table row (outside the `docs/stability.qmd` tables), an
experimental type gets the suffix ` [experimental]` right after its name and a
stable type gets nothing. A gallery heading keeps its old anchor with an
explicit `{#id}`; `tests/docs/test_experimental_marks.py` checks the headings.

Order follows the split too: stable first, then experimental. A list of plot
types (the per-library lists in `docs/index.qmd`, the family list in
`docs/examples.qmd`, `docs/llms.txt`) is split into a Stable part and then an
Experimental part, each under its own sub-heading (a bold lead-in in
`llms.txt`), with a link to `stability.qmd` under Experimental; an item
mixing both tiers stays in Stable. In `docs/_quarto.yml` the pages about
experimental types only come after the stable ones, in their own group. On a
gallery page the experimental `##` sections come after every stable one.
`tests/docs/test_stable_before_experimental.py` checks the ordering.

Note that `maidr/plotly/` builds its MAIDR schema in Python and therefore needs its own
handling per plot type, whereas `maidr/altair/` delegates entirely to the upstream
Vega-Lite JS adapter -- an Altair-only plot type is implemented there, not here.
`maidr/bokeh/` (experimental, `docs/stability.qmd#bokeh-support`) also builds its
schema in Python, from the Bokeh document model (`layers.py` maps glyphs to layer
types, `layout.py` places plots on the subplot grid). Bokeh draws to a canvas, so
its highlight is an `onNavigate` callback handed to `maidr.js` through
`window.maidrLive.setData` rather than CSS selectors; see `bokeh_maidr.py`. The
`maidr.js` loader both it and Plotly use lives in `maidr/util/bundle_loader.py`.
`maidr/plotnine/` (experimental, `docs/stability.qmd#plotnine-support`) reads a
`ggplot` handed to `maidr.show`/`render`/`save_html` from plotnine's own layer
data rather than from the artists: `layers.py` draws a copy with each geom's
`draw_group` recorded, so every row is paired with the artist that drew it, and
maps geoms to layer types; `plotnine_maidr.py` renders the drawn figure through a
`Maidr` subclass whose subplot grid is the facet layout. Its selectors name each
element by the gid it is given (`g[id='maidr-...']`). `import maidr` alone reads
only a plotnine chart's points, through the `Axes.scatter` patch.
`maidr/excel/` (experimental, `docs/stability.qmd#excel-support`) reads the
charts of an `.xlsx` file for `maidr.read_excel_charts`: `package.py` walks the
zip from sheet to drawing to chart part and streams the few cells it needs,
`chartxml.py` reads a DrawingML chart part from the values Excel cached in it
and `chartex.py` an Excel 2016 one (histogram to map), both into the
`ChartSpec` of `spec.py`. They share `cells.py` (range formulas), `formats.py`
(numbers, dates and number formats) and `colors.py`. The `draw/` package
redraws them: `draw_chart` picks a module per chart family (`cartesian.py`,
`pie.py`, `radar.py`, `stock.py`, `surface.py`, `histogram.py`, `box.py`,
`waterfall.py`, `funnel.py`, `hierarchy.py`, `region.py`), and the modules
share `common.py`. Where matplotlib has a call for the chart, it is drawn
through the patched `Axes` call, so the layers come from the ordinary
matplotlib readers; where it has none (radar, bubble sizes, candles,
waterfall, funnel, treemap, sunburst, map) the marks are drawn from plain
artists and `layers.py` registers an `ExcelLayer` built from the chart's own
values through `FigureManager.add_plot`, its selectors naming each mark's gid.
It reads with lxml, not openpyxl, which loads every cell of the workbook
before it shows a chart.
`maidr/tensorboard/` (experimental, `docs/stability.qmd#tensorboard-support`)
reads the scalars and histograms of a TensorBoard log directory for
`maidr.read_tensorboard_scalars` and `maidr.read_tensorboard_histograms`:
`events.py` decodes the TFRecord event files and the few protobuf fields a
scalar or histogram needs by hand, so neither TensorFlow, TensorBoard nor
protobuf is a dependency, converts a legacy histogram as TensorBoard's
`data_compat` does, and follows TensorBoard's own rules for restarted runs;
`logdir.py` finds runs and tags; `__init__.py` draws one chart per scalar tag
through the patched `Axes.plot`; `distributions.py` reads each histogram at
TensorBoard's nine basis points as one line layer of nine lines over
unregistered band polygons; `histograms.py` draws one ridge polygon per
step and registers a `RidgelinePlot` (`maidr/core/plot/ridgeline.py`) built
from the binned counts through `FigureManager.add_plot`; `hparams.py` reads
the HParams plugin's `HParamsPluginData` and draws the parallel coordinates
from plain `Line2D`s, registering a `PrebuiltPlot`
(`maidr/core/plot/prebuilt.py`) that carries the unscaled values, and the
scatter matrix through the patched `scatter`; `projector.py` reads the
Embedding Projector's `projector_config.pbtxt` and its TSV vectors (or, with
TensorFlow installed, a checkpoint variable) and draws the first two principal
components through the patched `scatter`, a layer per label. Its tests compare
against what TensorBoard itself read from logs real writers wrote
(`tests/tensorboard/fixtures/make_fixtures.py`).
`maidr/keras.py` (experimental, `docs/stability.qmd#keras-support`) draws a
Keras model's training curves and confusion matrix: `plot_history` from a
`History` or its dictionary, `plot_confusion_matrix` from the predictions
through the patched `imshow`, and `MaidrCallback`, a
`keras.callbacks.Callback` that rewrites an HTML page as the model trains. It imports Keras only for that base class, and
`import maidr` does not import it. Keras is not a dev dependency: the callback
tests stand in a bare `Callback`, and the one real `model.fit` test runs only
where Keras is installed.

### Canonical `axes` Payload

Every emitted schema's `axes` object follows the canonical per-axis form:

```python
{
    "x": {"label": "...", "min": ..., "max": ..., "tickStep": ..., "format": {...}},
    "y": {"label": "...", ...},
    "z": {"label": "..."},  # only when applicable (heatmap colorbar, hue/legend)
}
```

- Keys of `axes` are a subset of `{x, y, z}`. No other keys are allowed.
- Each value is an `AxisConfig` dict. `label` is a string; `min`/`max`/`tickStep` are numbers; `format` is a dict.
- `format`, `min`, `max`, `tickStep`, `fill`, and `level` must **never** appear as siblings of `x`/`y`/`z`.
- Use `MaidrPlot._axis_config(...)` / `PlotlyPlot._axis_config(...)` helpers to build an `AxisConfig` so only non-`None` fields are emitted.
- `tests/core/test_axes_schema.py` enforces this contract across real emitters.

## Code Style

- **Linter/Formatter**: Ruff (line-length 88), configured in pyproject.toml
- **PEP 8** style; **NumPy-style docstrings** for all functions and classes
- **Type annotations** on all functions
- **Commits**: Conventional commits enforced in CI (allowed tags: feat, fix, docs, perf, refactor, style, test, build, chore, ci). Semantic release uses `feat` for minor, `fix`/`perf` for patch.

## Testing

Tests live in `tests/` using pytest + pytest-mock. Test fixtures in `tests/fixture/` use a factory pattern (`MatplotlibFactory`, `SeabornFactory`) to create test plots. Tests are parametrized across library/plot-type combinations.

`tests/docs/test_gallery_examples.py` executes every `{python}` chunk of the
gallery pages (`docs/examples/*.qmd`, `docs/examples-plotly.qmd`,
`docs/examples-bokeh.qmd`, `docs/examples-plotnine.qmd`,
`docs/examples-altair.qmd`, `docs/examples-excel.qmd`,
`docs/examples-tensorboard.qmd`, `docs/examples-keras.qmd`) and pins the layer types
each section emits, plus the measured claims the prose makes. Adding or changing a gallery example means
updating its `EXPECTED_LAYERS` entry there.
