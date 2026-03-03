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
- **`maidr/widget/shiny.py`** — Shiny framework integration

### Supported Plot Types

Defined in `maidr/core/enum/plot_type.py`: BAR, BOX, COUNT, DODGED, HEAT, HIST, LINE, SCATTER, STACKED, SMOOTH, CANDLESTICK.

## Code Style

- **Linter/Formatter**: Ruff (line-length 88), configured in pyproject.toml
- **PEP 8** style; **NumPy-style docstrings** for all functions and classes
- **Type annotations** on all functions
- **Commits**: Conventional commits enforced in CI (allowed tags: feat, fix, docs, perf, refactor, style, test, build, chore, ci). Semantic release uses `feat` for minor, `fix`/`perf` for patch.

## Testing

Tests live in `tests/` using pytest + pytest-mock. Test fixtures in `tests/fixture/` use a factory pattern (`MatplotlibFactory`, `SeabornFactory`) to create test plots. Tests are parametrized across library/plot-type combinations.
