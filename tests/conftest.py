"""Shared test helpers: fixture file loading."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def valid_workflows() -> list[Path]:
    return sorted((FIXTURES / "valid").glob("*.yaml"))


@pytest.fixture
def invalid_workflows() -> list[Path]:
    return sorted((FIXTURES / "invalid").glob("*.yaml"))
