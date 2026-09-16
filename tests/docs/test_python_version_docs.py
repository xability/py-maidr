"""The documented Python support has to match what the package declares.

``docs/index.qmd`` told readers that "Python 3.x" was required while
``requires-python`` said ``>=3.9``, so someone on 3.8 followed the
installation section and got a pip resolution failure the page gave no hint
about. ``CONTRIBUTING.md`` drifted the other way, naming 3.12 as the top of
the CI matrix after 3.13 was added to it.

Four places state the same fact -- ``requires-python``, the trove
classifiers, the CI matrix, and the prose -- and nothing made them agree. A
new interpreter is added to the matrix and the classifiers in one commit and
to the prose in none, which is how both of the above happened.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.9 and 3.10
    tomllib = None  # type: ignore[assignment]

_REPO = Path(__file__).parents[2]
_INSTALL_PAGE = _REPO / "docs" / "index.qmd"
_CONTRIBUTING = _REPO / "CONTRIBUTING.md"
_CI_WORKFLOW = _REPO / ".github" / "workflows" / "ci.yml"


def _version(text: str) -> tuple[int, int]:
    """``"3.10"`` as ``(3, 10)``, so versions sort numerically."""
    major, minor = text.split(".")
    return int(major), int(minor)


def _classifier_versions() -> list[tuple[int, int]]:
    """Every ``Programming Language :: Python :: 3.x`` version, in order."""
    found = re.findall(
        r'"Programming Language :: Python :: (\d+\.\d+)"',
        (_REPO / "pyproject.toml").read_text(encoding="utf-8"),
    )
    assert found, "pyproject.toml no longer lists any Python version classifiers"
    return sorted(_version(raw) for raw in found)


def _matrix_versions() -> list[tuple[int, int]]:
    """The interpreters the ``ci.yml`` test job runs against."""
    matrix = re.search(
        r"python-version:\s*\[(.*?)\]",
        _CI_WORKFLOW.read_text(encoding="utf-8"),
    )
    assert matrix is not None, "ci.yml no longer declares a python-version matrix"
    return sorted(_version(raw) for raw in re.findall(r'"(\d+\.\d+)"', matrix.group(1)))


def _spelled(version: tuple[int, int]) -> str:
    """``(3, 13)`` as ``"3.13"``, the form the prose uses."""
    return f"{version[0]}.{version[1]}"


class TestTheMatrixMatchesTheClassifiers:
    """What CI proves and what PyPI promises are the same set."""

    def test_every_classifier_is_tested(self) -> None:
        untested = set(_classifier_versions()) - set(_matrix_versions())
        assert not untested, (
            "pyproject.toml claims support for "
            f"{sorted(map(_spelled, untested))}, which ci.yml never runs"
        )

    def test_every_tested_version_is_claimed(self) -> None:
        unclaimed = set(_matrix_versions()) - set(_classifier_versions())
        assert not unclaimed, (
            f"ci.yml tests {sorted(map(_spelled, unclaimed))}, which pyproject.toml "
            "does not carry a classifier for"
        )


class TestTheDocsNameTheRealRange:
    """The prose names the same floor and ceiling as the metadata."""

    def test_the_install_section_names_the_minimum(self) -> None:
        minimum = _spelled(_classifier_versions()[0])
        assert f"Python {minimum} or later" in _INSTALL_PAGE.read_text(
            encoding="utf-8"
        ), (
            f"docs/index.qmd should say 'Python {minimum} or later', to match the "
            "lowest version pyproject.toml claims"
        )

    def test_the_install_section_names_the_highest_tested(self) -> None:
        versions = _classifier_versions()
        span = f"{_spelled(versions[0])} through {_spelled(versions[-1])}"
        assert span in _INSTALL_PAGE.read_text(encoding="utf-8"), (
            f"docs/index.qmd should say 'tested on {span}', so a reader on a newer "
            "interpreter knows where the tested range stops"
        )

    def test_contributing_names_the_ci_matrix(self) -> None:
        matrix = _matrix_versions()
        span = f"{_spelled(matrix[0])}\n  through {_spelled(matrix[-1])}"
        assert span in _CONTRIBUTING.read_text(encoding="utf-8"), (
            f"CONTRIBUTING.md should say CI runs {_spelled(matrix[0])} through "
            f"{_spelled(matrix[-1])}, to match ci.yml"
        )


@pytest.mark.skipif(tomllib is None, reason="tomllib is Python 3.11+")
class TestRequiresPythonAgreesWithTheClassifiers:
    """``requires-python`` is the floor the classifiers start from.

    Skipped on 3.9 and 3.10, which have no ``tomllib``. Reading pyproject.toml
    as TOML is the whole point of this case, and the matrix covers 3.11
    through 3.13, so the drift it guards against is still caught without
    adding a parser dependency for two interpreters.
    """

    def test_the_floor_is_the_lowest_classifier(self) -> None:
        with (_REPO / "pyproject.toml").open("rb") as handle:
            requires = tomllib.load(handle)["project"]["requires-python"]

        floor = re.fullmatch(r">=\s*(\d+\.\d+)", requires.strip())
        assert floor is not None, (
            f"requires-python is {requires!r}; this test only understands a '>=X.Y' "
            "floor, so teach it the new form rather than deleting it"
        )
        assert _version(floor.group(1)) == _classifier_versions()[0], (
            f"requires-python promises {requires!r} but the lowest classifier is "
            f"{_spelled(_classifier_versions()[0])}"
        )
