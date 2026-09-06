# Contributing to py-maidr

Thank you for helping make data visualizations accessible. This page covers
setting up a development environment, running the checks CI runs, and
shaping a change so it can be merged. By taking part you agree to our
[Code of Conduct](CONDUCT.md).

## Set up

py-maidr manages its environment with [uv](https://docs.astral.sh/uv/), and
`uv.lock` pins every dependency, so all you need installed is git and uv --
uv fetches a suitable Python (3.9 or newer) if none is available.

```sh
git clone https://github.com/xability/py-maidr.git
cd py-maidr
uv sync --locked --all-extras --dev
uv run pre-commit install
```

`uv sync --locked --all-extras --dev` creates `.venv/` with the package, every
optional extra and the dev tooling, exactly as CI installs them. The pre-commit
hook runs `ruff check --fix` on the files in each commit.

If you use VS Code, accept the recommended extensions for this workspace when
prompted; the settings in `.vscode/` format and lint with ruff.

## Run the tests

```sh
uv run pytest                                                 # whole suite
uv run pytest tests/core/test_figure_manager.py -vvv          # one file
uv run pytest tests/core/test_figure_manager.py::test_get_axes_from_none
```

Always run pytest through `uv run` (or after activating `.venv`). A `pytest`
from some other environment sees a different set of packages and can silently
collect nothing.

Tests live in `tests/` and mirror the package layout (`tests/core`,
`tests/patch`, `tests/plotly`, ...). Plot fixtures in `tests/fixture/` use
factories (`MatplotlibFactory`, `SeabornFactory`), and most tests are
parametrized across library/plot-type combinations.

The tests in `tests/browser/` drive a real Chromium through Playwright and are
skipped unless you opt in:

```sh
uv run playwright install --with-deps chromium   # once
uv run pytest tests/browser --run-browser
```

## Lint and format

Ruff is the only linter and formatter. It is pinned to the same version in
`pyproject.toml`, `.pre-commit-config.yaml` and the CI workflow, so
`uv run ruff` gives the same answer as CI.

```sh
uv run ruff check --fix   # what the pre-commit hook runs
uv run ruff check --diff  # what CI checks
uv run ruff format        # reformat
```

Style: PEP 8 with 88-character lines, type annotations on every function, and
NumPy-style docstrings on every public function and class. The package still
supports Python 3.9, so a module that writes `X | Y` in an annotation needs
`from __future__ import annotations` at the top (ruff rule `FA102` flags this,
and CI checks it separately).

## Dependencies

Runtime dependencies live in `[project.dependencies]`, optional integrations in
`[project.optional-dependencies]`, and development tooling in
`[dependency-groups].dev`, all in `pyproject.toml`. After changing any of them
run `uv lock` and commit the updated `uv.lock`; CI fails on
`uv lock --check` otherwise.

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
and are checked by commitlint in CI:

```
<type>(<optional scope>): <imperative, lower-case description>
```

Types: `feat`, `fix`, `docs`, `perf`, `refactor`, `style`, `test`, `build`,
`chore`, `ci`. Releases are cut automatically from `main` by semantic-release,
so the type matters: `feat` makes a minor release and `fix` or `perf` a patch
release. Pull requests are squash-merged and the PR title becomes the commit
subject, so the title must follow the same format. The title is also the
whole of the pull request that reaches `CHANGELOG.md` and the GitHub release
notes: the description becomes the commit body, which the changelog leaves
out. Write the title as the one line a reader of the release notes sees.

## Documentation

The docs site in `docs/` is built with [Quarto](https://quarto.org/), and the
API reference is generated from docstrings by quartodoc:

```sh
cd docs
uv run quartodoc build
uv run quartodoc interlinks
quarto preview
```

Quarto itself is installed separately, following its own instructions.

## Pull requests

- For anything larger than a small fix, open an issue first (there are
  templates for bug reports and feature requests) so the approach can be
  agreed before the work is done.
- Keep each pull request to one logical change, with a test that fails
  before and passes after, and update any docstring or documentation the
  change makes wrong.
- Fill in the pull request template. CI runs the test suite on Python 3.9
  through 3.12, the browser tests, an install of the package with no extras,
  ruff, and commitlint.
