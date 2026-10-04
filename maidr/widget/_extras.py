"""Shared error reporting for the optional framework extras.

Every framework integration imports a package maidr does not depend on, so
each has the same two failure modes to tell apart -- and the same reason to
bother: the advice differs.
"""

from __future__ import annotations

import sys


def missing_extra_error(
    error: ImportError,
    package: str,
    extra: str,
    *,
    name: str | None = None,
    python: tuple[int, int] | None = None,
) -> ImportError:
    """Return an :class:`ImportError` whose advice matches the failure.

    Two things arrive as an ``ImportError`` here and they need opposite
    answers.  The package may be absent, in which case installing the extra
    is the fix.  Or it may be installed and its own import chain broken --
    a version skew with a transitive dependency raises ``ImportError`` for
    a missing *name*, and telling someone in that state to install the
    extra sends them to reinstall a package they already have.

    Parameters
    ----------
    error : ImportError
        The original failure.
    package : str
        Top-level package the integration needs, e.g. ``"shiny"``.
    extra : str
        Name of the optional extra that provides it.
    name : str, optional
        What the integration is called, such as ``"MLflow"``. By default
        ``extra`` in title case.
    python : tuple of (int, int), optional
        The oldest Python the extra installs the package on. On an older
        one the extra installs nothing, so the advice names the package to
        install by hand instead.

    Returns
    -------
    ImportError
        To be raised ``from`` the original.

    Examples
    --------
    >>> try:
    ...     import shiny
    ... except ImportError as error:
    ...     raise missing_extra_error(error, "shiny", "shiny") from error
    """
    absent = isinstance(error, ModuleNotFoundError) and (
        error.name or ""
    ).partition(".")[0] == package

    name = name or extra.title()
    if absent and python is not None and sys.version_info[:2] < python:
        oldest = ".".join(map(str, python))
        return ImportError(
            f"maidr's {name} integration requires the `{package}` package. "
            f'The "maidr[{extra}]" extra installs it only on Python {oldest} '
            f"or newer; on this Python, install it yourself: pip install {package}"
        )
    if absent:
        return ImportError(
            f"maidr's {name} integration requires the `{package}` "
            f'package. Install it with: pip install "maidr[{extra}]"'
        )

    return ImportError(
        f"maidr's {name} integration could not import `{package}`. "
        "The package is installed but its imports failed, which usually "
        "means a version skew with one of its dependencies; try "
        f'pip install --upgrade "maidr[{extra}]". Original error: {error}'
    )
