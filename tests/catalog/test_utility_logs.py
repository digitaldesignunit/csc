"""Tests for admin log-file utility routes."""

from __future__ import annotations

from apps.catalog.api import utility as utility_mod


def test_log_routes_are_registered():
    paths = {getattr(route, 'path', None) for route in utility_mod.router.routes}
    assert '/fastapi_log' in paths
    assert '/previewgen_log' in paths
    assert '/descriptors_simple_log' in paths
    assert '/component_map_log' in paths


def test_read_last_log_lines_returns_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(utility_mod, '_BACKEND_DIR', str(tmp_path))
    log_dir = tmp_path / 'logs'
    log_dir.mkdir()
    (log_dir / 'fastapi.log').write_text('a\nb\nc\n', encoding='utf-8')
    assert utility_mod._read_last_log_lines('fastapi.log', 2) == 'b\nc'


def test_read_last_log_lines_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(utility_mod, '_BACKEND_DIR', str(tmp_path))
    text = utility_mod._read_last_log_lines('missing.log', 10)
    assert 'No missing.log file found' in text
