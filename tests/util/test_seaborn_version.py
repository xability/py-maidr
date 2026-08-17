"""An unsupported seaborn must say so, not raise from inside wrapt (#441).

The patches wrap seaborn internals by name, and the ones under
``_CategoricalPlotter`` arrived in 0.13. On an older seaborn the failure
used to be::

    AttributeError: type object '_CategoricalPlotter' has no attribute 'plot_bars'

raised while ``maidr.patch`` was being imported -- so before any of the
user's own code ran, naming neither seaborn nor a version.

Reproduced against a real seaborn 0.12.2 before this check existed; these
tests drive the check itself, since the suite runs on a supported seaborn
and cannot install an unsupported one to prove it.
"""

from __future__ import annotations

import types

import pytest

from maidr.patch._seaborn_version import (
    MIN_SEABORN,
    _parse,
    check_seaborn_version,
)


class TestParsingAVersion:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("0.13.2", (0, 13)),
            ("0.12.2", (0, 12)),
            ("1.0", (1, 0)),
            ("0.14.0.dev0", (0, 14)),
            ("0.13.2rc1", (0, 13)),
        ],
    )
    def test_it_reads_the_leading_numbers(self, text, expected):
        assert _parse(text) == expected

    @pytest.mark.parametrize("text", ["", "unknown", "v0.13"])
    def test_an_unreadable_version_yields_nothing(self, text):
        """Tolerated rather than guessed at.

        A version string this cannot read must not become a second, more
        confusing import failure than the one being replaced -- so it
        parses to nothing and the check lets the import proceed.
        """
        assert _parse(text) == ()


class TestTheCheck:
    @staticmethod
    def _with_seaborn(monkeypatch, version):
        module = types.ModuleType("seaborn")
        if version is not None:
            module.__version__ = version
        monkeypatch.setitem(__import__("sys").modules, "seaborn", module)

    def test_a_supported_seaborn_passes(self, monkeypatch):
        self._with_seaborn(monkeypatch, "0.13.2")
        check_seaborn_version()

    def test_a_newer_seaborn_passes(self, monkeypatch):
        self._with_seaborn(monkeypatch, "0.14.0")
        check_seaborn_version()

    def test_an_old_seaborn_raises(self, monkeypatch):
        self._with_seaborn(monkeypatch, "0.12.2")
        with pytest.raises(ImportError) as raised:
            check_seaborn_version()

        message = str(raised.value)
        # What is installed, what is needed, and how to fix it -- the three
        # things the AttributeError this replaces did not say.
        assert "0.12.2" in message
        assert "0.13" in message
        assert "pip install" in message
        assert "seaborn" in message

    def test_an_unreadable_version_is_allowed_through(self, monkeypatch):
        """Better a later, specific failure than a wrong early one.

        Refusing to import on a version string we merely failed to parse
        would break installs that work.
        """
        self._with_seaborn(monkeypatch, "not-a-version")
        check_seaborn_version()

    def test_a_seaborn_with_no_version_attribute_is_allowed_through(
        self, monkeypatch
    ):
        self._with_seaborn(monkeypatch, None)
        check_seaborn_version()


def test_the_floor_matches_what_the_package_declares():
    """The check and `pyproject.toml` have to agree.

    Two floors that drift apart give the worst of both: a resolver that
    installs a version the code then refuses, or the reverse.
    """
    import pathlib
    import re

    text = (pathlib.Path(__file__).parents[2] / "pyproject.toml").read_text()
    declared = set(re.findall(r'"seaborn>=([0-9.]+)"', text))

    expected = ".".join(str(part) for part in MIN_SEABORN)
    assert declared == {expected}, (
        f"pyproject declares seaborn floors {sorted(declared)}; the import "
        f"check enforces {expected}"
    )
