"""Collection must survive a missing optional extra.

``tests/widget/conftest.py`` and ``tests/plotly/conftest.py`` once called
``pytest.importorskip`` at module scope.  ``Skipped`` is a
``BaseException``, so pytest's conftest loader does not wrap it, and on
the locked pytest 7 every sub-conftest is imported while the *session* is
being collected: the session itself came out "skipped", zero tests were
collected and pytest exited 5 -- which CI reads as a clean skip.  Anyone
without the ``shiny`` or ``plotly`` extra (a ``uv sync --dev`` contributor,
a downstream packager) ran nothing while looking green.

Each case hides one package behind a shadow whose ``__init__`` raises
``ImportError`` and collects the suite in a subprocess.  Collection must
exit 0, the bulk of the suite must still be collected, and the modules
that genuinely need the package must skip with a reason rather than
vanish.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Far above the 0 the bug gave, well below what survives either shadow:
#: the suite has ~3 700 tests, ~1 300 of them under ``tests/plotly``.  The
#: point is "the suite was collected", not a count that every new test file
#: would have to update.
PLENTY = 2000


def _collect_with_shadowed(package: str, tmp_path: pathlib.Path) -> str:
    """Collect the suite with ``package`` unimportable; return pytest's output."""
    shadow = tmp_path / "shadow" / package
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text(
        f'raise ImportError("{package} is shadowed for this test")\n'
    )

    # Start from the caller's environment minus anything that steers pytest
    # itself (``PYTEST_ADDOPTS``, ``PYTEST_PLUGINS``, ...): the run has to
    # reflect the repository's own defaults, not a developer's or a CI job's.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(shadow.parent), env.get("PYTHONPATH", "")) if p
    )
    # The *installed* shiny registers a ``shiny-test`` pytest plugin that
    # would import the shadow before collection starts and abort the run
    # for a different reason.  An environment that really lacks the extra
    # has no such plugin, so autoloading is off and the one plugin the
    # suite relies on is named explicitly.
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-rs",
            "-p",
            "no:cacheprovider",
            "-p",
            "pytest_mock",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"collection exited {result.returncode} with {package} shadowed:\n"
        f"{result.stdout[-3000:]}\n{result.stderr[-3000:]}"
    )
    return result.stdout


def _collected_count(output: str) -> int:
    """The ``N tests collected`` figure from a ``--collect-only -q`` run."""
    match = re.search(r"(\d+) tests? collected", output)
    assert match, f"no collection summary in:\n{output[-2000:]}"
    return int(match.group(1))


def _skipped_modules(output: str) -> set[str]:
    """The test files ``-rs`` reports as skipped during collection."""
    return {
        pathlib.Path(m).name
        for m in re.findall(r"^SKIPPED \[\d+\] (tests/\S+?):\d+", output, re.M)
    }


@pytest.mark.parametrize(
    ("package", "must_skip", "must_survive"),
    [
        (
            "shiny",
            {"test_shiny.py", "test_every_door_agrees.py"},
            "tests/widget/test_streamlit.py::",
        ),
        (
            "plotly",
            {"test_plotly_maidr.py", "test_plotly_plots.py"},
            "tests/core/test_figure_manager.py::",
        ),
    ],
)
def test_collection_survives_a_missing_extra(
    package: str, must_skip: set[str], must_survive: str, tmp_path: pathlib.Path
) -> None:
    output = _collect_with_shadowed(package, tmp_path)

    assert _collected_count(output) > PLENTY
    assert must_survive in output
    # The modules that need the package skip *with a reason*, which is
    # what distinguishes "not installed here" from "silently dropped".
    assert must_skip <= _skipped_modules(output), output[-3000:]
