import os
app_path = os.environ['HOME'] + '/csc/backend'

# Gunicorn configuration
wsgi_app = 'main:app'
bind = ':8000'
chdir = app_path
workers = 4
worker_class = 'uvicorn.workers.UvicornWorker'
errorlog = app_path + '/errors.log'
