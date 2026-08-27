"""The stability split in ``docs/stability.qmd`` has to cover every plot type.

The page divides :class:`PlotType` into a stable set and an experimental one,
and the split is a promise to users: the stable set is what py-maidr was built
around and has been exercised by real readers, and the experimental set is
prototypes that may change in a patch release.

A member that is in neither table inherits whichever promise the reader
assumes, which is the failure this guards. Twenty-two types were added in about
two weeks; at that rate a new one reaching the enum and not the page is the
expected outcome, not an unlikely one.

A member in *both* tables is the other direction of the same drift, and is
worse, because each table reads as complete on its own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from maidr.core.enum.plot_type import PlotType

STABILITY_PAGE = Path(__file__).parents[2] / "docs" / "stability.qmd"


def _section(heading: str) -> str:
    """The body of one ``##`` section of the stability page.

    Parameters
    ----------
    heading : str
        The section heading, without the leading hashes.

    Returns
    -------
    str
        Everything between that heading and the next ``##`` heading.

    Raises
    ------
    AssertionError
        If the page no longer has the heading, so a rename fails here rather
        than silently emptying the set it names.
    """
    text = STABILITY_PAGE.read_text(encoding="utf-8")
    marker = f"\n## {heading}\n"
    assert marker in text, f"docs/stability.qmd no longer has a '{heading}' section"

    body = text.split(marker, 1)[1]
    return body.split("\n## ", 1)[0]


def _members(heading: str) -> set[str]:
    """The ``PlotType`` member names named in one section's table."""
    rows = re.findall(r"^\| `([A-Z_0-9]+)` \|", _section(heading), re.MULTILINE)
    return set(rows)


def test_every_plot_type_is_classified() -> None:
    """No member may sit outside the split and inherit a promise by default."""
    classified = _members("Stable") | _members("Experimental")

    assert classified == {member.name for member in PlotType}


def test_no_plot_type_is_in_both_sets() -> None:
    """Each table reads as complete, so an overlap makes both of them wrong."""
    assert _members("Stable") & _members("Experimental") == set()


@pytest.mark.parametrize(
    ("heading", "member"),
    [
        # `VIOLIN_KDE` is the last type added before the roadmap and `AREA` the
        # first added after, so this pair is where an off-by-one in the
        # boundary would show.
        ("Stable", "VIOLIN_KDE"),
        ("Experimental", "AREA"),
    ],
)
def test_the_boundary_is_where_the_page_says_it_is(heading: str, member: str) -> None:
    """Spot-check the split against ``d9f7aee``, the commit the page names."""
    assert member in _members(heading)


def test_the_page_says_what_experimental_does_not_promise() -> None:
    """The tables alone would read as a changelog.

    What makes the page usable is the claim attached to it, so the claim is
    pinned too: softening the wording without revisiting the split fails here.
    """
    # Normalised, because these phrases are wrapped across lines in the
    # source and a reflow should not be what breaks this test.
    prose = " ".join(STABILITY_PAGE.read_text(encoding="utf-8").split())

    assert "These are prototypes. Treat them as prototypes." in prose
    assert "has been through a user study" in prose
    assert "without a deprecation period" in prose


def test_the_emitted_values_match_the_enum() -> None:
    """A table row names both the member and the string it emits.

    The second column is what reaches the MAIDR schema, so a wrong one sends a
    reader looking for a type that never appears in the output.
    """
    text = STABILITY_PAGE.read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([A-Z_0-9]+)` \| `([a-z_0-9]+)` \|", text, re.MULTILINE)
    assert rows, "the stability tables no longer pair a member with its value"

    for name, emitted in rows:
        assert PlotType[name].value == emitted
