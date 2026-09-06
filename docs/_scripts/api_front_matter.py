"""Give the quartodoc-generated API pages a title and a meta description.

quartodoc 0.8 writes ``api/*.qmd`` without YAML front matter, so Quarto falls
back to the lowercase file stem for ``<title>`` and emits no description.
This script runs as a Quarto ``pre-render`` step (after CI's ``quartodoc
build``) and prepends ``pagetitle`` and ``description`` to every API page that
does not already start with a YAML block. ``pagetitle`` rather than ``title``
is used on purpose: ``title`` would render a second H1 above quartodoc's own
heading.

It uses only the standard library so it runs under whichever interpreter
Quarto resolves, and it is idempotent.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

MAX_DESCRIPTION = 160
# A one-line docstring summary makes a thin snippet; pad it with the site
# context so every page still gets a full, unique description.
SHORT_SUMMARY = 60
SUFFIX = (
    "Part of the py-maidr Python API for accessible matplotlib, seaborn, "
    "Plotly and Altair charts."
)

# The index has no docstring to draw on, so its description is hand-written.
INDEX_PAGETITLE = "API Reference"
INDEX_DESCRIPTION = (
    "Reference for the public py-maidr API: show, render, save_html, stacked, "
    "close, set_backend, set_use_cdn, init_notebook and the Shiny and "
    "Streamlit widgets."
)

_HEADING = re.compile(r"^#\s+(?P<display>.+?)\s*\{\s*#(?P<anchor>[\w.]+)\s*\}\s*$")
_RST_ROLE = re.compile(r":\w+:`~?([^`]+)`")
_FENCE = re.compile(r"^```")


def _first_paragraph(body: list[str]) -> str:
    """Return the first prose paragraph of a rendered API page.

    The heading and the fenced signature block are skipped; the paragraph is
    the first run of non-empty lines that is not inside a code fence and does
    not start a Markdown heading or table.
    """
    paragraph: list[str] = []
    in_fence = False
    for line in body:
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith(("#", "|", ":::")):
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    return " ".join(paragraph)


def _clean(text: str) -> str:
    """Strip RST roles and inline code markers and collapse whitespace."""
    text = _RST_ROLE.sub(r"\1", text)
    text = text.replace("``", "").replace("`", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _truncate(text: str, limit: int = MAX_DESCRIPTION) -> str:
    """Cut ``text`` to ``limit`` characters at a sentence or word boundary."""
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    cut = max(head.rfind(". "), head.rfind("; "))
    if cut >= limit // 2:
        return head[: cut + 1]
    # The ellipsis counts towards the limit, so cut three characters earlier.
    head = text[: limit - 3]
    cut = head.rfind(" ")
    return (head[:cut] if cut > 0 else head).rstrip(",;:") + "..."


def _yaml_string(text: str) -> str:
    """Quote ``text`` as a double-quoted YAML scalar."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _describe(qualname: str, body: list[str]) -> str:
    """Build the meta description for one API page."""
    summary = _clean(_first_paragraph(body))
    if not summary:
        summary = f"Signature and reference documentation for {qualname}."
    if len(summary) < SHORT_SUMMARY:
        summary = f"{summary} {SUFFIX}"
    return _truncate(summary)


def process(path: Path) -> bool:
    """Prepend front matter to ``path``; return True when the file changed."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        return False
    lines = text.split("\n")
    if path.name == "index.qmd":
        pagetitle, description = INDEX_PAGETITLE, INDEX_DESCRIPTION
    else:
        # quartodoc starts each page with its heading; tolerate leading
        # blank lines so a format change fails loudly rather than silently.
        first = next((i for i, line in enumerate(lines) if line.strip()), None)
        match = _HEADING.match(lines[first]) if first is not None else None
        if match is None:
            raise SystemExit(f"{path}: no quartodoc heading on its first line")
        qualname = match.group("anchor")
        pagetitle = f"{qualname} API reference"
        description = _describe(qualname, lines[first + 1 :])
    front_matter = (
        "---\n"
        f"pagetitle: {_yaml_string(pagetitle)}\n"
        f"description: {_yaml_string(description)}\n"
        "---\n\n"
    )
    path.write_text(front_matter + text, encoding="utf-8")
    return True


def main() -> int:
    """Process every ``api/*.qmd`` under the Quarto project directory."""
    project_dir = Path(
        os.environ.get("QUARTO_PROJECT_DIR", Path(__file__).parent.parent)
    )
    api_dir = project_dir / "api"
    if not api_dir.is_dir():
        print(f"api_front_matter: {api_dir} not found, nothing to do", file=sys.stderr)
        return 0
    changed = sum(process(path) for path in sorted(api_dir.glob("*.qmd")))
    quiet = os.environ.get("QUARTO_PROJECT_SCRIPT_QUIET")
    if not quiet:
        print(f"api_front_matter: added front matter to {changed} API page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
