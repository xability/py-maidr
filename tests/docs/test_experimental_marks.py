"""A gallery heading says whether the chart under it is experimental.

``docs/stability.qmd`` splits the plot types into a stable set and an
experimental one, and the rest of the docs mark an experimental type by
putting ``[experimental]`` after its name. A section heading is where a reader
scanning the gallery meets the type, so it is where a missing mark misleads.

What a section emits is already pinned by ``EXPECTED_LAYERS`` (and checked by
executing the page in ``test_gallery_examples.py``), so this reads the
classification from there rather than running anything: a section whose
layers are all experimental carries the mark, and a section whose layers are
all stable does not. A section mixing the two is left to the prose.
"""

from __future__ import annotations

import pytest

from maidr.core.enum.plot_type import PlotType
from tests.core.test_plot_type_stability import _members
from tests.docs.test_gallery_examples import DOCS, EXPECTED_LAYERS

MARK = "[experimental]"

#: The Altair page lists Vega-Lite marks, not py-maidr layer types, so there
#: is nothing here to classify.
UNCLASSIFIED_PAGES = {"examples-altair.qmd"}

#: Pages that are about one experimental type throughout, whose section
#: headings ("One classifier") name no type. The mark is carried by the page:
#: its navigation label, and a Prototype callout before the first section.
WHOLE_PAGE_EXPERIMENTAL = {"examples/roc.qmd"}

EXPERIMENTAL = {PlotType[name].value for name in _members("Experimental")}
STABLE = {PlotType[name].value for name in _members("Stable")}


def _emitted(figures: list[list[str]]) -> set[str]:
    """Every layer type a section shows, across all its figures and cells."""
    return {
        layer for figure in figures for cell in figure for layer in cell.split(" + ")
    }


SECTIONS = [
    (page, section, _emitted(figures))
    for page, sections in EXPECTED_LAYERS.items()
    if page not in UNCLASSIFIED_PAGES
    for section, figures in sections.items()
]


@pytest.mark.parametrize(
    ("page", "section", "emitted"),
    SECTIONS,
    ids=[f"{page}::{section}" for page, section, _ in SECTIONS],
)
def test_heading_marks_experimental_sections(
    page: str, section: str, emitted: set[str]
) -> None:
    assert emitted <= STABLE | EXPERIMENTAL, f"unclassified layer types: {emitted}"

    if emitted <= EXPERIMENTAL and page not in WHOLE_PAGE_EXPERIMENTAL:
        assert section.endswith(f" {MARK}"), (
            f"{page}: '{section}' emits only experimental types {sorted(emitted)}"
            f" and its heading should end with ' {MARK}'"
        )
    if emitted <= STABLE:
        assert (
            MARK not in section
        ), f"{page}: '{section}' emits only stable types {sorted(emitted)}"


@pytest.mark.parametrize("page", sorted(WHOLE_PAGE_EXPERIMENTAL))
def test_whole_page_experimental_is_marked_at_page_level(page: str) -> None:
    for section, figures in EXPECTED_LAYERS[page].items():
        assert _emitted(figures) <= EXPERIMENTAL, f"{page}: '{section}' is not"

    text = (DOCS / page).read_text(encoding="utf-8")
    before_first_section = text.split("\n## ", 1)[0]
    assert '::: {.callout-warning title="Prototype"}' in before_first_section

    navigation = (DOCS / "_quarto.yml").read_text(encoding="utf-8")
    label = navigation.split(f"href: {page}", 1)[0].rsplit("text:", 1)[1]
    assert MARK in label, f"the navigation label for {page} is not marked"
