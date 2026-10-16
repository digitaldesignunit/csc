"""Pytest configuration for repository-wide tests."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1] / 'src' / 'backend'
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_settings():
    """The settings are read once per process (decision 8.156): every test
    starts, and ends, with a new read of the environment."""
    from settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def env(monkeypatch):
    """Set (a text) or remove (None) environment variables and read the
    settings again: ``env(CSC_WORKERS='3', SMTP_HOST=None)``."""
    from settings import get_settings

    def apply(**values):
        for key, value in values.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        get_settings.cache_clear()
    return apply
