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


#: The stable set as it stood at ``d9f7aee``, the last commit before #345.
#:
#: Written out rather than spot-checked, so the whole classification is what
#: the suite verifies. A contributor can otherwise misfile a type into the
#: wrong table and still leave both tables internally consistent -- the
#: partition check above would pass, and only this would notice.
#:
#: Re-derive with::
#:
#:     git show d9f7aee:maidr/core/enum/plot_type.py \
#:       | grep -oE '^\s+[A-Z_0-9]+ = "[a-z_0-9]+"'
STABLE_AT_D9F7AEE = {
    "BAR",
    "BOX",
    "CANDLESTICK",
    "COUNT",
    "DODGED",
    "HEAT",
    "HIST",
    "LINE",
    "PIE",
    "SCATTER",
    "SMOOTH",
    "STACKED",
    "STEP",
    "VIOLIN_BOX",
    "VIOLIN_KDE",
}


def test_the_stable_set_is_exactly_the_one_that_predates_the_roadmap() -> None:
    """The whole set, not a sample.

    The partition check is satisfied by any split that covers the enum,
    including a wrong one, so the boundary needs its own assertion.
    """
    assert _members("Stable") == STABLE_AT_D9F7AEE


def test_everything_else_is_experimental() -> None:
    """The complement, so a misfiled member fails from both directions."""
    expected = {member.name for member in PlotType} - STABLE_AT_D9F7AEE

    assert _members("Experimental") == expected


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
