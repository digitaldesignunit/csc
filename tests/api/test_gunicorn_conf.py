"""``conf.py`` reads the worker count and the log level from the environment
(decision 8.130), with sensible limits."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def conf(env):
    env(CSC_WORKERS=None, CSC_LOG_LEVEL=None, CSC_TRUSTED_PROXIES=None)
    import conf as module
    return importlib.reload(module)


def test_the_defaults_are_two_workers_and_info(conf):
    assert conf.workers == 2 and conf.loglevel == 'info'


def test_the_environment_sets_both(conf, env):
    env(CSC_WORKERS='3', CSC_LOG_LEVEL='WARNING')
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


# S12 (8.144): the trusted proxies of the server and of the limiter are one list --
def test_the_default_trusted_proxies_are_the_limiters_default(conf):
    import limiter
    assert conf.DEFAULT_TRUSTED_PROXIES == limiter.DEFAULT_TRUSTED_PROXIES
    assert conf.forwarded_allow_ips == '127.0.0.0/8,::1/128'


def test_csc_trusted_proxies_sets_forwarded_allow_ips(conf, env):
    env(CSC_TRUSTED_PROXIES='127.0.0.0/8, ::1 ,203.0.113.7')
    module = importlib.reload(conf)
    assert module.forwarded_allow_ips == \
        '127.0.0.0/8,::1/128,203.0.113.7/32'


@pytest.mark.parametrize('raw', ['*', 'not-an-address', '127.0.0.1,,bogus'])
def test_a_bad_entry_stops_the_start_and_names_the_variable(conf, raw):
    with pytest.raises(ValueError, match='CSC_TRUSTED_PROXIES: bad entry'):
        conf.trusted_proxies(raw)


def test_gunicorn_accepts_the_list_and_the_bind_stays(conf, env):
    pytest.importorskip('fcntl')            # gunicorn imports on Unix only
    from gunicorn.config import Config
    env(CSC_TRUSTED_PROXIES='127.0.0.0/8,::1,203.0.113.7')
    module = importlib.reload(conf)
    cfg = Config()
    cfg.set('forwarded_allow_ips', module.forwarded_allow_ips)
    assert cfg.forwarded_allow_ips == ['127.0.0.0/8', '::1/128',
                                       '203.0.113.7/32']
    assert module.bind == ':8000'
