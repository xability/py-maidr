"""The shortcut table names the keys the bundled maidr.js actually binds.

``@tbl-shortcuts`` in ``docs/index.qmd`` is the page's canonical list, and
every other section cites it rather than restating a binding. That makes it
part of the public contract, and it is exactly the kind of thing that goes
stale silently: ``maidr/static/maidr.js`` is bumped, a binding moves, and the
table keeps describing the old key until a reader tries it.

It had gone stale three ways at once before this test existed -- two rows
claimed ``Ctrl + Home``/``Ctrl + End``, which no keymap binds; the Mac column
for Stop Auto-play said Ctrl where ``Platform.ctrl`` resolves to Command; and
the chat row named the ``?`` glyph without the ``Shift + /`` chord that
produces it.

This is the same guard, and for the same reason, as
``tests/core/test_docs_quote_the_real_warning.py``: the docs quote something
the code owns, so the code is asked whether the quote is still true.

The bundle is minified, so the shape it is parsed by matters. Two things in
it are stable across a minifier run and are what the regex anchors on: the
``keybinding.*`` message ids, which are i18n keys rather than locals, and the
``helpKey`` property name. Local identifiers (``z``, ``R``, ``Gm``) are not,
so nothing here depends on them -- the one place a mangled name appears
inside a value, ``${R.ctrl}``, is normalized away below.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).parents[2]
_BUNDLE = _REPO / "maidr" / "static" / "maidr.js"
_PAGE = _REPO / "docs" / "index.qmd"

#: ``z(<hotkey>, `keybinding.<id>`, {helpKey: `<key>`})`` in the minified
#: bundle. Only the message id and the ``helpKey`` literal are captured; the
#: hotkey is often a hoisted constant (``Gm`` for the help chord) and so is
#: not readable here, while ``helpKey`` is what the app shows a reader and
#: what the table is supposed to agree with.
_BINDING = re.compile(r"`keybinding\.(\w+)`,\{helpKey:`([^`]*)`\}")

#: ``Platform.ctrl`` is a getter returning ``'command'`` on Mac and ``'ctrl'``
#: elsewhere, so a helpKey interpolating it is one binding with two spellings.
#: The object it is read from is a mangled local, so match the property.
_PLATFORM_CTRL = re.compile(r"\$\{\w+\.ctrl\}")


def _bundle_help_keys() -> dict[str, str]:
    """Every ``keybinding.*`` id in the bundle, mapped to its help key.

    ``${R.ctrl}`` is normalized to ``${ctrl}`` so the expectations below do
    not encode whatever the minifier called that object this build.
    """
    text = _BUNDLE.read_text(encoding="utf-8", errors="replace")
    found = {
        command: _PLATFORM_CTRL.sub("${ctrl}", help_key)
        for command, help_key in _BINDING.findall(text)
    }
    assert found, (
        "no `keybinding.*` entries with a helpKey were found in "
        f"{_BUNDLE.relative_to(_REPO)}. The bundle's shape has changed -- "
        "teach this test the new form rather than deleting it, or the "
        "shortcut table goes back to being unchecked"
    )
    return found


#: One row per binding the table documents and this test pins.
#:
#: Each entry is (command id, the helpKey the bundle must still carry, the
#: table row as it must still read). All three are literals on purpose: when
#: this fails, the message can name what the bundle says and what the page
#: says, and a reader can compare them without decoding a normalizer.
_ROWS: list[tuple[str, str, str]] = [
    (
        "stopAutoplay",
        "${ctrl}",
        "| Stop Auto-play | Ctrl | CMD |",
    ),
    (
        "goToMinimumValue",
        "[ (open bracket)",
        "| Jump to the lowest value | Open bracket ([) | Open bracket ([) |",
    ),
    (
        "goToMaximumValue",
        "] (close bracket)",
        "| Jump to the highest value | Close bracket (]) | Close bracket (]) |",
    ),
    (
        "openSettings",
        "${ctrl} + ,",
        "| Open or close settings, including AI providers and API keys "
        "| Ctrl + Comma (,) | CMD + Comma (,) |",
    ),
    (
        "openChat",
        "?",
        "| Open or close the AI chat | Shift + Slash (?) | Shift + Slash (?) |",
    ),
    (
        "openCloseHelp",
        "${ctrl} + /",
        "| Open or close the keyboard help | Ctrl + Slash (/) | CMD + Slash (/) |",
    ),
]


class TestTheBundleStillBindsWhatTheTableClaims:
    """Each documented row still matches the bundled engine."""

    def test_every_documented_command_exists(self) -> None:
        bundle = _bundle_help_keys()
        missing = [command for command, _, _ in _ROWS if command not in bundle]
        assert not missing, (
            f"@tbl-shortcuts documents {missing}, which the bundled maidr.js no "
            "longer binds. Either the binding moved and the table needs the new "
            "key, or the feature is gone and the row should be dropped -- the "
            "rows claiming Ctrl + Home and Ctrl + End were the latter"
        )

    def test_every_documented_key_is_unchanged(self) -> None:
        bundle = _bundle_help_keys()
        drifted = [
            (command, expected, bundle[command])
            for command, expected, _ in _ROWS
            if command in bundle and bundle[command] != expected
        ]
        assert not drifted, (
            "the bundled maidr.js changed a key @tbl-shortcuts documents "
            f"(command, documented, bundle): {drifted}. Update the table row "
            "and the expectation here together"
        )


class TestThereIsOnlyOneTable:
    """A second copy of the table is how the first one drifted.

    ``docs/examples.qmd`` carried a byte-identical duplicate, under the same
    ``{#tbl-shortcuts}`` id, and it kept all three defects after the copy on
    the Welcome page was fixed -- so a reader landing on ``/examples`` was
    still told to press ``Ctrl + Home``. Two pages defining one crossref id
    also makes ``@tbl-shortcuts`` ambiguous.

    The checks above pin one page's rows. This pins that there is only one
    page to check.
    """

    def test_the_crossref_id_is_defined_once(self) -> None:
        defined = sorted(
            page.relative_to(_REPO).as_posix()
            for page in (_REPO / "docs").rglob("*.qmd")
            if "{#tbl-shortcuts}" in page.read_text(encoding="utf-8")
        )
        assert defined == ["docs/index.qmd"], (
            f"`{{#tbl-shortcuts}}` is defined in {defined}. It belongs to "
            "docs/index.qmd alone -- another page wanting the shortcuts links "
            "to that section instead of copying the table, which is what let "
            "the copies disagree"
        )

    def test_no_other_page_lists_the_mode_toggles_as_a_table(self) -> None:
        """A copied table is still a copy without the crossref id."""
        row = "| Toggle Braille Mode | b | b |"
        carrying = sorted(
            page.relative_to(_REPO).as_posix()
            for page in (_REPO / "docs").rglob("*.qmd")
            if row in page.read_text(encoding="utf-8")
        )
        assert carrying == ["docs/index.qmd"], (
            f"a shortcut table appears in {carrying}. Dropping the crossref id "
            "from a copy does not make it maintainable -- link to "
            "docs/index.qmd#keyboard-shortcuts-and-controls instead"
        )


class TestTheTableStillReadsAsExpected:
    """The rows this pins are still on the page, spelled the same way."""

    def test_every_row_is_present(self) -> None:
        page = _PAGE.read_text(encoding="utf-8")
        absent = [row for _, _, row in _ROWS if row not in page]
        assert not absent, (
            f"these rows are no longer in docs/index.qmd verbatim: {absent}. If "
            "a row was reworded on purpose, update it here too; if it was "
            "dropped, drop its entry"
        )

    def test_a_ctrl_binding_says_cmd_in_the_mac_column(self) -> None:
        """``Platform.ctrl`` is Command on Mac, so the columns differ.

        This reads the row out of ``_ROWS`` rather than off the page, which
        is the point: ``test_every_row_is_present`` already pins the page to
        those literals, so a cell that is wrong in *both* places passes it.
        That is the likely shape of the mistake, since a row is added here
        and to the page in one edit -- and it is how the Stop Auto-play cell
        said Ctrl in the Mac column while its neighbours were right. Stating
        the rule catches a new row that repeats it.
        """
        bundle = _bundle_help_keys()
        wrong = []
        for command, _, row in _ROWS:
            if "${ctrl}" not in bundle.get(command, ""):
                continue
            _, _, windows, mac, _ = row.split("|")
            if "Ctrl" not in windows or "CMD" not in mac:
                wrong.append((command, windows.strip(), mac.strip()))
        assert not wrong, (
            "these rows interpolate Platform.ctrl, so the Windows column is "
            f"Ctrl and the Mac column is CMD, but read: {wrong}"
        )
