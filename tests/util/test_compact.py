"""The compactor of the script and stylesheet a Shiny string frame carries."""

from __future__ import annotations

import pytest

from maidr.util.compact import compact_css, compact_js, css_blocks


def _wrapped(body: str) -> str:
    return "(function () {\n" + body + "\n})();"


def test_comments_and_spaces_go():
    script = _wrapped(
        "    // a comment\n"
        "    var a = 1;  /* another */\n"
        "    window.x = a + 2;\n"
    )
    assert compact_js(script) == "(function(){var a=1;window.x=a+2;})();"


@pytest.mark.parametrize(
    ("body", "kept"),
    [
        # A line break that ends a statement automatic semicolon insertion
        # reads stays a line break.
        ("var a = b\nvar c = d", "var a=b\nvar c=d"),
        ("a\n++b", "a\n++b"),
        ("window.f = function () { return\n1 };", "return\n1"),
        # One that cannot end a statement goes.
        ("var a = b +\nc", "var a=b+c"),
        ("var a = b\n.c", "var a=b.c"),
    ],
)
def test_line_breaks_that_end_a_statement_are_kept(body, kept):
    assert kept in compact_js(_wrapped(body))


def test_operators_that_would_merge_keep_a_space():
    out = compact_js(_wrapped("var a = b + +c, d = e - -f, g = h++ + i;"))
    assert "b+ +c" in out and "e- -f" in out and "h++ +i" in out


def test_strings_are_left_as_they_are():
    out = compact_js(_wrapped("var a = 'x  // not a comment', b = \"y /* z */\";"))
    assert "'x  // not a comment'" in out and '"y /* z */"' in out


@pytest.mark.parametrize(
    "body", ["var a = /x+/.test(b);", "var a = `x`;", "var a = 'x;", "/* x"]
)
def test_what_it_cannot_read_is_refused(body):
    with pytest.raises(ValueError):
        compact_js(_wrapped(body))


def test_helpers_nothing_calls_go_and_names_are_shortened():
    script = _wrapped(
        "    function maidrUsed(el) { return el.maidrUsed + maidrInner(); }\n"
        "    function maidrInner() { return 1; }\n"
        "    function maidrUnused() { return maidrInner(); }\n"
        "    window.f = function (x) { return maidrUsed({maidrUsed: x}); };\n"
    )
    out = compact_js(script)
    assert "maidrUnused" not in out
    # The functions are renamed where they are called, not as a property
    # or an object's key.
    assert "function maidrUsed" not in out and "function maidrInner" not in out
    assert ".maidrUsed" in out and "{maidrUsed:x}" in out


def test_a_stylesheet_loses_its_comments_spaces_and_needless_quotes():
    css = (
        "/* a comment */\n"
        "figure[id^=\"maidr-figure-\"] > div[tabindex=\"0\"]:focus {\n"
        "  outline: 3px solid #1a5fb4 !important;\n"
        "}\n"
        "html[x] .a .b {\n  margin-top: calc((100vh - var(--r)) / 2);\n}\n"
    )
    assert compact_css(css) == (
        'figure[id^=maidr-figure-]>div[tabindex="0"]:focus'
        "{outline:3px solid #1a5fb4 !important}"
        "html[x] .a .b{margin-top:calc((100vh - var(--r)) / 2)}"
    )


def test_a_stylesheet_is_cut_into_its_rules():
    css = "a{b:c}@media (x){d{e:f}g{h:i}}j>k{l:m}"
    assert css_blocks(css) == ["a{b:c}", "@media (x){d{e:f}g{h:i}}", "j>k{l:m}"]
