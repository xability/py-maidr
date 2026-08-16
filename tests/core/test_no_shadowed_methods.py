"""A class must not define the same method twice.

Python executes a class body top to bottom, so a second ``def`` of the same
name silently replaces the first. Nothing raises, nothing warns, and the tests
go on passing -- because the *live* definition is still correct. What is left
behind is a block of dead code that looks live: a maintainer fixing a bug in
the shadowed copy sees no effect, and blame and diff tooling point at it as
readily as at the real one.

This happened in ``boxenplot.py`` while #438 was in review. Nine methods ended
up defined twice, ~250 lines of the file were unreachable, and the whole suite
stayed green throughout. Eight of the nine pairs were byte-identical, so the
duplication changed nothing -- but the ninth was an *edit* that had been
appended rather than applied, so the version that ran was the one the change
had meant to replace, and a commit message said the opposite.

The check is cheap, reads the whole package, and needs no imports: a duplicate
name in one class body is never intentional.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "maidr"


def shadowed_methods(source: str) -> list[str]:
    """Every ``class.method`` defined more than once in one class body.

    Nested classes are walked too, and only direct children of a class body
    count -- a method and a same-named function defined inside it are not in
    conflict.
    """
    found = []

    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef):
            continue

        names = [
            child.name
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for name in sorted({name for name in names if names.count(name) > 1}):
            found.append(f"{node.name}.{name} (x{names.count(name)})")

    return found


def test_no_class_defines_a_method_twice():
    offenders = []

    for path in sorted(PACKAGE.rglob("*.py")):
        for shadowed in shadowed_methods(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(PACKAGE.parent)}::{shadowed}")

    assert offenders == [], "shadowed method definitions:\n  " + "\n  ".join(offenders)


def test_the_check_can_fail():
    # A guard whose detector is broken is worse than no guard, and this one
    # asserts an empty list -- which is what a detector that never finds
    # anything also produces.
    doubled = """
class Example:
    def read(self):
        return 1

    def read(self):
        return 2
"""

    assert shadowed_methods(doubled) == ["Example.read (x2)"]


def test_a_name_reused_in_a_different_scope_is_not_shadowing():
    # Two classes may each have a `read`, and a closure inside a method may
    # share its name. Neither replaces anything.
    fine = """
class One:
    def read(self):
        def read():
            return 1
        return read()


class Two:
    def read(self):
        return 2
"""

    assert shadowed_methods(fine) == []
