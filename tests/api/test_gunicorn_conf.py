"""``conf.py`` reads the worker count and the log level from the environment
(decision 8.130), with sensible limits."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def conf(monkeypatch):
    monkeypatch.delenv('CSC_WORKERS', raising=False)
    monkeypatch.delenv('CSC_LOG_LEVEL', raising=False)
    import conf as module
    return importlib.reload(module)


def test_the_defaults_are_two_workers_and_info(conf):
    assert conf.workers == 2 and conf.loglevel == 'info'


def test_the_environment_sets_both(conf, monkeypatch):
    monkeypatch.setenv('CSC_WORKERS', '3')
    monkeypatch.setenv('CSC_LOG_LEVEL', 'WARNING')
    module = importlib.reload(conf)
    assert module.workers == 3 and module.loglevel == 'warning'


@pytest.mark.parametrize('raw, expected', [
    ('1', 1), (' 4 ', 4), ('8', 8), ('0', 1), ('-3', 1), ('64', 8),
    ('', 2), ('two', 2), ('2.5', 2), (None, 2)])
def test_the_worker_count_is_a_whole_number_within_limits(conf, raw, expected):
    assert conf.worker_count(raw if raw is not None else '') == expected


@pytest.mark.parametrize('raw, expected', [
    ('debug', 'debug'), ('Error', 'error'), (' critical ', 'critical'),
    ('verbose', 'info'), ('trace', 'info'), ('', 'info')])
def test_the_log_level_is_one_of_gunicorns_or_info(conf, raw, expected):
    assert conf.log_level(raw) == expected
