"""The advice an integration gives when its package cannot be imported."""

from __future__ import annotations

import sys

import pytest

from maidr.widget._extras import missing_extra_error


def _absent(package: str) -> ModuleNotFoundError:
    return ModuleNotFoundError(f"No module named '{package}'", name=package)


def test_an_absent_package_names_the_extra():
    error = missing_extra_error(_absent("shiny"), "shiny", "shiny")
    assert str(error) == (
        "maidr's Shiny integration requires the `shiny` package. "
        'Install it with: pip install "maidr[shiny]"'
    )


def test_the_integration_is_called_by_its_own_name():
    error = missing_extra_error(_absent("mlflow"), "mlflow", "mlflow", name="MLflow")
    assert str(error).startswith("maidr's MLflow integration")


def test_below_the_extras_python_the_package_is_named_to_install_by_hand(
    monkeypatch,
):
    # The extra installs nothing on this Python, so naming it would send the
    # reader to a command that changes nothing.
    monkeypatch.setattr(sys, "version_info", (3, 9, 23, "final", 0))
    error = missing_extra_error(_absent("gradio"), "gradio", "gradio", python=(3, 10))
    assert "only on Python 3.10 or newer" in str(error)
    assert str(error).endswith("pip install gradio")


def test_from_the_extras_python_on_the_extra_is_named(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 10, 0, "final", 0))
    error = missing_extra_error(_absent("gradio"), "gradio", "gradio", python=(3, 10))
    assert str(error).endswith('pip install "maidr[gradio]"')


@pytest.mark.parametrize("python", [None, (3, 10)])
def test_a_broken_install_is_told_apart_from_an_absent_one(python):
    broken = ImportError("cannot import name 'x' from 'gradio.blocks'")
    error = missing_extra_error(broken, "gradio", "gradio", python=python)
    assert "is installed but its imports failed" in str(error)
