"""Tests for the Quarto post-render script that adds Dublin Core tags.

``docs/_scripts/dublin_core.py`` is a standalone Quarto ``post-render`` step
rather than part of the ``maidr`` package, so it is loaded here by path, the
same way ``test_api_front_matter.py`` loads its sibling.

Quarto swallows the script's stdout, so a mistake here is invisible in a build
log: the site would publish with wrong metadata and nothing would say so. That
is what these pin.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

try:  # pragma: no cover - the import itself is the version check
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10; this package supports 3.9+
    tomllib = None

_REPO = Path(__file__).parents[2]
_SCRIPT = _REPO / "docs" / "_scripts" / "dublin_core.py"


def _load() -> ModuleType:
    """Import the post-render script by path."""
    spec = importlib.util.spec_from_file_location("dublin_core", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dc = _load()

_PAGE = (
    "<html><head><title>{title}</title>"
    '<meta name="description" content="{description}">'
    '<meta property="og:site_name" content="{site_name}">'
    '<link rel="canonical" href="{canonical}"></head><body>x</body></html>'
)


def _write_page(
    path: Path,
    title: str = "A Page – py-maidr",
    description: str = "What the page is about.",
    canonical: str = "https://py.maidr.ai/a-page.html",
    site_name: str = "py-maidr",
) -> Path:
    """Write a page shaped like Quarto's output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _PAGE.format(
            title=title,
            description=description,
            canonical=canonical,
            site_name=site_name,
        ),
        encoding="utf-8",
    )
    return path


def _tag_values(html: str, name: str) -> list[str]:
    """Every ``content`` of the ``name`` meta tags in ``html``, in order."""
    import re

    return re.findall(rf'<meta name="{re.escape(name)}" content="([^"]*)">', html)


class TestTags:
    """``_tags`` emits the fields a reference manager reads."""

    def test_carries_the_facts_zotero_needs(self) -> None:
        block = dc._tags("T", "D", "https://py.maidr.ai/", "2026-09-06", "Text")
        assert _tag_values(block, "DC.title") == ["T"]
        assert _tag_values(block, "DC.creator") == dc.CREATORS
        assert _tag_values(block, "DC.publisher") == [dc.PUBLISHER]
        assert _tag_values(block, "DC.identifier") == ["https://py.maidr.ai/"]
        assert _tag_values(block, "DC.rights") == [dc.RIGHTS]
        assert _tag_values(block, "DC.language") == ["en"]

    def test_never_emits_citation_tags(self) -> None:
        # Google Scholar reserves those for scholarly articles; the module
        # docstring records why this script must not use them.
        block = dc._tags("T", "D", "https://py.maidr.ai/", "2026-09-06", "Text")
        assert "citation_" not in block

    def test_writes_one_creator_tag_per_author(self) -> None:
        block = dc._tags("T", "D", "https://py.maidr.ai/", "", "Text")
        assert len(_tag_values(block, "DC.creator")) == len(dc.CREATORS) > 1

    def test_omits_an_empty_date_and_description(self) -> None:
        block = dc._tags("T", "", "https://py.maidr.ai/", "", "Text")
        assert "DC.date" not in block
        assert "DC.description" not in block

    def test_a_backslash_does_not_become_a_regex_replacement(self) -> None:
        # `re.sub` with a string replacement would read these as escapes or
        # group references and raise, taking the whole render down.
        for title in (r"C:\1 drive", r"regex \d+ example", r"C:\Users\docs"):
            block = dc._tags(title, "D", "https://py.maidr.ai/", "", "Text")
            assert title in block or title.replace("&", "&amp;") in block

    def test_escapes_a_value_that_would_close_the_attribute(self) -> None:
        block = dc._tags('A "quoted" <b>t</b> & more', "D", "u", "", "Text")
        assert "&quot;quoted&quot;" in block
        assert "<b>" not in block


def _git(repo: Path, *args: str, date: str | None = None) -> None:
    """Run a git command in ``repo``, optionally at a fixed commit date."""
    env = {
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@e",
        "PATH": os.environ.get("PATH", ""),
    }
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=repo, check=True, env=env)


@pytest.fixture
def dated_repo(tmp_path: Path) -> Path:
    """A repository whose two files were committed on different days.

    Built rather than borrowed: asserting against this repository's own
    history would pass today and fail the day one commit happens to touch
    both paths -- a rename, a licence sweep, a formatting pass -- even though
    the code under test is still correct.
    """
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "maidr").mkdir()
    _git(repo, "init", "-q")

    (repo / "docs" / "guide.qmd").write_text("guide", encoding="utf-8")
    _git(repo, "add", "docs/guide.qmd")
    _git(repo, "commit", "-qm", "add the guide", date="2026-01-02T00:00:00Z")

    (repo / "maidr" / "api.py").write_text("code", encoding="utf-8")
    _git(repo, "add", "maidr/api.py")
    _git(repo, "commit", "-qm", "add the package", date="2026-03-04T00:00:00Z")
    return repo


class TestSourceDate:
    """``_source_date`` dates a page from the file it was rendered from."""

    def test_generated_api_pages_take_the_package_date(self, dated_repo: Path) -> None:
        # quartodoc writes these; they are not in git.
        site = dated_repo / "_site"
        page = site / "api" / "show.html"
        assert (
            dc._source_date(dated_repo, page, site, "2026-03-04", True) == "2026-03-04"
        )

    def test_a_page_dates_from_its_own_source(self, dated_repo: Path) -> None:
        site = dated_repo / "_site"
        page = site / "guide.html"
        # Its own commit date, not the package's.
        assert (
            dc._source_date(dated_repo, page, site, "2026-03-04", True) == "2026-01-02"
        )

    def test_pages_with_different_sources_get_different_dates(
        self, dated_repo: Path
    ) -> None:
        # The whole point of the feature: one shared timestamp is the bug.
        site = dated_repo / "_site"
        package_date = dc._git_date(dated_repo, "maidr")
        dates = {
            dc._source_date(dated_repo, site / rel, site, package_date, True)
            for rel in ("guide.html", "api/show.html")
        }
        assert dates == {"2026-01-02", "2026-03-04"}

    def test_a_page_whose_source_is_untracked_falls_back_to_the_package(
        self, dated_repo: Path
    ) -> None:
        site = dated_repo / "_site"
        assert (
            dc._source_date(dated_repo, site / "absent.html", site, "2026-03-04", True)
            == "2026-03-04"
        )

    def test_no_usable_history_yields_no_date_rather_than_a_wrong_one(
        self, dated_repo: Path
    ) -> None:
        # `dated` is False when the checkout holds a single commit. It is a
        # separate signal from an empty package date, which only means the
        # package directory itself has no commit.
        site = dated_repo / "_site"
        page = site / "guide.html"
        assert dc._source_date(dated_repo, page, site, "2026-03-04", False) == ""


class TestHasHistory:
    """``_has_history`` separates a usable checkout from a depth-1 one."""

    def test_a_repository_with_several_commits_has_history(
        self, dated_repo: Path
    ) -> None:
        # Built rather than asserted against this checkout, whose depth is a
        # CI setting rather than a property of the code.
        assert dc._has_history(dated_repo) is True

    def test_a_single_commit_checkout_does_not(self, tmp_path: Path) -> None:
        repo = tmp_path / "shallow"
        repo.mkdir()
        run = ["git", "-c", "user.email=t@e", "-c", "user.name=T"]
        subprocess.run([*run, "init", "-q"], cwd=repo, check=True)
        (repo / "a.txt").write_text("a", encoding="utf-8")
        subprocess.run([*run, "add", "a.txt"], cwd=repo, check=True)
        subprocess.run([*run, "commit", "-qm", "one"], cwd=repo, check=True)
        assert dc._has_history(repo) is False

    def test_no_repository_at_all_is_not_usable(self, tmp_path: Path) -> None:
        assert dc._has_history(tmp_path) is False


class TestProcess:
    """``process`` reports what it did and never tags a page twice."""

    def test_tags_a_page_and_strips_the_site_name(self, tmp_path: Path) -> None:
        page = _write_page(tmp_path / "a-page.html", title="A Page – py-maidr")
        assert dc.process(page, tmp_path, _REPO, "2026-09-06") == "added"
        html = page.read_text(encoding="utf-8")
        assert _tag_values(html, "DC.title") == ["A Page"]
        assert _tag_values(html, "DC.identifier") == ["https://py.maidr.ai/a-page.html"]
        # The block goes inside the head, before the body.
        assert html.index("DC.title") < html.index("</head>")

    @pytest.mark.parametrize(
        "title",
        [r"C:\1 drive – py-maidr", r"regex \d+ – py-maidr", r"C:\Users – py-maidr"],
    )
    def test_a_backslash_in_the_title_does_not_crash_the_render(
        self, tmp_path: Path, title: str
    ) -> None:
        # One such page used to abort the run for the entire site.
        page = _write_page(tmp_path / "a.html", title=title)
        assert dc.process(page, tmp_path, _REPO, "") == "added"
        assert _tag_values(page.read_text("utf-8"), "DC.title") == [
            title[: -len(" – py-maidr")]
        ]

    def test_a_backslash_in_the_description_does_not_crash_the_render(
        self, tmp_path: Path
    ) -> None:
        page = _write_page(tmp_path / "a.html", description=r"Matches \d+ digits")
        assert dc.process(page, tmp_path, _REPO, "") == "added"
        assert _tag_values(page.read_text("utf-8"), "DC.description") == [
            r"Matches \d+ digits"
        ]

    def test_is_idempotent(self, tmp_path: Path) -> None:
        page = _write_page(tmp_path / "a-page.html")
        dc.process(page, tmp_path, _REPO, "2026-09-06")
        first = page.read_text(encoding="utf-8")
        assert dc.process(page, tmp_path, _REPO, "2026-09-06") == "present"
        assert page.read_text(encoding="utf-8") == first

    def test_types_the_home_page_as_software_and_others_as_text(
        self, tmp_path: Path
    ) -> None:
        home = _write_page(tmp_path / "index.html")
        other = _write_page(tmp_path / "guide.html")
        dc.process(home, tmp_path, _REPO, "")
        dc.process(other, tmp_path, _REPO, "")
        assert _tag_values(home.read_text("utf-8"), "DC.type") == ["Software"]
        assert _tag_values(other.read_text("utf-8"), "DC.type") == ["Text"]

    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            # Quarto separates with an en dash; the others are defensive.
            ("A Page – py-maidr", "A Page"),
            ("A Page — py-maidr", "A Page"),
            ("A Page | py-maidr", "A Page"),
            # Only an exact trailing site name is a suffix. A title that
            # merely contains a separator keeps all of it.
            ("Sonification — A Deep Dive – py-maidr", "Sonification — A Deep Dive"),
            ("Bar - Line Comparison – py-maidr", "Bar - Line Comparison"),
            # "py-maidr" alone must survive rather than become empty.
            ("py-maidr", "py-maidr"),
        ],
    )
    def test_title_stripping(self, tmp_path: Path, title: str, expected: str) -> None:
        page = _write_page(tmp_path / "a.html", title=title)
        dc.process(page, tmp_path, _REPO, "")
        assert _tag_values(page.read_text("utf-8"), "DC.title") == [expected]

    def test_a_page_without_a_canonical_url_is_skipped(self, tmp_path: Path) -> None:
        # No canonical means no stable identifier to record.
        page = tmp_path / "a.html"
        page.write_text("<html><head><title>T</title></head></html>", encoding="utf-8")
        assert dc.process(page, tmp_path, _REPO, "") == "skipped"
        assert "DC." not in page.read_text(encoding="utf-8")

    def test_a_page_without_og_site_name_keeps_its_whole_title(
        self, tmp_path: Path
    ) -> None:
        # Nothing to strip means nothing is stripped, rather than a guess at
        # where a suffix might begin.
        page = _write_page(tmp_path / "a.html", title="A – B", site_name="")
        dc.process(page, tmp_path, _REPO, "")
        assert _tag_values(page.read_text("utf-8"), "DC.title") == ["A – B"]

    def test_a_page_without_a_title_is_skipped(self, tmp_path: Path) -> None:
        page = tmp_path / "a.html"
        page.write_text(
            '<html><head><link rel="canonical" href="u"></head></html>',
            encoding="utf-8",
        )
        assert dc.process(page, tmp_path, _REPO, "") == "skipped"


class TestMain:
    """``main`` fails loudly when it tagged nothing, or when a page raised."""

    def test_one_unreadable_page_does_not_stop_the_rest(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Not valid UTF-8: `read_text` raises, where the whole run used to die.
        (tmp_path / "broken.html").write_bytes(b"<html><head>\xff\xfe</head></html>")
        _write_page(tmp_path / "fine.html")
        monkeypatch.setenv("QUARTO_PROJECT_OUTPUT_DIR", str(tmp_path))

        # The build still fails -- a page that raised is not "skipped" -- but
        # every other page was processed first and the cause is named.
        assert dc.main() == 1
        assert "DC.title" in (tmp_path / "fine.html").read_text(encoding="utf-8")
        assert "broken.html" in capsys.readouterr().err

    def test_every_failing_page_is_named_not_just_the_first(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        for name in ("a.html", "b.html"):
            (tmp_path / name).write_bytes(b"<html><head>\xff\xfe</head></html>")
        monkeypatch.setenv("QUARTO_PROJECT_OUTPUT_DIR", str(tmp_path))

        assert dc.main() == 1
        err = capsys.readouterr().err
        assert "a.html" in err and "b.html" in err

    def test_exits_non_zero_when_no_page_could_be_tagged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "a.html").write_text("<html><head></head></html>", "utf-8")
        monkeypatch.setenv("QUARTO_PROJECT_OUTPUT_DIR", str(tmp_path))
        assert dc.main() == 1

    def test_exits_zero_when_pages_are_tagged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_page(tmp_path / "a.html")
        monkeypatch.setenv("QUARTO_PROJECT_OUTPUT_DIR", str(tmp_path))
        assert dc.main() == 0

    def test_a_second_run_over_a_tagged_site_still_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Idempotence must not read as "nothing could be tagged".
        _write_page(tmp_path / "a.html")
        monkeypatch.setenv("QUARTO_PROJECT_OUTPUT_DIR", str(tmp_path))
        assert dc.main() == 0
        assert dc.main() == 0


@pytest.mark.skipif(tomllib is None, reason="tomllib is Python 3.11+")
class TestMetadataAgreesWithPackaging:
    """The hand-written constants match what the package declares.

    Skipped on Python 3.9 and 3.10, which have no ``tomllib``. Reading
    pyproject.toml is the whole point of these two cases, and the test matrix
    covers 3.11 through 3.13, so the drift they guard against is still caught
    without adding a parser dependency for two interpreters.
    """

    def test_creators_are_the_pyproject_authors(self) -> None:
        with (_REPO / "pyproject.toml").open("rb") as handle:
            authors = tomllib.load(handle)["project"]["authors"]
        # Surname-first here, "Given Family" there; compare as name sets.
        assert {name.strip() for name in dc.CREATORS} == {
            f"{a['name'].split()[-1]}, {' '.join(a['name'].split()[:-1])}"
            for a in authors
        }

    def test_rights_is_the_pyproject_license(self) -> None:
        with (_REPO / "pyproject.toml").open("rb") as handle:
            license_field = tomllib.load(handle)["project"]["license"]
        expected = (
            license_field
            if isinstance(license_field, str)
            else license_field.get("text", "")
        )
        assert dc.RIGHTS == expected
