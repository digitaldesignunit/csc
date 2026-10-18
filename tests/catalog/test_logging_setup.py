"""Logging of the backend (decision 8.157): one logger per module under
``csc``, the level from CSC_LOG_LEVEL, gunicorn's error log in the API and
stderr elsewhere, and no ``print`` and no direct environment read in the
backend."""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

import pytest

import logging_setup
from settings import Settings

BACKEND = Path(__file__).resolve().parents[2] / 'src' / 'backend'
SKIP_DIRS = {'__pycache__', 'logs', 'static'}


@pytest.fixture(autouse=True)
def clean_logger():
    root = logging.getLogger('csc')
    before = (list(root.handlers), root.level)
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in before[0]:
        root.addHandler(handler)
    root.setLevel(before[1])


def backend_sources():
    for path in sorted(BACKEND.rglob('*.py')):
        if SKIP_DIRS.isdisjoint(path.relative_to(BACKEND).parts):
            yield path, ast.parse(path.read_text(encoding='utf-8'))


# THE LOGGERS -----------------------------------------------------------------
def test_a_module_logs_below_csc():
    assert logging_setup.get_logger('apps.catalog.api.snapshots').name == 'csc.apps.catalog.api.snapshots'
    assert logging_setup.get_logger('__main__').name.startswith('csc.')


def test_the_level_comes_from_the_settings():
    root = logging_setup.configure(Settings(csc_log_level='warning'))
    assert root.level == logging.WARNING
    root = logging_setup.configure(Settings(csc_log_level='DEBUG'))
    assert root.level == logging.DEBUG


def test_configure_twice_leaves_one_handler():
    logging_setup.configure(Settings())
    logging_setup.configure(Settings())
    ours = [h for h in logging.getLogger('csc').handlers if getattr(h, '_csc_handler', False)]
    assert len(ours) == 1


def test_without_gunicorn_the_lines_go_to_stderr_as_time_level_module_message(capsys):
    logging_setup.configure(Settings(csc_log_level='info'))
    logging_setup.get_logger('some.module').warning('three %s', 'users')
    err = capsys.readouterr().err
    assert re.match(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} WARNING csc\.some\.module three users', err)


def test_the_level_filters(capsys):
    logging_setup.configure(Settings(csc_log_level='warning'))
    logging_setup.get_logger('m').info('quiet')
    logging_setup.get_logger('m').error('loud')
    err = capsys.readouterr().err
    assert 'quiet' not in err and 'loud' in err


def test_a_traceback_is_kept_by_log_exception(capsys):
    logging_setup.configure(Settings())
    try:
        raise ValueError('the cause')
    except ValueError:
        logging_setup.get_logger('m').exception('it failed')
    err = capsys.readouterr().err
    assert 'it failed' in err and 'Traceback' in err and 'ValueError: the cause' in err


def test_in_the_api_the_records_go_through_gunicorns_error_log():
    gunicorn = logging.getLogger('gunicorn.error')
    lines = []

    class Collect(logging.Handler):
        def emit(self, record):
            lines.append((record.levelno, record.getMessage()))
    handler = Collect()
    gunicorn.addHandler(handler)
    try:
        logging_setup.configure(Settings())
        logging_setup.get_logger('apps.x').info('hello %d', 3)
        try:
            raise KeyError('k')
        except KeyError:
            logging_setup.get_logger('apps.x').exception('failed')
    finally:
        gunicorn.removeHandler(handler)
    assert lines[0] == (logging.INFO, 'csc.apps.x hello 3')           # the module in front
    assert lines[1][0] == logging.ERROR and lines[1][1].startswith('csc.apps.x failed')
    assert 'KeyError' in lines[1][1]                                  # the traceback follows


# THE BACKEND SOURCES ---------------------------------------------------------
def test_nothing_in_the_backend_prints():
    found = []
    for path, tree in backend_sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'print':
                found.append(f'{path.relative_to(BACKEND)}:{node.lineno}')
    assert not found, found


def test_only_settings_py_reads_the_environment():
    found = []
    for path, tree in backend_sources():
        if path.name == 'settings.py' and path.parent == BACKEND:
            continue
        for node in ast.walk(tree):
            text = ast.unparse(node) if isinstance(node, (ast.Attribute, ast.Name)) else ''
            if text in ('os.environ', 'os.getenv', 'getenv', 'environ'):
                found.append(f'{path.relative_to(BACKEND)}:{node.lineno}')
    assert not found, found
