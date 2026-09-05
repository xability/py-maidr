"""Tests for the changelog templates in ``templates/``.

python-semantic-release renders ``CHANGELOG.md`` and the GitHub release
notes from ``templates/``, a copy of its own default templates with one
change: an entry is the commit's subject line, not the subject followed by
the whole body.  Every commit on ``main`` is a squash merge whose body is the
pull request description, so with the upstream template a release of a dozen
entries ran to hundreds of lines.

Like ``test_changelog_filter.py``, this exists because nothing reads the
release configuration back before a release: a template that quietly reverts
to the upstream behaviour, or that python-semantic-release quietly stops
picking up, is discovered in the published changelog.  The templates are
rendered here the way ``semantic-release changelog`` renders them, with the
package's own loader, context and filters, against a synthetic squash commit.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

try:  # Python 3.11 and later
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10
    tomllib = pytest.importorskip(
        "tomli",
        reason="reading pyproject.toml needs tomllib (3.11+) or tomli",
    )

# The release tooling is in the ``dev`` dependency group, which every
# workflow that runs the suite installs.  Guarded all the same, for the
# reason ``test_changelog_filter.py`` guards ``tomli``.
pytest.importorskip(
    "semantic_release",
    reason="rendering the templates needs python-semantic-release",
)

from git import Actor  # noqa: E402
from semantic_release.changelog.context import (  # noqa: E402
    ChangelogMode,
    make_changelog_context,
)
from semantic_release.changelog.release_history import ReleaseHistory  # noqa: E402
from semantic_release.changelog.template import (  # noqa: E402
    environment,
    recursive_render,
)
from semantic_release.cli.changelog_writer import generate_release_notes  # noqa: E402
from semantic_release.commit_parser.conventional import (  # noqa: E402
    ConventionalCommitParser,
    ConventionalCommitParserOptions,
)
from semantic_release.hvcs.github import Github  # noqa: E402
from semantic_release.version.version import Version  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = PROJECT_ROOT / "templates"

#: A squash-merge commit as GitHub writes one: the pull request title as the
#: subject, the pull request description as the body.
SUBJECT = "fix(seaborn): read a box chart's grouping from the legend that names it"
BODY = [
    "Three readers still asked `ax.get_legend()` directly after #672 moved "
    "everything else onto `legend_of`.",
    "The label and the levels now come from the same legend.",
    "Closes #674.",
    "Co-authored-by: Someone <someone@example.com>",
]
BREAKING = "`render()` no longer accepts a list of figures."


def squash_commit(subject: str, *paragraphs: str, pr: int = 676) -> Mock:
    """Build the commit object the parser and templates read.

    Parameters
    ----------
    subject : str
        The subject line, without the ``(#N)`` GitHub appends.
    *paragraphs : str
        Body paragraphs, joined by blank lines as git does.
    pr : int
        The pull request number appended to the subject.

    Returns
    -------
    Mock
        Standing in for ``git.Commit``: the parser reads ``message``,
        ``hexsha`` and ``parents`` and nothing else.
    """
    message = "\n\n".join((f"{subject} (#{pr})", *paragraphs))
    return Mock(message=message, hexsha="50b2197" + "0" * 33, parents=())


def release_config() -> dict:
    """Read ``[tool.semantic_release]`` rather than restating it."""
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    return config["tool"]["semantic_release"]


def render(tmp_path: Path, *commits: Mock) -> tuple[str, str, list[str]]:
    """Render the templates as ``semantic-release changelog`` would.

    Parameters
    ----------
    tmp_path : Path
        Stands in for the project root the rendered files land in.
    *commits : Mock
        The commits of the one release being rendered.

    Returns
    -------
    tuple of (str, str, list of str)
        The rendered ``CHANGELOG.md``, the rendered GitHub release notes,
        and every path ``recursive_render`` wrote under ``tmp_path``.
    """
    config = release_config()
    options = config["commit_parser_options"]
    parser = ConventionalCommitParser(
        ConventionalCommitParserOptions(
            allowed_tags=tuple(options["allowed_tags"]),
            minor_tags=tuple(options["minor_tags"]),
            patch_tags=tuple(options["patch_tags"]),
        )
    )

    elements: dict = defaultdict(list)
    for commit in commits:
        for result in parser.parse(commit):
            elements[result.type].append(result)

    someone = Actor("semantic-release", "semantic-release")
    version = Version.parse("1.24.0", tag_format=config["tag_format"])
    release = {
        "tagger": someone,
        "committer": someone,
        "tagged_date": datetime(2026, 9, 5, tzinfo=timezone.utc),
        "elements": elements,
        "version": version,
    }
    history = ReleaseHistory(unreleased={}, released={version: release})
    hvcs = Github(remote_url="https://github.com/xability/py-maidr.git")

    context = make_changelog_context(
        hvcs_client=hvcs,
        release_history=history,
        mode=ChangelogMode(config["changelog"].get("mode", "init")),
        prev_changelog_file=tmp_path / "CHANGELOG.md",
        insertion_flag=config["changelog"].get("insertion_flag", ""),
        mask_initial_release=False,
    )
    # The environment python-semantic-release builds for a user template
    # directory comes from ``[tool.semantic_release.changelog.environment]``,
    # so the settings there -- ``autoescape`` above all -- are under test too.
    env_options = {
        key: value
        for key, value in config["changelog"]["environment"].items()
        if key != "extensions"
    }
    env = context.bind_to_environment(
        environment(template_dir=TEMPLATE_DIR, **env_options)
    )
    written = recursive_render(TEMPLATE_DIR, environment=env, _root_dir=tmp_path)

    notes = generate_release_notes(
        hvcs,
        release=release,
        template_dir=TEMPLATE_DIR,
        history=history,
        style="angular",
        mask_initial_release=False,
    )
    return (tmp_path / "CHANGELOG.md").read_text(), notes, written


def test_psr_finds_the_templates() -> None:
    """The directory must be the one python-semantic-release looks in.

    With no ``.j2`` file there it silently renders its bundled default
    instead, which is the template this directory exists to replace.
    """
    assert release_config()["changelog"]["template_dir"] == "templates"
    assert (TEMPLATE_DIR / "CHANGELOG.md.j2").is_file()
    assert (TEMPLATE_DIR / ".release_notes.md.j2").is_file()


def test_only_the_subject_reaches_the_changelog(tmp_path: Path) -> None:
    """The regression the file exists for: no commit body in an entry."""
    changelog, notes, _ = render(tmp_path, squash_commit(SUBJECT, *BODY))

    for rendered in (changelog, notes):
        assert "## v1.24.0 (2026-09-05)" in rendered
        assert "### Bug Fixes" in rendered
        # Capitalised, scope split out, PR number turned into a link, as the
        # upstream template does; the point is that this is the whole entry.
        assert (
            "**seaborn**: Read a box chart's grouping from the legend that names it"
            " ([#676](https://github.com/xability/py-maidr/pull/676),"
            " [`50b2197`](https://github.com/xability/py-maidr/commit/"
        ) in rendered.replace("\n  ", " ")
        for paragraph in BODY:
            assert paragraph[:40] not in rendered


def test_a_breaking_change_is_still_explained(tmp_path: Path) -> None:
    """Dropping the body must not drop the ``BREAKING CHANGE:`` paragraph.

    That paragraph is the one entry a reader of a major release needs; it
    has its own section, and the section is what must survive.
    """
    changelog, notes, _ = render(
        tmp_path,
        squash_commit(
            "feat(api)!: render one figure at a time",
            *BODY,
            f"BREAKING CHANGE: {BREAKING}",
        ),
    )

    for rendered in (changelog, notes):
        assert "### Breaking Changes" in rendered
        assert f"**api**: {BREAKING}" in rendered
        for paragraph in BODY:
            assert paragraph[:40] not in rendered


def test_a_subject_is_not_html_escaped(tmp_path: Path) -> None:
    """``autoescape`` must be off for the user template environment.

    python-semantic-release renders its bundled template with a fixed
    environment, but a user template directory gets the one configured in
    ``pyproject.toml``.  With Jinja's HTML escaping on there, the apostrophe
    in "chart's" reaches the Markdown as ``&#39;``.
    """
    changelog, _, _ = render(tmp_path, squash_commit(SUBJECT))

    assert "chart's" in changelog
    assert "&#39;" not in changelog
    assert "&quot;" not in changelog


def test_only_the_changelog_is_written(tmp_path: Path) -> None:
    """Rendering the directory must produce ``CHANGELOG.md`` and nothing else.

    ``recursive_render`` walks the whole directory: a ``.j2`` file becomes a
    file of the same name at the project root, and any *other* file is
    copied there as it is.  A ``README.md`` explaining the templates would
    overwrite the project's README at the next release.  Explanations go in
    Jinja comments inside the templates, or under a dot-prefixed name, which
    the walk skips.
    """
    _, _, written = render(tmp_path, squash_commit(SUBJECT))

    assert written == [str(tmp_path / "CHANGELOG.md")]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["CHANGELOG.md"]
