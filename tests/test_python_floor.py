"""
Every shipped module has to import on the oldest Python we claim.

``pyproject.toml`` sets ``requires-python = ">=3.9"``, and 3.9 evaluates
annotations at definition time. So a bare ``str | None`` in a signature is not
a typing nicety there -- it raises ``TypeError: unsupported operand type(s)
for |`` while the module is being imported, and any module reachable from
``maidr/__init__.py`` takes ``import maidr`` down with it.

That is what happened to ``maidr/util/iframe_utils.py``: written with
``str | None`` and no ``from __future__ import annotations``, it passed every
local run on 3.11 and broke ``import maidr`` outright on 3.9. The CI matrix
caught it, which is the point of the matrix -- but the failure reads as one
job among fifteen rather than as "the package does not import", so it is
worth a test that names it.

The check is on the source rather than on a 3.9 interpreter, because pytest
runs on one version at a time and the fault is only visible on the oldest.
Reading the AST asks the same question on every version.

Out of scope, deliberately: a PEP 604 union used at *runtime* rather than in
an annotation -- ``isinstance(x, int | str)``, ``cast(int | None, v)`` -- is
equally broken on 3.9 and the future import does not save it. Nothing in the
package does that today, and a check for it would have to understand which
call arguments are evaluated as types.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "maidr"

FUTURE_IMPORT = "from __future__ import annotations"


def _modules() -> list[Path]:
    """Every shipped Python module, in a stable order."""
    return sorted(PACKAGE.rglob("*.py"))


def _annotations_of(tree: ast.AST):
    """
    Yield every annotation expression in a module.

    Covers the three places one can appear: a parameter, a return type, and a
    variable or attribute annotation. Parameter coverage includes positional-
    only, keyword-only, ``*args`` and ``**kwargs``, since any one of them
    carrying a union is enough to raise.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in (
                *args.posonlyargs,
                *args.args,
                *args.kwonlyargs,
                args.vararg,
                args.kwarg,
            ):
                if arg is not None and arg.annotation is not None:
                    yield arg.annotation
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            yield node.annotation


def _has_pep604_union(annotation: ast.AST) -> bool:
    """
    Whether an annotation writes a union with ``|``.

    A string annotation is not evaluated at definition time, so
    ``"str | None"`` is safe on 3.9 and is not reported. Walking the whole
    expression rather than checking the top node catches the nested cases --
    ``list[str | None]``, ``dict[str, int | None]`` -- which raise just the
    same.
    """
    for node in ast.walk(annotation):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # A quoted annotation is a string until something resolves it.
            continue
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return True
    return False


def _imports_future_annotations(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "annotations" for alias in node.names):
                return True
    return False


@pytest.mark.parametrize("module", _modules(), ids=lambda p: str(p.name))
def test_a_module_writing_pep604_unions_postpones_its_annotations(module: Path) -> None:
    """
    A ``X | Y`` annotation needs the future import to survive Python 3.9.

    Failing here means the module raises ``TypeError`` on import under 3.9,
    not that it merely fails a type check -- and if anything reachable from
    ``maidr/__init__.py`` imports it, ``import maidr`` raises too.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))

    unions = [a for a in _annotations_of(tree) if _has_pep604_union(a)]
    if not unions:
        return

    assert _imports_future_annotations(tree), (
        f"{module.relative_to(PACKAGE.parent)} writes a PEP 604 union "
        f"(first at line {unions[0].lineno}) without `{FUTURE_IMPORT}`. "
        "Python 3.9 evaluates annotations at definition time, so this raises "
        "TypeError on import."
    )


def test_the_guard_would_notice_the_regression_it_was_written_for() -> None:
    """
    The detector answers yes to the shape that broke, no to the safe ones.

    Without this the guard could pass by never detecting anything -- which is
    how a check for an absent condition usually fails.
    """
    offending = ast.parse("def f(x: str | None = None) -> str: ...")
    assert any(_has_pep604_union(a) for a in _annotations_of(offending))
    assert not _imports_future_annotations(offending)

    nested = ast.parse("def f(x: list[str | None]) -> None: ...")
    assert any(_has_pep604_union(a) for a in _annotations_of(nested))

    returns = ast.parse("def f(x: str) -> str | None: ...")
    assert any(_has_pep604_union(a) for a in _annotations_of(returns))

    variable = ast.parse("x: int | None = None")
    assert any(_has_pep604_union(a) for a in _annotations_of(variable))

    quoted = ast.parse('def f(x: "str | None" = None) -> str: ...')
    assert not any(_has_pep604_union(a) for a in _annotations_of(quoted))

    optional = ast.parse("from typing import Optional\ndef f(x: Optional[str]): ...")
    assert not any(_has_pep604_union(a) for a in _annotations_of(optional))

    guarded = ast.parse(
        "from __future__ import annotations\ndef f(x: str | None = None): ..."
    )
    assert any(_has_pep604_union(a) for a in _annotations_of(guarded))
    assert _imports_future_annotations(guarded)
