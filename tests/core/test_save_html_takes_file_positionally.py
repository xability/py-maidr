"""`maidr.save_html(plot, "output.html")` is the call the tutorial shows.

`file` was keyword-only in the public wrapper and nowhere else --
`Maidr.save_html`, `PlotlyMaidr.save_html` and `AltairMaidr.save_html` all
take it positionally, and `api.save_html` forwards it positionally to each
-- so the getting-started line in `docs/index.qmd` raised `TypeError:
save_html() takes from 0 to 1 positional arguments but 2 were given`,
which tells a tutorial reader nothing useful (#694).

The last test keeps the docs and the signature from drifting apart again:
every `maidr.save_html(...)` call written in the docs must bind to the
real signature.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402

_DOCS = pathlib.Path(__file__).resolve().parents[2] / "docs"


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _bar():
    _, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    return ax


def test_file_may_be_passed_positionally(tmp_path):
    target = tmp_path / "out.html"

    written = maidr.save_html(_bar(), str(target), use_cdn=False)

    assert written == str(target)
    assert target.exists()


def test_file_may_still_be_passed_by_keyword(tmp_path):
    target = tmp_path / "out.html"

    maidr.save_html(_bar(), file=str(target), use_cdn=False)

    assert target.exists()


def test_leaving_file_out_says_which_argument_is_missing():
    with pytest.raises(TypeError, match="file"):
        maidr.save_html(_bar())


def _calls_in(text: str, page: str) -> list[tuple[str, str]]:
    """Every ``maidr.save_html(...)`` call in ``text``, with its argument text.

    Balanced-parenthesis scan rather than a regex, because a call may span
    lines or nest a call of its own. A call whose parenthesis never closes
    is reported here, naming the page and the offset, rather than as a
    ``SyntaxError`` from parsing the rest of the file as an argument list.
    """
    found = []
    for match in re.finditer(r"maidr\.save_html\(", text):
        depth, start = 1, match.end()
        for end in range(start, len(text)):
            depth += {"(": 1, ")": -1}.get(text[end], 0)
            if depth == 0:
                break
        assert depth == 0, (
            f"{page}: maidr.save_html( at offset {match.start()} is never closed"
        )
        found.append((f"{page}:{text.count(chr(10), 0, start) + 1}", text[start:end]))
    return found


def _documented_calls() -> list[tuple[str, str]]:
    """Every ``maidr.save_html(...)`` call across the docs."""
    return [
        call
        for page in sorted(_DOCS.rglob("*.qmd"))
        for call in _calls_in(page.read_text(encoding="utf-8"), page.name)
    ]


def test_the_scan_finds_nested_and_multi_line_calls():
    text = 'x = maidr.save_html(\n    fig, str(tmp / "o.html"),\n)\nmaidr.save_html(fig, file=f("a"))\n'

    assert _calls_in(text, "page.qmd") == [
        ("page.qmd:1", '\n    fig, str(tmp / "o.html"),\n'),
        ("page.qmd:4", 'fig, file=f("a")'),
    ]


def test_an_unclosed_call_is_reported_with_its_page_and_offset():
    with pytest.raises(AssertionError, match=r"page\.qmd: .* offset 7 is never closed"):
        _calls_in("before maidr.save_html(fig, str(x)", "page.qmd")


@pytest.mark.parametrize("where,args", _documented_calls())
def test_every_documented_call_binds_to_the_real_signature(where, args):
    call = ast.parse(f"f({args})", mode="eval").body
    assert isinstance(call, ast.Call)
    positional = [None] * len(call.args)
    keywords = {keyword.arg: None for keyword in call.keywords}

    inspect.signature(maidr.save_html).bind(*positional, **keywords)
