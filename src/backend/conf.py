import os

# The backend folder this config lives in: ~/csc/current/backend on the server
# (a symlink into ~/csc/releases/<version>/), so a deploy that switches
# `current` and restarts gunicorn runs the new release.
app_path = os.path.dirname(os.path.abspath(__file__))

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


# Gunicorn configuration. The two settings come from the environment
# (fastapi.ini), so a deploy no longer resets them.
wsgi_app = 'main_fastapi:app'
bind = ':8000'
chdir = app_path
workers = worker_count()
worker_class = 'uvicorn.workers.UvicornWorker'
timeout = 600
loglevel = log_level()
# logs/ is a symlink to ~/csc/shared/logs, so logs survive deploys
errorlog = os.path.join(app_path, 'logs', 'fastapi.log')
