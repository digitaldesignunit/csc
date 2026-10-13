"""Tests for admin log-file utility routes."""

from __future__ import annotations

from apps.catalog.api import utility as utility_mod


def test_log_routes_are_registered():
    paths = {getattr(route, 'path', None) for route in utility_mod.router.routes}
    assert '/fastapi_log' in paths
    assert '/geometry_log' in paths
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


# S8 (8.144 h): the cron jobs write one dated file a day --------------------
def _logs(tmp_path, monkeypatch, names):
    monkeypatch.setattr(utility_mod, '_BACKEND_DIR', str(tmp_path))
    log_dir = tmp_path / 'logs'
    log_dir.mkdir()
    for name in names:
        (log_dir / name).write_text(f'from {name}\n', encoding='utf-8')


def test_the_cron_log_routes_read_the_newest_dated_file(tmp_path, monkeypatch):
    _logs(tmp_path, monkeypatch, [
        'geometry_cronjob.log',                      # an older crontab's file
        'geometry_cronjob.2026-10-11.log', 'geometry_cronjob.2026-10-13.log',
        'geometry_cronjob.2026-10-12.log',
        'component_map_cronjob.2026-10-09.log',
        'geometry_cronjob.2026-10-14.log.bak', 'other_cronjob.2026-10-20.log'])
    assert utility_mod._latest_dated_log('geometry_cronjob') == \
        'geometry_cronjob.2026-10-13.log'
    assert utility_mod._latest_dated_log('component_map_cronjob') == \
        'component_map_cronjob.2026-10-09.log'
    text = utility_mod._read_last_log_lines(
        utility_mod._latest_dated_log('geometry_cronjob'), 5)
    assert text == 'from geometry_cronjob.2026-10-13.log'


def test_without_a_dated_file_the_undated_name_is_read(tmp_path, monkeypatch):
    _logs(tmp_path, monkeypatch, ['geometry_cronjob.log'])
    assert utility_mod._latest_dated_log('geometry_cronjob') == \
        'geometry_cronjob.log'
    _logs_missing = tmp_path / 'none'
    monkeypatch.setattr(utility_mod, '_BACKEND_DIR', str(_logs_missing))
    assert utility_mod._latest_dated_log('geometry_cronjob') == \
        'geometry_cronjob.log'


def test_a_missing_log_does_not_show_where_the_logs_live(tmp_path, monkeypatch):
    monkeypatch.setattr(utility_mod, '_BACKEND_DIR', str(tmp_path))
    text = utility_mod._read_last_log_lines('missing.log', 10)
    assert str(tmp_path) not in text and 'logs' not in text.replace(
        'missing.log', '')
