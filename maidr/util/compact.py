"""Make the script and stylesheet a Shiny frame carries smaller, safely.

A frame that :class:`maidr.widget.shiny.render_maidr` does not send carries
the script that sizes it in its ``onload``, and a Shiny app sends the frame,
``onload`` and all, over its websocket with every flush of the output. These
take out what a browser does not need -- comments, indentation, the spaces a
reader does, the helpers a kind of chart never calls -- and shorten the names
of the script's own helpers, without changing what it does. They are made for
the scripts :mod:`maidr.util.iframe_utils` writes, not for every script: one
with a regular expression or a template literal in it is refused rather than
compacted wrongly.
"""

from __future__ import annotations

import re
from typing import List, Tuple

#: Operators and punctuation, longest first.
_PUNCTUATORS = sorted(
    """>>>= ... === !== **= <<= >>= >>> &&= ||= ??= => == != <= >= && || ?? ?.
    ++ -- += -= *= /= %= &= |= ^= ** << >> { } ( ) [ ] ; , < > + - * / % & | ^
    ! ~ ? : = .""".split(),
    key=len,
    reverse=True,
)

#: Words after which a ``/`` would start a regular expression.
_BEFORE_EXPRESSION = {
    "return",
    "typeof",
    "case",
    "do",
    "else",
    "in",
    "of",
    "new",
    "delete",
    "void",
    "throw",
    "instanceof",
    "yield",
    "await",
}

#: Words a line break after which ends the statement (ASI's restricted
#: productions).
_RESTRICTED = {"return", "break", "continue", "throw", "yield"}

_WORD = re.compile(r"[A-Za-z0-9_$]+")
_SPACE = re.compile(r"\s+")
_NUMBER_START = re.compile(r"[0-9]")

Token = Tuple[str, str, bool]  # kind, text, a line break before it


def _tokens(script: str) -> List[Token]:
    """The script's tokens, without its comments and white space.

    Raises
    ------
    ValueError
        On a regular expression, a template literal or an unended string or
        comment: what this tokenizer does not read.
    """
    out: List[Token] = []
    i, n = 0, len(script)
    newline = False
    while i < n:
        c = script[i]
        space = _SPACE.match(script, i)
        if space:
            newline = newline or "\n" in space.group()
            i = space.end()
            continue
        if script.startswith("//", i):
            end = script.find("\n", i)
            i = n if end < 0 else end
            continue
        if script.startswith("/*", i):
            end = script.find("*/", i + 2)
            if end < 0:
                raise ValueError("an unended comment")
            newline = newline or "\n" in script[i:end]
            i = end + 2
            continue
        if c == "`":
            raise ValueError("a template literal")
        if c in "'\"":
            j = i + 1
            while j < n and script[j] != c:
                if script[j] == "\n":
                    raise ValueError("an unended string")
                j += 2 if script[j] == "\\" else 1
            if j >= n:
                raise ValueError("an unended string")
            out.append(("str", script[i : j + 1], newline))
            i = j + 1
        elif _WORD.match(c):
            word = _WORD.match(script, i).group()  # type: ignore[union-attr]
            kind = "num" if _NUMBER_START.match(word) else "id"
            if kind == "num" and script.startswith(".", i + len(word)):
                frac = _WORD.match(script, i + len(word) + 1)
                if frac:
                    word += "." + frac.group()
            out.append((kind, word, newline))
            i += len(word)
        else:
            for punct in _PUNCTUATORS:
                if script.startswith(punct, i):
                    break
            else:
                raise ValueError(f"an unknown character {c!r}")
            if punct in ("/", "/="):
                last = out[-1] if out else ("punct", "(", False)
                if (last[0] == "punct" and last[1] not in (")", "]", "}")) or (
                    last[0] == "id" and last[1] in _BEFORE_EXPRESSION
                ):
                    raise ValueError("a regular expression")
            out.append(("punct", punct, newline))
            i += len(punct)
        newline = False
    return out


def _ends_statement(token: Token) -> bool:
    kind, text, _ = token
    return kind in ("id", "num", "str") or text in (")", "]", "}", "++", "--")


def _starts_statement(token: Token) -> bool:
    kind, text, _ = token
    return kind in ("id", "num", "str") or text in ("{", "++", "--", "!", "~")


def _join(tokens: List[Token]) -> str:
    """The tokens as a script again, with no more space than they need.

    A line break is kept where automatic semicolon insertion may read one:
    between a token that can end a statement and one that can start the
    next, and after ``return`` and the other words a line break ends.
    """
    out: List[str] = []
    last: Token | None = None
    for token in tokens:
        if last is not None:
            kind, text, newline = token
            if newline and (
                (_ends_statement(last) and _starts_statement(token))
                or (last[0] == "id" and last[1] in _RESTRICTED)
            ):
                out.append("\n")
            elif (last[0] in ("id", "num") and kind in ("id", "num")) or (
                last[1][-1:] in "+-" and text[:1] == last[1][-1:]
            ):
                out.append(" ")
            elif last[1][-1:] == "/" and text[:1] in "/*":
                out.append(" ")
        out.append(token[1])
        last = token
    return "".join(out)


def _functions(tokens: List[Token]) -> List[Tuple[str, int, int]]:
    """The functions declared at the script's outermost function's top level.

    Returns their names and where each declaration starts and ends, in
    tokens: the outermost function is the script's own wrapper, ``(function
    () { ... })();``, whose body is at brace depth 1.
    """
    found = []
    depth = 0
    i = 0
    while i < len(tokens):
        text = tokens[i][1]
        if (
            depth == 1
            and tokens[i][0] == "id"
            and text == "function"
            and i + 1 < len(tokens)
            and tokens[i + 1][0] == "id"
        ):
            j = i
            while tokens[j][1] != "{":
                j += 1
            level = 0
            for k in range(j, len(tokens)):
                if tokens[k][1] == "{":
                    level += 1
                elif tokens[k][1] == "}":
                    level -= 1
                    if level == 0:
                        break
            found.append((tokens[i + 1][1], i, k + 1))
            i = k + 1
            continue
        if text == "{":
            depth += 1
        elif text == "}":
            depth -= 1
        i += 1
    return found


def _is_reference(tokens: List[Token], i: int) -> bool:
    """Whether the name at ``i`` is the variable, not a property or a key."""
    before = tokens[i - 1][1] if i else ""
    after = tokens[i + 1][1] if i + 1 < len(tokens) else ""
    return before not in (".", "?.") and not (after == ":" and before in ("{", ","))


def _drop_unused(tokens: List[Token]) -> List[Token]:
    """The tokens without the top-level functions nothing calls."""
    while True:
        declared = _functions(tokens)
        uses: dict = {name: 0 for name, _, _ in declared}
        spans = {name: (start, end) for name, start, end in declared}
        for i, (kind, text, _) in enumerate(tokens):
            if kind == "id" and text in uses and _is_reference(tokens, i):
                start, end = spans[text]
                if not start < i < end:
                    uses[text] += 1
        unused = [spans[name] for name, count in uses.items() if count == 0]
        if not unused:
            return tokens
        for start, end in sorted(unused, reverse=True):
            del tokens[start:end]


def _short_names(tokens: List[Token]) -> List[Token]:
    """The top-level functions' names shortened, wherever they are referred to."""
    names = [name for name, _, _ in _functions(tokens)]
    taken = {text for kind, text, _ in tokens if kind == "id"}
    short = {}
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    k = 0
    for name in sorted(names, key=lambda n: -sum(t[1] == n for t in tokens)):
        while True:
            candidate = "$" + (letters[k] if k < 52 else f"{letters[k % 52]}{k // 52}")
            k += 1
            if candidate not in taken:
                break
        if len(candidate) < len(name):
            short[name] = candidate
    out = []
    for i, (kind, text, newline) in enumerate(tokens):
        if kind == "id" and text in short and _is_reference(tokens, i):
            text = short[text]
        out.append((kind, text, newline))
    return out


def compact_js(script: str) -> str:
    """A script as small as it can safely be: see the module's docstring.

    Parameters
    ----------
    script : str
        The script, a function expression called at once, as
        :func:`maidr.util.iframe_utils.shiny_frame_script` writes it.

    Returns
    -------
    str
        The same script, smaller.
    """
    return _join(_short_names(_drop_unused(_tokens(script))))


def compact_css(css: str) -> str:
    """A stylesheet without its comments and the white space it does not need.

    And without the quotes round an attribute selector's value that is a
    name. White space goes only around the braces, semicolons, commas and
    child combinators, and after a declaration's colon: a space between two
    selectors is a combinator, and one in ``calc()`` an operator's.

    Parameters
    ----------
    css : str
        The stylesheet.

    Returns
    -------
    str
        The same stylesheet, smaller.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,>])\s*", r"\1", css)
    css = re.sub(r":\s+", ":", css)
    # An attribute selector's value needs no quotes when it is a name.
    css = re.sub(r'="(-?[A-Za-z_][A-Za-z0-9_-]*)"\]', r"=\1]", css)
    return css.replace(";}", "}").strip()


def css_blocks(css: str) -> List[str]:
    """A compacted stylesheet's top-level rules, an ``@media`` block whole.

    Parameters
    ----------
    css : str
        The stylesheet, as :func:`compact_css` returns it.

    Returns
    -------
    list of str
        Its rules, in order.
    """
    blocks, depth, start = [], 0, 0
    for i, char in enumerate(css):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                blocks.append(css[start : i + 1])
                start = i + 1
    return blocks
