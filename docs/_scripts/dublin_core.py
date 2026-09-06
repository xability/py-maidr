"""Add Dublin Core meta tags to every rendered page.

Reference managers read a page's bibliographic details from embedded meta
tags. Zotero's Embedded Metadata translator looks for Highwire Press
``citation_*`` tags first, then Dublin Core, then Open Graph, and finally falls
back to ``<title>`` with no author and no date -- which is what this site gave
it before.

We deliberately do not emit ``citation_*``. Google Scholar's inclusion
guidelines reserve those tags for scholarly articles and say they must not
carry a repository or site name, so putting them on software documentation
misrepresents the page and risks the site being dropped from Scholar. Dublin
Core carries the same facts without claiming the page is a paper, and it is
what Zotero reads next. The two MAIDR papers stay cited by DOI in the page's
JSON-LD and in the visible citation section.

This runs as a Quarto ``post-render`` step rather than through
``include-in-header``, because that key injects the same text into every page
and the title, identifier and date differ per page.

It uses only the standard library so it runs under whichever interpreter
Quarto resolves, and it is idempotent.
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import sys
from pathlib import Path

PUBLISHER = "(x)Ability Design Lab, University of Illinois Urbana-Champaign"

# Surname-first so Zotero splits each into first and last names rather than
# storing the whole string as a single-field name. Matches `authors` in
# pyproject.toml.
CREATORS = ["Seo, JooYoung", "Venkatesh, Saairam"]

RIGHTS = "GPL-3.0-or-later"

# The home page stands for the library itself; every other page is
# documentation about it. Telling a reference manager that a guide page is the
# program would be a different kind of wrong.
SOFTWARE_PAGE = "index.html"

_TITLE = re.compile(r"<title>(?P<title>.*?)</title>", re.S)
_DESCRIPTION = re.compile(
    r'<meta\s+name="description"\s+content="(?P<content>[^"]*)"', re.I
)
_CANONICAL = re.compile(r'<link\s+rel="canonical"\s+href="(?P<href>[^"]*)"', re.I)
# The first `</head>` closes the real head: a page that shows HTML in its body
# has it after this one, and a literal `</head>` inside the head would end the
# head for a browser too, so such a page is already broken.
_HEAD_END = re.compile(r"</head>", re.I)
_ALREADY = re.compile(r'<meta\s+name="DC\.', re.I)


def _has_history(repo: Path) -> bool:
    """Report whether ``repo`` holds enough history to date a file by.

    A depth-1 checkout has a single commit with no parent, so git treats every
    tracked path as added by it and ``git log -1 -- <path>`` reports that one
    commit for all of them -- every page would carry the build date while
    looking correctly per-page. A wrong date that looks right is worse than
    none, so that case is reported rather than dated.

    Being shallow is not itself the problem: a checkout deepened to many
    commits still distinguishes the files changed recently, which is what the
    dates are for. Only the single-commit case is unusable.

    Parameters
    ----------
    repo : Path
        Working directory of the repository to ask.

    Returns
    -------
    bool
        True when the checkout holds more than one commit. False when it holds
        one, or when git cannot be run at all.
    """
    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    if out.returncode != 0:
        return False
    try:
        return int(out.stdout.strip()) > 1
    except ValueError:
        return False


def _git_date(repo: Path, rel_path: str) -> str:
    """Return the date of the last commit touching ``rel_path``.

    Parameters
    ----------
    repo : Path
        Working directory of the repository to ask.
    rel_path : str
        Path relative to ``repo``.

    Returns
    -------
    str
        An ISO date, or an empty string when git cannot answer -- an untracked
        path, or no git at all.
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", rel_path],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _source_date(repo: Path, page: Path, site_dir: Path, package_date: str) -> str:
    """Date for ``page``, from the .qmd it was rendered from.

    The ``api/`` pages are written by ``quartodoc build`` and are not in git,
    so they take the date of the package they document.

    Parameters
    ----------
    repo : Path
        Working directory of the repository.
    page : Path
        The rendered HTML file.
    site_dir : Path
        Render output directory ``page`` sits under.
    package_date : str
        Date of the ``maidr`` package, used for the generated ``api/`` pages
        and as the fallback for a page whose source git cannot date. Empty
        when the checkout has no usable history, which makes this return
        empty too rather than guess.

    Returns
    -------
    str
        An ISO date, or an empty string when no date can be trusted.
    """
    rel = page.relative_to(site_dir).with_suffix(".qmd")
    if rel.parts and rel.parts[0] == "api":
        return package_date
    if not package_date:
        return ""
    date = _git_date(repo, str(Path("docs") / rel))
    return date or package_date


def _tags(
    title: str, description: str, identifier: str, date: str, dc_type: str
) -> str:
    """Build the Dublin Core block for one page.

    Parameters
    ----------
    title : str
        Page title, with the site-name suffix already stripped.
    description : str
        Same text as the page's meta description; omitted when empty.
    identifier : str
        Canonical URL of the page.
    date : str
        ISO date the page's source was last changed; omitted when empty.
    dc_type : str
        A Dublin Core Type Vocabulary term, ``Software`` or ``Text``.

    Returns
    -------
    str
        Newline-terminated ``<meta>`` tags, ready to splice before ``</head>``.
    """
    pairs: list[tuple[str, str]] = [("DC.title", title)]
    pairs += [("DC.creator", creator) for creator in CREATORS]
    pairs.append(("DC.publisher", PUBLISHER))
    if description:
        pairs.append(("DC.description", description))
    pairs += [
        ("DC.identifier", identifier),
        ("DC.type", dc_type),
        ("DC.format", "text/html"),
        ("DC.language", "en"),
        ("DC.rights", RIGHTS),
    ]
    if date:
        pairs.append(("DC.date", date))
    return (
        "\n".join(
            f'<meta name="{name}" content="{html.escape(content, quote=True)}">'
            for name, content in pairs
        )
        + "\n"
    )


def process(page: Path, site_dir: Path, repo: Path, package_date: str) -> str:
    """Insert the Dublin Core block into ``page``.

    Returns
    -------
    str
        ``"added"`` when the block was written, ``"present"`` when the page
        already had one, ``"skipped"`` when the page carries no title or no
        canonical URL to build one from.
    """
    text = page.read_text(encoding="utf-8")
    if _ALREADY.search(text):
        return "present"

    title_match = _TITLE.search(text)
    if title_match is None:
        return "skipped"
    # Quarto renders "<page title> – <site name>"; the suffix is site
    # furniture, and a reference manager should record the page's own title.
    title = html.unescape(title_match.group("title")).strip()
    title = re.split(r"\s+[–—|]\s+", title)[0].strip() or title

    description_match = _DESCRIPTION.search(text)
    description = (
        html.unescape(description_match.group("content")) if description_match else ""
    )

    canonical_match = _CANONICAL.search(text)
    if canonical_match is None:
        # Without a canonical URL there is no stable identifier to record, and
        # `canonical-url: true` in _quarto.yml means every page has one.
        return "skipped"
    identifier = html.unescape(canonical_match.group("href"))

    rel = page.relative_to(site_dir).as_posix()
    block = _tags(
        title=title,
        description=description,
        identifier=identifier,
        date=_source_date(repo, page, site_dir, package_date),
        dc_type="Software" if rel == SOFTWARE_PAGE else "Text",
    )
    page.write_text(_HEAD_END.sub(block + "</head>", text, count=1), encoding="utf-8")
    return "added"


def main() -> int:
    """Add the Dublin Core block to every page under the render output.

    Returns
    -------
    int
        0 when at least one page carries the block, 1 when none does. Quarto
        swallows this script's stdout, so exiting non-zero is the only way a
        silent no-op reaches the build log.
    """
    site_dir = Path(
        os.environ.get("QUARTO_PROJECT_OUTPUT_DIR")
        or Path(__file__).parent.parent / "_site"
    )
    if not site_dir.is_dir():
        print(f"dublin_core: {site_dir} not found, nothing to do", file=sys.stderr)
        return 0

    repo = Path(__file__).resolve().parents[2]
    if _has_history(repo):
        package_date = _git_date(repo, "maidr")
    else:
        # Emit the block without DC.date rather than stamping every page with
        # the checkout's own commit. Fix by giving the workflow's checkout step
        # `fetch-depth: 0`.
        print(
            "dublin_core: single-commit checkout, omitting DC.date "
            "(set fetch-depth: 0 on the checkout step)",
            file=sys.stderr,
        )
        package_date = ""

    counts = {"added": 0, "present": 0, "skipped": 0}
    for page in sorted(site_dir.rglob("*.html")):
        counts[process(page, site_dir, repo, package_date)] += 1

    if not os.environ.get("QUARTO_PROJECT_SCRIPT_QUIET"):
        print(
            f"dublin_core: {counts['added']} page(s) tagged, "
            f"{counts['present']} already tagged, {counts['skipped']} skipped"
        )

    # Quarto swallows this script's stdout, so a silent no-op would ship a
    # site with no bibliographic metadata and nothing in the log to show it.
    # Fail loudly instead: the site always has pages, and they always have a
    # canonical URL, so ending with none tagged means something broke.
    if counts["added"] + counts["present"] == 0:
        print(
            f"dublin_core: no page under {site_dir} could be tagged "
            f"({counts['skipped']} skipped)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
