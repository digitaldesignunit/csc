"""
Logging of the backend (decision 8.157).

Every module logs through ``log = get_logger(__name__)``: a logger under the
common ``csc`` logger. ``configure(settings)`` is called once by each entry
point (the API at its start, each cron script in its ``main``) and sets the
level (``CSC_LOG_LEVEL``) and where the records go:

* in the API under gunicorn, through gunicorn's error-log handler, the daily
  file that keeps 14 days (``gunicorn_logger.py``, ``logrotation.py``);
* otherwise (cron scripts, plain uvicorn in development, tests) to stderr,
  which the cron lines append to their dated ``*_cronjob.<date>.log`` file.

Plain text: time, level, module, message. A line holds counts and ids, never a
user name, an e-mail address or a typed value (decision 8.144 h).
"""

from __future__ import annotations

import logging
import os
import sys

from settings import Settings

ROOT_NAME = 'csc'
FORMAT = '%(asctime)s %(levelname)s %(name)s %(message)s'

_ours = '_csc_handler'


def get_logger(name: str) -> logging.Logger:
    """The logger of a module, below ``csc``; a script run as ``__main__``
    is named after its file."""
    if name == '__main__':
        main = sys.modules.get('__main__')
        path = getattr(main, '__file__', None) or 'main'
        name = os.path.splitext(os.path.basename(path))[0]
    return logging.getLogger(f'{ROOT_NAME}.{name}')


class _ThroughGunicorn(logging.Handler):
    """Hands a record to gunicorn's error-log handlers. Their formatter adds
    gunicorn's own time, process and level, so the record goes in with the
    module name in front of its message (and the traceback after it)."""

    def __init__(self, targets):
        super().__init__()
        self.targets = targets
        self.setFormatter(logging.Formatter('%(name)s %(message)s'))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
            forward = logging.makeLogRecord({
                'name': record.name, 'levelno': record.levelno,
                'levelname': record.levelname, 'msg': text, 'args': None})
            for target in self.targets:
                if forward.levelno >= target.level:
                    target.handle(forward)
        except Exception:                                # noqa: BLE001
            self.handleError(record)


def _gunicorn_handlers():
    return list(logging.getLogger('gunicorn.error').handlers)


def configure(settings: Settings) -> logging.Logger:
    """Set up the ``csc`` logger (idempotent: a second call replaces what the
    first one added)."""
    root = logging.getLogger(ROOT_NAME)
    for handler in list(root.handlers):
        if getattr(handler, _ours, False):
            root.removeHandler(handler)
    targets = _gunicorn_handlers()
    if targets:
        handler: logging.Handler = _ThroughGunicorn(targets)
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(FORMAT))
    setattr(handler, _ours, True)
    root.addHandler(handler)
    root.setLevel(settings.csc_log_level.upper())
    return root
