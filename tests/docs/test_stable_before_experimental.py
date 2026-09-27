"""Wherever the docs enumerate plot types, the stable ones come first.

``docs/stability.qmd`` splits the plot types into a stable set and an
experimental one, and ``test_experimental_marks.py`` checks that an
experimental type is marked. Marks alone still leave the two interleaved, so a
reader scanning a list meets prototypes between the types they can rely on.
The docs therefore also *order* by the split: a list of plot types has a
Stable part and then an Experimental part, the navigation groups the pages
about experimental types only after the stable ones, and a gallery page shows
its stable charts before its experimental ones.

The classification is read from ``EXPECTED_LAYERS``, as the marks test does,
rather than from the ``[experimental]`` marks themselves, wherever a section
or page emits layers. The home page lists are prose, so there the mark is the
signal, with the few items that name a stable and an experimental type
together listed below by hand. Each check fails closed: a list, heading or
navigation group it cannot find is a failure, not a pass.
"""

from __future__ import annotations

import re

import pytest
import yaml

from tests.docs.test_experimental_marks import (
    EXPERIMENTAL,
    MARK,
    STABLE,
    UNCLASSIFIED_PAGES,
    _emitted,
)
from tests.docs.test_gallery_examples import DOCS, EXPECTED_LAYERS, _chunks

NOTE = (
    "These may change without a deprecation period; see "
    "[Plot Type Stability](stability.qmd)."
)

#: Pages every one of whose sections emits only experimental types.
WHOLE_PAGE_EXPERIMENTAL = {
    page
    for page, sections in EXPECTED_LAYERS.items()
    if page.startswith("examples/")
    and all(_emitted(figures) <= EXPERIMENTAL for figures in sections.values())
}

#: Home page items that name a stable type and an experimental one together.
#: They stay in the Stable part, carrying the mark on the experimental name.
MIXED_ITEMS = (
    "* Stacked bar plot — several bar traces",
    "* Two-dimensional histogram (`go.Histogram2d`)",
    "* Choropleth map [experimental] (`go.Choropleth`, `px.choropleth`) and "
    "geographic scatter",
)


def test_some_pages_are_whole_page_experimental() -> None:
    """The navigation checks below are vacuous if this set is empty."""
    assert "examples/roc.qmd" in WHOLE_PAGE_EXPERIMENTAL
    assert "examples/area-errorbar-point-lollipop.qmd" in WHOLE_PAGE_EXPERIMENTAL


# --------------------------------------------------------------------------
# Gallery pages
# --------------------------------------------------------------------------

GALLERY = sorted(set(EXPECTED_LAYERS) - UNCLASSIFIED_PAGES)


@pytest.mark.parametrize("page", GALLERY)
def test_gallery_shows_stable_sections_first(page: str) -> None:
    order: list[str] = []
    for chunk in _chunks(DOCS / page):
        if chunk.section in EXPECTED_LAYERS[page] and chunk.section not in order:
            order.append(chunk.section)
    assert set(order) == set(EXPECTED_LAYERS[page]), f"{page}: sections not found"

    seen_experimental = None
    for section in order:
        emitted = _emitted(EXPECTED_LAYERS[page][section])
        if emitted <= EXPERIMENTAL:
            seen_experimental = seen_experimental or section
        elif emitted <= STABLE:
            assert seen_experimental is None, (
                f"{page}: stable section '{section}' comes after the"
                f" experimental section '{seen_experimental}'"
            )


# --------------------------------------------------------------------------
# Lists of plot types
# --------------------------------------------------------------------------


def _section(text: str, heading: str) -> str:
    """The body under ``heading`` up to the next heading of its level or above."""
    level = len(heading) - len(heading.lstrip("#"))
    marker = f"\n{heading}\n"
    assert marker in text, f"heading '{heading}' not found"
    body = text.split(marker, 1)[1]
    stop = re.search(rf"^#{{1,{level}}} ", body, re.MULTILINE)
    return body[: stop.start()] if stop else body


def _split_list(body: str, level: str, bullet: str) -> tuple[list[str], list[str], str]:
    """The items before and after the Experimental sub-heading, and the prose
    between that sub-heading and its first item."""
    headings = re.findall(rf"^{level} (\w+)", body, re.MULTILINE)
    assert headings == [
        "Stable",
        "Experimental",
    ], f"expected '{level} Stable' then '{level} Experimental', got {headings}"
    stable, experimental = re.split(rf"^{level} Experimental\b.*$", body, 1, re.M)

    def items(part: str) -> list[str]:
        return [line for line in part.splitlines() if line.startswith(bullet)]

    lead = experimental.split(f"\n{bullet}", 1)[0]
    return items(stable), items(experimental), lead


INDEX = (DOCS / "index.qmd").read_text(encoding="utf-8")
LIBRARIES = re.findall(
    r"^### (.+)$",
    _section(INDEX, "## Supported Data Visualization Libraries"),
    re.MULTILINE,
)


def test_home_page_lists_every_library() -> None:
    assert {"Matplotlib", "Seaborn", "Plotly", "Altair"} <= set(LIBRARIES)


@pytest.mark.parametrize("library", LIBRARIES)
def test_home_page_lists_stable_types_first(library: str) -> None:
    body = _section(INDEX, f"### {library}")
    items = [line for line in body.splitlines() if line.startswith("* ")]
    if not any(MARK in item for item in items):
        assert "#### Experimental" not in body, f"{library}: nothing experimental"
        return

    stable, experimental, lead = _split_list(body, "####", "* ")
    assert experimental, f"{library}: the Experimental part lists nothing"
    assert NOTE in lead, f"{library}: the Experimental part should say '{NOTE}'"
    for item in experimental:
        assert MARK in item, f"{library}: unmarked item after Experimental: {item}"
    for item in stable:
        if MARK in item:
            assert item.startswith(
                MIXED_ITEMS
            ), f"{library}: an experimental item sits in the Stable part: {item}"


def test_examples_overview_lists_stable_families_first() -> None:
    text = (DOCS / "examples.qmd").read_text(encoding="utf-8")
    body = _section(text, "## Examples by plot family")
    stable, experimental, lead = _split_list(body, "###", "- [")
    assert NOTE in lead

    def page(item: str) -> str:
        href = re.search(r"\]\((examples/[^)]+\.qmd)\)", item)
        assert href, f"no page link in: {item}"
        return href.group(1)

    assert {page(item) for item in experimental} == WHOLE_PAGE_EXPERIMENTAL
    assert not {page(item) for item in stable} & WHOLE_PAGE_EXPERIMENTAL


def test_llms_txt_lists_stable_types_first() -> None:
    text = (DOCS / "llms.txt").read_text(encoding="utf-8")
    stable = re.search(r"^\*\*Stable\*\*: (.+)$", text, re.MULTILINE)
    experimental = re.search(r"^\*\*Experimental\*\*: (.+?)\. ", text, re.MULTILINE)
    assert stable and experimental
    assert text.index(stable.group(0)) < text.index(experimental.group(0))
    assert MARK not in stable.group(1)
    for name in experimental.group(1).split(", "):
        assert name.endswith(f" {MARK}"), f"llms.txt: unmarked '{name}'"

    docs, rest = text.split("\n## Experimental plot families\n", 1)
    grouped = rest.split("\n## ", 1)[0]
    for page in WHOLE_PAGE_EXPERIMENTAL:
        url = page.replace(".qmd", ".html")
        assert url in grouped, f"llms.txt: {page} is not in its experimental group"
        assert url not in docs, f"llms.txt: {page} is listed among the stable pages"


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------

SITE = yaml.safe_load((DOCS / "_quarto.yml").read_text(encoding="utf-8"))["website"]


def test_navbar_groups_experimental_pages_last() -> None:
    (examples,) = [
        item for item in SITE["navbar"]["left"] if item.get("text") == "Examples"
    ]
    menu = examples["menu"]
    headers = [i for i, item in enumerate(menu) if item == {"text": "Experimental"}]
    assert len(headers) == 1, "the Examples menu needs one 'Experimental' header"
    start = headers[0]
    assert menu[start - 1] == {"text": "---"}, "the header should follow a separator"

    end = next(
        (i for i in range(start + 1, len(menu)) if menu[i] == {"text": "---"}),
        len(menu),
    )
    group = {item.get("href") for item in menu[start + 1 : end]}
    assert group == WHOLE_PAGE_EXPERIMENTAL

    for item in menu[:start]:
        href = item.get("href", "")
        assert href not in WHOLE_PAGE_EXPERIMENTAL, f"{href} is before its group"
    for item in menu[end:]:
        href = item.get("href", "")
        assert not href.startswith("examples/"), f"{href} is after the group"


def test_sidebar_groups_experimental_pages_after_stable_ones() -> None:
    (examples,) = [bar for bar in SITE["sidebar"] if bar.get("id") == "examples"]
    sections = [item["section"] for item in examples["contents"] if "section" in item]
    assert "Plot families" in sections
    assert "Experimental plot families" in sections
    assert sections.index("Plot families") < sections.index(
        "Experimental plot families"
    )

    def hrefs(section: str) -> set[str]:
        (entry,) = [
            item
            for item in examples["contents"]
            if isinstance(item, dict) and item.get("section") == section
        ]
        return {
            item if isinstance(item, str) else item["href"]
            for item in entry["contents"]
        }

    assert hrefs("Experimental plot families") == WHOLE_PAGE_EXPERIMENTAL
    assert not hrefs("Plot families") & WHOLE_PAGE_EXPERIMENTAL
