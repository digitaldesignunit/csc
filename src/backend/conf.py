import os
import sys

# The backend folder this config lives in: ~/csc/current/backend on the server
# (a symlink into ~/csc/releases/<version>/), so a deploy that switches
# `current` and restarts gunicorn runs the new release.
app_path = os.path.dirname(os.path.abspath(__file__))
# gunicorn reads this file before it puts the backend folder on the path
if app_path not in sys.path:
    sys.path.insert(0, app_path)


# The values come from settings.py (decision 8.156): the same class the
# application reads, so gunicorn and the app never disagree. The two helpers
# keep their form for a raw text (tests, tools).
import settings as _settings  # noqa: E402
from settings import (  # noqa: E402,F401
    DEFAULT_TRUSTED_PROXIES,
    DEFAULT_WORKERS,
    LOG_LEVELS,
    MAX_WORKERS,
)


def worker_count(raw=None) -> int:
    """``CSC_WORKERS`` (decision 8.130): a whole number from 1 to 8; two when
    it is unset or not a number. Every worker loads the geometry libraries, so
    the number follows the memory of the account, not the number of cores."""
    if raw is None:
        return _settings.get_settings().csc_workers
    return _settings.worker_count(raw)


def log_level(raw=None) -> str:
    """``CSC_LOG_LEVEL`` (decision 8.130): one of gunicorn's levels, ``info``
    when it is unset or unknown."""
    if raw is None:
        return _settings.get_settings().csc_log_level
    return _settings.log_level(raw)


# The proxies whose X-Forwarded-For is believed: the same list the rate
# limiter reads (``CSC_TRUSTED_PROXIES``, limiter.py), so the server and the
# limits never disagree about who may speak for a client (S12, decision
# 8.144). Default: loopback, where the web server reaches the backend.


def trusted_proxies(raw=None) -> str:
    """``CSC_TRUSTED_PROXIES`` as gunicorn's ``forwarded_allow_ips``: comma
    separated addresses and networks, each checked so that a typo stops the
    start with its name in the message. ``*`` (trust everyone) is refused."""
    text = (_settings.get_settings().csc_trusted_proxies
            if raw is None else raw) or ''
    networks = _settings.parse_trusted_proxies(text or DEFAULT_TRUSTED_PROXIES)
    return ','.join(str(n) for n in networks) or DEFAULT_TRUSTED_PROXIES


# Gunicorn configuration. The two settings come from the environment
# (fastapi.ini), so a deploy no longer resets them.
wsgi_app = 'main_fastapi:app'
# the Uberspace web backend connects to :8000 (all interfaces), so the bind stays
bind = ':8000'
forwarded_allow_ips = trusted_proxies()
chdir = app_path
workers = worker_count()
worker_class = 'uvicorn.workers.UvicornWorker'
timeout = 600
loglevel = log_level()
# logs/ is a symlink to ~/csc/shared/logs, so logs survive deploys
errorlog = os.path.join(app_path, 'logs', 'fastapi.log')
# a daily file that keeps 14 days (gunicorn_logger.py); no accesslog: it would
# hold client addresses
logger_class = 'gunicorn_logger.DailyLogger'
