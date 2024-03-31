import os
app_path = os.environ['HOME'] + '/csc/backend'

# Gunicorn configuration
wsgi_app = 'main_fastapi:app'
bind = ':8000'
chdir = app_path
workers = 4
worker_class = 'uvicorn.workers.UvicornWorker'
timeout = 600
loglevel = 'debug'
errorlog = app_path + '/errors.log'
