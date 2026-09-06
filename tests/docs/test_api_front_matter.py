"""Tests for the Quarto pre-render script that titles the API pages.

``docs/_scripts/api_front_matter.py`` is a standalone Quarto ``pre-render``
step rather than part of the ``maidr`` package, so it is loaded here by path.
Its string handling parses quartodoc's output, which is the part most likely
to drift on a quartodoc upgrade, so the boundaries are pinned here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).parents[2] / "docs" / "_scripts" / "api_front_matter.py"


def _load() -> ModuleType:
    """Import the pre-render script by path."""
    spec = importlib.util.spec_from_file_location("api_front_matter", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


afm = _load()


class TestFirstParagraph:
    """``_first_paragraph`` skips fences, headings, tables and callouts."""

    def test_skips_the_signature_fence(self) -> None:
        body = [
            "",
            "```python",
            "show(fig=None, renderer='auto')",
            "```",
            "",
            "Render a figure as accessible HTML.",
        ]
        assert afm._first_paragraph(body) == "Render a figure as accessible HTML."

    def test_joins_a_wrapped_paragraph_and_stops_at_the_blank_line(self) -> None:
        body = ["", "Render a figure", "as accessible HTML.", "", "Second paragraph."]
        assert afm._first_paragraph(body) == "Render a figure as accessible HTML."

    def test_skips_headings_tables_and_callouts_before_the_prose(self) -> None:
        body = ["## Parameters", "| name | type |", "::: {.callout}", "", "The prose."]
        assert afm._first_paragraph(body) == "The prose."

    def test_returns_empty_when_there_is_no_prose(self) -> None:
        assert afm._first_paragraph(["", "```", "code", "```", ""]) == ""

    def test_an_unclosed_fence_swallows_the_rest(self) -> None:
        # Better to fall back to the generic description than to lift a code
        # sample into a meta description.
        assert afm._first_paragraph(["```python", "show()", "", "Prose."]) == ""


class TestClean:
    """``_clean`` removes RST roles and inline code markers."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (":func:`~maidr.show`", "maidr.show"),
            (":class:`Figure`", "Figure"),
            ("Use ``maidr.show()`` here.", "Use maidr.show() here."),
            ("Use `show` here.", "Use show here."),
            ("collapse\n  the   whitespace", "collapse the whitespace"),
        ],
    )
    def test_cleans(self, raw: str, expected: str) -> None:
        assert afm._clean(raw) == expected


class TestTruncate:
    """``_truncate`` never exceeds the limit and prefers a sentence boundary."""

    def test_short_text_is_returned_unchanged(self) -> None:
        assert afm._truncate("Short.") == "Short."

    def test_text_at_exactly_the_limit_is_unchanged(self) -> None:
        text = "a" * afm.MAX_DESCRIPTION
        assert afm._truncate(text) == text

    def test_cuts_at_a_sentence_boundary_when_one_is_late_enough(self) -> None:
        # Past the halfway mark, so cutting here keeps most of the text.
        first = (
            "This first sentence runs past the halfway mark of the limit "
            "and then it finally ends here."
        )
        assert len(first) > afm.MAX_DESCRIPTION // 2
        assert afm._truncate(f"{first} {'b' * 200}") == first

    def test_cuts_at_a_semicolon_boundary(self) -> None:
        first = (
            "This clause runs well past the halfway mark of the limit "
            "and then it ends right here;"
        )
        assert len(first) > afm.MAX_DESCRIPTION // 2
        assert afm._truncate(f"{first} {'b' * 200}") == first

    def test_falls_back_to_a_word_boundary_with_an_ellipsis(self) -> None:
        text = " ".join(["word"] * 80)
        cut = afm._truncate(text)
        assert cut.endswith("...")
        assert cut[:-3] == cut[:-3].rstrip()

    def test_an_early_sentence_boundary_does_not_gut_the_description(self) -> None:
        # A boundary before the halfway mark would throw away most of the
        # text, so the word-boundary path is taken instead.
        text = "Hi. " + " ".join(["word"] * 80)
        cut = afm._truncate(text)
        assert cut.endswith("...")
        assert len(cut) > afm.MAX_DESCRIPTION // 2

    def test_trailing_punctuation_is_stripped_before_the_ellipsis(self) -> None:
        text = "word, " * 60
        assert "..." in afm._truncate(text)
        assert ",..." not in afm._truncate(text)

    @pytest.mark.parametrize("length", range(155, 340, 7))
    def test_never_exceeds_the_limit(self, length: int) -> None:
        assert len(afm._truncate(" ".join(["word"] * length))) <= afm.MAX_DESCRIPTION

    def test_a_single_unbroken_token_is_still_capped(self) -> None:
        assert len(afm._truncate("x" * 400)) <= afm.MAX_DESCRIPTION


class TestDescribe:
    """``_describe`` pads thin summaries and falls back when there is none."""

    def test_a_long_summary_is_used_as_is(self) -> None:
        summary = "Render the given matplotlib figure as accessible HTML output."
        assert afm._describe("maidr.show", ["", summary]) == summary

    def test_a_short_summary_is_padded_with_the_site_context(self) -> None:
        description = afm._describe("maidr.close", ["", "Close a figure."])
        assert description.startswith("Close a figure. ")
        assert "py-maidr" in description

    def test_a_missing_summary_falls_back_to_the_qualname(self) -> None:
        description = afm._describe("maidr.show", ["", "```", "code", "```"])
        assert "maidr.show" in description

    @pytest.mark.parametrize(
        "body",
        [
            ["", "Short."],
            ["", "A moderately sized summary of the function's behaviour."],
            ["", " ".join(["word"] * 90)],
            ["", "```", "code", "```"],
        ],
    )
    def test_never_exceeds_the_limit(self, body: list[str]) -> None:
        assert len(afm._describe("maidr.show", body)) <= afm.MAX_DESCRIPTION


class TestYamlString:
    """``_yaml_string`` escapes what would otherwise break the YAML block."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("plain", '"plain"'),
            ('a "quoted" word', '"a \\"quoted\\" word"'),
            ("a \\ backslash", '"a \\\\ backslash"'),
        ],
    )
    def test_escapes(self, raw: str, expected: str) -> None:
        assert afm._yaml_string(raw) == expected


class TestProcess:
    """``process`` is idempotent and fails loudly on an unknown heading."""

    def test_adds_front_matter_to_an_api_page(self, tmp_path: Path) -> None:
        page = tmp_path / "show.qmd"
        page.write_text(
            "# show { #maidr.show }\n\nRender a figure as accessible HTML.\n",
            encoding="utf-8",
        )
        assert afm.process(page) is True
        text = page.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert 'pagetitle: "maidr.show API reference"' in text
        assert "Render a figure as accessible HTML." in text
        # `pagetitle`, not `title`: `title` would render a second H1.
        assert "\ntitle:" not in text

    def test_is_idempotent(self, tmp_path: Path) -> None:
        page = tmp_path / "show.qmd"
        page.write_text("# show { #maidr.show }\n\nProse.\n", encoding="utf-8")
        afm.process(page)
        first = page.read_text(encoding="utf-8")
        assert afm.process(page) is False
        assert page.read_text(encoding="utf-8") == first

    def test_tolerates_leading_blank_lines(self, tmp_path: Path) -> None:
        page = tmp_path / "show.qmd"
        page.write_text("\n\n# show { #maidr.show }\n\nProse.\n", encoding="utf-8")
        assert afm.process(page) is True
        assert 'pagetitle: "maidr.show API reference"' in page.read_text("utf-8")

    def test_the_index_gets_its_hand_written_description(self, tmp_path: Path) -> None:
        page = tmp_path / "index.qmd"
        page.write_text("# API\n", encoding="utf-8")
        assert afm.process(page) is True
        text = page.read_text(encoding="utf-8")
        assert afm.INDEX_PAGETITLE in text
        assert afm.INDEX_DESCRIPTION in text

    @pytest.mark.parametrize(
        "first_line",
        [
            "## show { #maidr.show }",  # not an H1
            "# show",  # no anchor
            "Some prose before the heading.",
            "",  # an empty file
        ],
    )
    def test_an_unrecognized_heading_fails_loudly(
        self, tmp_path: Path, first_line: str
    ) -> None:
        page = tmp_path / "show.qmd"
        page.write_text(f"{first_line}\n\nProse.\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            afm.process(page)

    def test_a_hyphenated_anchor_fails_loudly_rather_than_guessing(
        self, tmp_path: Path
    ) -> None:
        # The anchor pattern allows only word characters and dots. If a future
        # quartodoc emits something else, CI goes red here instead of shipping
        # a page titled after its lowercase file stem.
        page = tmp_path / "show.qmd"
        page.write_text("# show { #maidr-show }\n\nProse.\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            afm.process(page)
