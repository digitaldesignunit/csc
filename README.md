# CSC - Catalogue of Second Chances

Catalogue of Second Chances - Web Backend & Frontend

## VENV on Uberspace

Activate VENV
```
source venv/bin/activate
```

## FastAPI

- Runs using Gunicorn

```
~/csc/venv/bin/gunicorn --config ~/csc/backend/conf.py --check-config
```

### Supervisor Config

File
```
~/etc/services.d/fastapi.ini
```

Code
```
[program:fastapi]
directory=%(ENV_HOME)s/csc/backend
command=%(ENV_HOME)s/csc/venv/bin/gunicorn --config %(ENV_HOME)s/csc/backend/conf.py --reload
```

## Gunicorn

- Gunicorn runs on Port 8000

## Web Backend

- Demo Web backend is set up on Port 8000
- Web Backend has to be set to the port that the app is listening on!

```
uberspace web backend list
```

```
uberspace web backend del <route>
```


### Specific Path

In this example requests to /ep are routed to an application listening on port 
9000, everything else is handled by apache:

```
uberspace web backend set /ep --http --port 9000
```

### FastAPI Template
```
uberspace web backend set / --http --port 8000
```

```
uberspace web backend set /api --http --port 8000
```

```
uberspace web backend set api.ddu.uber.space --http --port 8000
```

## React

### Supervisor Config

```
[program:react-frontend]
directory=%(ENV_HOME)s/csc/frontend
command=npm run start
autostart=true
autorestart=true
environment=NODE_ENV=production
```

