import os

# The backend folder this config lives in: ~/csc/current/backend on the server
# (a symlink into ~/csc/releases/<version>/), so a deploy that switches
# `current` and restarts gunicorn runs the new release.
app_path = os.path.dirname(os.path.abspath(__file__))

# Gunicorn configuration
wsgi_app = 'main_fastapi:app'
bind = ':8000'
chdir = app_path
workers = 4
worker_class = 'uvicorn.workers.UvicornWorker'
timeout = 600
loglevel = 'debug'
# logs/ is a symlink to ~/csc/shared/logs, so logs survive deploys
errorlog = os.path.join(app_path, 'logs', 'fastapi.log')
