import os
import sys

# The backend folder this config lives in: ~/csc/current/backend on the server
# (a symlink into ~/csc/releases/<version>/), so a deploy that switches
# `current` and restarts gunicorn runs the new release.
app_path = os.path.dirname(os.path.abspath(__file__))
# gunicorn reads this file before it puts the backend folder on the path
if app_path not in sys.path:
    sys.path.insert(0, app_path)


LOG_LEVELS = ('debug', 'info', 'warning', 'error', 'critical')
DEFAULT_WORKERS = 2
MAX_WORKERS = 8


def worker_count(raw=None) -> int:
    """``CSC_WORKERS`` (decision 8.130): a whole number from 1 to 8; two when
    it is unset or not a number. Every worker loads the geometry libraries, so
    the number follows the memory of the account, not the number of cores."""
    text = (os.getenv('CSC_WORKERS') if raw is None else raw) or ''
    try:
        value = int(text.strip())
    except ValueError:
        return DEFAULT_WORKERS
    return min(max(value, 1), MAX_WORKERS)


def log_level(raw=None) -> str:
    """``CSC_LOG_LEVEL`` (decision 8.130): one of gunicorn's levels, ``info``
    when it is unset or unknown."""
    text = ((os.getenv('CSC_LOG_LEVEL') if raw is None else raw) or '')
    text = text.strip().lower()
    return text if text in LOG_LEVELS else 'info'


# The proxies whose X-Forwarded-For is believed: the same list the rate
# limiter reads (``CSC_TRUSTED_PROXIES``, limiter.py), so the server and the
# limits never disagree about who may speak for a client (S12, decision
# 8.144). Default: loopback, where the web server reaches the backend.
DEFAULT_TRUSTED_PROXIES = '127.0.0.0/8,::1'


def trusted_proxies(raw=None) -> str:
    """``CSC_TRUSTED_PROXIES`` as gunicorn's ``forwarded_allow_ips``: comma
    separated addresses and networks, each checked here so that a typo stops
    the start with its name in the message. ``*`` (trust everyone) is refused."""
    import ipaddress
    text = (os.getenv('CSC_TRUSTED_PROXIES') if raw is None else raw) or ''
    entries = []
    for item in (text or DEFAULT_TRUSTED_PROXIES).split(','):
        item = item.strip()
        if not item:
            continue
        try:
            entries.append(str(ipaddress.ip_network(item, strict=False)))
        except ValueError as exc:
            raise ValueError(
                f'CSC_TRUSTED_PROXIES: bad entry {item!r}') from exc
    return ','.join(entries) or DEFAULT_TRUSTED_PROXIES


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
