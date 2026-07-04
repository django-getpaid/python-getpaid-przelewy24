"""Tests for the public package API."""

import re
import tomllib
from importlib.metadata import version
from pathlib import Path

import getpaid_przelewy24


def test_version() -> None:
    """__version__ must be a valid PEP 440-ish version and match
    the installed distribution metadata — no hardcoded literals."""
    assert re.fullmatch(
        r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?",
        getpaid_przelewy24.__version__,
    )
    assert getpaid_przelewy24.__version__ == version(
        "python-getpaid-przelewy24"
    )


def test_core_dependency_floor() -> None:
    """Core floor must be >=3.1.0 — ChargeResult and AutoName only
    exist from core 3.1.0 on."""
    pyproject_data = tomllib.loads(Path("pyproject.toml").read_text())
    assert (
        "python-getpaid-core>=3.1.0"
        in pyproject_data["project"]["dependencies"]
    )
