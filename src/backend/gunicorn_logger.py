"""
Gunicorn's logger with a daily ``errorlog`` that keeps 14 days (the retention
the privacy notice names) instead of one file that only grows. ``conf.py``
names it as ``logger_class``; gunicorn imports it, so this module needs
gunicorn (it does not import on Windows, where gunicorn does not run).
"""

from __future__ import annotations

from gunicorn.glogging import Logger

from logrotation import RETENTION_DAYS, DailyFileHandler


class DailyLogger(Logger):
    def _set_handler(self, log, output, fmt, stream=None):
        if output is None or output == '-':
            return super()._set_handler(log, output, fmt, stream)
        handler = self._get_gunicorn_handler(log)
        if handler:
            log.removeHandler(handler)
        new = DailyFileHandler(output, backup_count=RETENTION_DAYS)
        new.setFormatter(fmt)
        new._gunicorn = True
        log.addHandler(new)
