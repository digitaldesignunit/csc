"""
The read-only flag (decision 8.154): a file switch for maintenance.

While the file ``CSC_READ_ONLY_FLAG`` names (default ``~/csc/shared/READ_ONLY``)
exists, the API refuses every request other than GET, HEAD and OPTIONS (the
middleware in ``apps/catalog/read_only_middleware.py``), sign-in writes
nothing, and the cron jobs that write (geometry runner, component map, user
clean-up) skip their run. The file is looked at on every call, with no cache:
``touch`` and ``rm`` switch every gunicorn worker and every job at once, with
no restart. An environment variable would need a restart and could leave
workers disagreeing.

Stdlib and settings only, so the jobs can import it.
"""

import os
from typing import Optional

from settings import Settings, get_settings

DETAIL = 'read-only: maintenance'
RETRY_AFTER_SECONDS = 120


def flag_path(settings: Optional[Settings] = None) -> str:
    return (settings or get_settings()).csc_read_only_flag


def is_on() -> bool:
    """Whether the file exists now. A path that cannot be read (a missing
    folder, no permission) counts as off: the switch is the file's existence.
    No parameter on purpose: slowapi passes the request to an ``exempt_when``
    function that takes one."""
    try:
        return os.path.exists(flag_path())
    except (OSError, ValueError):
        return False


def skip_job(log_line, job: str, dry_run: bool = False) -> bool:
    """True, after one log line, when a job that writes must not run: the flag
    is set. A dry run writes nothing and goes on."""
    if dry_run or not is_on():
        return False
    log_line(f'{job}: skipped, the read-only flag is set ({flag_path()})')
    return True
