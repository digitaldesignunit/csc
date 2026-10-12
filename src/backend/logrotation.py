"""
Daily log files that keep 14 days (the retention the privacy notice names).

``DailyFileHandler`` rotates at midnight and deletes what is older than
``RETENTION_DAYS`` files. Several processes (the gunicorn workers) write the
same log, so the rotation is made safe for that: a day's file that already
exists is never replaced, only the first process to roll over renames the
current file, and the others reopen it. Stdlib only, so ``conf.py`` can use it
before the application is imported.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
from typing import Any

RETENTION_DAYS = 14


class DailyFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Midnight rotation, ``backupCount`` dated files, UTF-8."""

    def __init__(self, filename: str, backup_count: int = RETENTION_DAYS,
                 **kwargs: Any):
        kwargs.setdefault('encoding', 'utf-8')
        kwargs.setdefault('delay', True)
        super().__init__(filename, when='midnight', backupCount=backup_count,
                         **kwargs)

    def _move_day(self, target: str) -> None:
        if self.rotator is None and hasattr(os, 'link'):
            try:
                os.link(self.baseFilename, target)
            except FileExistsError:
                return                      # another process was first
            except OSError as exc:
                print(f'[LOG] rotate {self.baseFilename}: {exc}',
                      file=sys.stderr)
            else:
                try:
                    if os.stat(self.baseFilename).st_ino \
                            == os.stat(target).st_ino:
                        os.remove(self.baseFilename)
                except OSError as exc:
                    print(f'[LOG] rotate {self.baseFilename}: {exc}',
                          file=sys.stderr)
                return
        if os.path.exists(target):
            return
        try:                                # no hard links: rename
            self.rotate(self.baseFilename, target)
        except OSError as exc:
            print(f'[LOG] rotate {self.baseFilename}: {exc}', file=sys.stderr)

    def doRollover(self) -> None:           # noqa: N802 (stdlib name)
        if self.stream:
            self.stream.close()
            self.stream = None              # type: ignore[assignment]
        now = int(time.time())
        # the file holds the day that has just ended
        day = time.localtime(self.rolloverAt - 1)
        target = self.rotation_filename(
            f'{self.baseFilename}.{time.strftime(self.suffix, day)}')
        # another process may have rotated already: never replace its file.
        # A hard link fails when the target exists, so of several workers
        # rolling over at once only the first one moves the day's file; the
        # base is removed only if it is still the inode that was linked
        if os.path.exists(self.baseFilename):
            self._move_day(target)
        if self.backupCount > 0:
            for old in self.getFilesToDelete():
                try:
                    os.remove(old)
                except OSError:
                    pass
        if not self.delay:
            self.stream = self._open()
        next_at = self.computeRollover(now)
        while next_at <= now:
            next_at += self.interval
        self.rolloverAt = next_at
