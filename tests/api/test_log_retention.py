"""The site's own logs keep 14 days (the retention the privacy notice names):
``client_versions.log`` and gunicorn's ``fastapi.log`` rotate at midnight, and
the log line carries no client address and no user name."""

from __future__ import annotations

import logging
import os
import time

import pytest

from apps.catalog import client_header
from logrotation import RETENTION_DAYS, DailyFileHandler


def _record(message: str = 'x') -> logging.LogRecord:
    return logging.LogRecord('t', logging.INFO, __file__, 1, message, (), None)


def _midnight_today() -> int:
    """The start of today: the moment a midnight rollover is due."""
    day = time.strftime('%Y-%m-%d', time.localtime())
    return int(time.mktime(time.strptime(day, '%Y-%m-%d')))


def _dated(directory, base: str, days_ago: range) -> list:
    """Rotated files as the handler names them, ``days_ago`` days old."""
    names = []
    for n in days_ago:
        stamp = time.strftime('%Y-%m-%d', time.localtime(time.time() - n * 86400))
        path = directory / f'{base}.{stamp}'
        path.write_text(f'day -{n}\n', encoding='utf-8')
        names.append(path.name)
    return names


def test_the_retention_is_fourteen_days():
    assert RETENTION_DAYS == 14


def test_the_handler_rotates_at_midnight_and_keeps_fourteen_files(tmp_path):
    log = tmp_path / 'x.log'
    handler = DailyFileHandler(str(log))
    assert handler.when == 'MIDNIGHT'
    assert handler.backupCount == 14
    assert handler.encoding == 'utf-8'
    handler.emit(_record('today'))
    _dated(tmp_path, 'x.log', range(2, 22))        # twenty old days
    handler.rolloverAt = _midnight_today()         # midnight has passed
    handler.doRollover()
    handler.close()
    kept = sorted(p.name for p in tmp_path.iterdir() if p.name != 'x.log')
    assert len(kept) == 14
    # the newest 14 days are kept: 1 to 14 days old (yesterday comes from the current file)
    today = time.strftime('%Y-%m-%d', time.localtime())
    assert not any(name.endswith(today) for name in kept)
    oldest = time.strftime('%Y-%m-%d', time.localtime(time.time() - 15 * 86400))
    assert not any(name.endswith(oldest) for name in kept)


def test_a_rotated_file_is_never_replaced_by_another_process(tmp_path):
    log = tmp_path / 'x.log'
    handler = DailyFileHandler(str(log))
    handler.emit(_record('second process line'))
    handler.rolloverAt = _midnight_today()
    yesterday = time.strftime('%Y-%m-%d', time.localtime(handler.rolloverAt - 1))
    taken = tmp_path / f'x.log.{yesterday}'
    taken.write_text('written by the first process\n', encoding='utf-8')
    handler.doRollover()
    handler.close()
    assert taken.read_text(encoding='utf-8') == 'written by the first process\n'


def test_a_late_rollover_keeps_the_day_file_of_the_first_process(tmp_path):
    # worker A moved the day's file, worker C already wrote a new base file,
    # worker B rolls over afterwards: the day file keeps A's lines and C's
    # new lines stay in the base file
    log = tmp_path / 'x.log'
    handler = DailyFileHandler(str(log))
    handler.rolloverAt = _midnight_today()
    yesterday = time.strftime('%Y-%m-%d', time.localtime(handler.rolloverAt - 1))
    taken = tmp_path / f'x.log.{yesterday}'
    taken.write_text('the whole day, moved by A\n', encoding='utf-8')
    log.write_text('first line of C\n', encoding='utf-8')
    handler.doRollover()
    handler.close()
    assert taken.read_text(encoding='utf-8') == 'the whole day, moved by A\n'
    assert log.read_text(encoding='utf-8') == 'first line of C\n'


def test_the_first_rollover_moves_the_day_file(tmp_path):
    log = tmp_path / 'x.log'
    log.write_text('yesterday\n', encoding='utf-8')
    handler = DailyFileHandler(str(log))
    handler.rolloverAt = _midnight_today()
    yesterday = time.strftime('%Y-%m-%d', time.localtime(handler.rolloverAt - 1))
    handler.doRollover()
    handler.close()
    assert (tmp_path / f'x.log.{yesterday}').read_text(encoding='utf-8') \
        == 'yesterday\n'
    assert not log.exists() or log.read_text(encoding='utf-8') == ''


def test_the_handler_writes_utf8_and_starts_a_new_file_after_rollover(tmp_path):
    log = tmp_path / 'x.log'
    handler = DailyFileHandler(str(log))
    handler.setFormatter(logging.Formatter('%(message)s'))
    handler.emit(_record('caf\u00e9'))
    handler.rolloverAt = int(time.time()) - 5
    handler.emit(_record('next day'))              # emit rolls over first
    handler.close()
    assert log.read_text(encoding='utf-8') == 'next day\n'
    rotated = [p for p in tmp_path.iterdir() if p.name != 'x.log']
    assert len(rotated) == 1
    assert rotated[0].read_text(encoding='utf-8') == 'caf\u00e9\n'


def test_the_client_log_uses_the_daily_handler(tmp_path):
    path = tmp_path / 'logs' / 'client_versions.log'
    logger = client_header.client_logger
    before = list(logger.handlers)
    try:
        client_header.configure_client_log(str(path))
        added = [h for h in logger.handlers if h not in before]
        assert len(added) == 1 and isinstance(added[0], DailyFileHandler)
        assert added[0].backupCount == RETENTION_DAYS
        client_header.configure_client_log(str(path))   # idempotent
        assert len([h for h in logger.handlers if h not in before]) == 1
    finally:
        for handler in list(logger.handlers):
            if handler not in before:
                handler.close()
                logger.removeHandler(handler)


def test_the_client_log_line_holds_no_address_and_no_user_name():
    line = client_header.describe_client(None, 'Mozilla/5.0 (X11)')
    assert line.startswith('client=unknown agent=')
    assert 'ip' not in line.split('agent=')[0]
    assert client_header.describe_client('web/0.6.1.0', 'ua') == 'client=web version=0.6.1.0'


def test_gunicorns_error_log_is_the_daily_file(tmp_path, monkeypatch):
    # gunicorn needs fcntl: it does not import (and does not run) on Windows
    pytest.importorskip('fcntl')
    from gunicorn.config import Config

    import conf
    from gunicorn_logger import DailyLogger
    cfg = Config()
    cfg.set('errorlog', str(tmp_path / 'fastapi.log'))
    cfg.set('logger_class', conf.logger_class)
    assert cfg.logger_class is DailyLogger
    logger = cfg.logger_class(cfg)
    try:
        handlers = [h for h in logger.error_log.handlers if getattr(h, '_gunicorn', False)]
        assert len(handlers) == 1
        assert isinstance(handlers[0], DailyFileHandler)
        assert handlers[0].backupCount == 14
        logger.error('a line')
        handlers[0].flush()
        assert 'a line' in (tmp_path / 'fastapi.log').read_text(encoding='utf-8')
        # the access log stays off: it would hold client addresses
        assert cfg.accesslog is None and not hasattr(conf, 'accesslog')
        # setup again (a configuration reload) does not stack handlers
        logger.setup(cfg)
        assert len([h for h in logger.error_log.handlers if getattr(h, '_gunicorn', False)]) == 1
    finally:
        for handler in list(logger.error_log.handlers):
            if getattr(handler, '_gunicorn', False):
                handler.close()
                logger.error_log.removeHandler(handler)


def test_conf_names_the_daily_logger_without_importing_gunicorn():
    import conf
    assert conf.logger_class == 'gunicorn_logger.DailyLogger'
    assert conf.errorlog.endswith('fastapi.log')


def test_the_stdout_prints_of_the_auth_routes_name_no_e_mail_address():
    source = open(os.path.join(os.path.dirname(__file__), '..', '..', 'src',
                               'backend', 'apps', 'catalog', 'api', 'auth.py'),
                  encoding='utf-8').read()
    for line in source.splitlines():
        if 'print(' in line:
            assert 'email}' not in line and '"email")' not in line, line
            assert 'username' not in line, line
