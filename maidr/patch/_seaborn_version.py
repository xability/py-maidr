"""Fail understandably when seaborn is older than the patches expect.

Nearly every module in this package wraps a seaborn internal by name, and
the ones under ``_CategoricalPlotter`` and ``_DistributionPlotter``
arrived with the categorical rewrite in seaborn **0.13**.  On an older
seaborn ``wrapt`` cannot resolve the attribute and raises while
``maidr.patch`` is being imported, so ``import maidr`` does not survive::

    AttributeError: type object '_CategoricalPlotter' has no attribute 'plot_bars'

Nothing in that names seaborn, names a version, or suggests what to do,
and it arrives before any of the user's own code runs.  ``pyproject.toml``
declares ``seaborn>=0.13``, so a resolver will not choose 0.12 on its own
-- but `--no-deps`, a conflicting pin elsewhere in the environment, or an
old lockfile all still land there, which is exactly the case #441 was
filed about.

This check does not make an old seaborn work.  It replaces an error that
says nothing with one that says which version is installed, which is
needed, and that the two do not match.
"""

from __future__ import annotations

#: The release that introduced the internals the patches wrap.
MIN_SEABORN = (0, 13)


def _parse(version: str) -> tuple[int, ...]:
    """Return the leading numeric components of a version string.

    Deliberately tolerant: a version this cannot read must not become a
    second, more confusing import failure than the one being replaced.
    """
    parts: list[int] = []
    for chunk in version.split(".")[:2]:
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def check_seaborn_version() -> None:
    """Raise a readable ``ImportError`` on a seaborn the patches cannot wrap.

    Raises
    ------
    ImportError
        If the installed seaborn predates :data:`MIN_SEABORN`.
    """
    try:
        import seaborn
    except ImportError:
        # Not our problem to report: seaborn is a declared dependency, and
        # the import that needs it will say so plainly enough.
        return

    installed = getattr(seaborn, "__version__", "")
    parsed = _parse(installed)
    if not parsed or parsed >= MIN_SEABORN:
        return

    needed = ".".join(str(part) for part in MIN_SEABORN)
    raise ImportError(
        f"maidr requires seaborn >= {needed}, but seaborn {installed} is "
        f"installed. maidr patches seaborn internals that arrived in "
        f"{needed} (the categorical rewrite), so importing it against an "
        f"older seaborn fails while those patches are applied. "
        f"Upgrade with: pip install --upgrade 'seaborn>={needed}'"
    )


__all__ = ["MIN_SEABORN", "check_seaborn_version"]
