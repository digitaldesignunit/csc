# CSC - Catalogue of Second Chances

Catalogue of Second Chances - Web Backend & Frontend

## VENV on Uberspace

Activate VENV
```
source venv/bin/activate
```

## FastAPI

- Runs using Gunicorn on port 8000

```
~/csc/venv/bin/gunicorn --config ~/csc/backend/conf.py --check-config
```

### Supervisor Config

Create a `services.d` file...
```
nano ~/etc/services.d/fastapi.ini
```

...with the following content:
```
[program:fastapi]
directory=%(ENV_HOME)s/csc/backend
command=%(ENV_HOME)s/csc/venv/bin/gunicorn --config %(ENV_HOME)s/csc/backend/conf.py --reload
```

### Web Backend

- Gunicorn runs the FastAPI backend on Port 8000
- Backend is set up on Port 8000
- Web Backend has to be set to the port that the app is listening on!

Web Backend usage and settings:
```
uberspace web backend list
uberspace web backend del <route>
uberspace web backend set <route>
```

For our backend we will set api.uber.space to port 8000 (where gunicorn is
listening!)
```
uberspace web backend set api.ddu.uber.space --http --port 8000
```

## Frontend with Next.js

### NEXT.js

#### Update NPM

```
npm install -g npm
```

#### Create new Project

```
npx create-next-app@latest frontend --use-npm --example "https://github.com/vercel/next-learn/tree/main/dashboard/starter-example"
```

#### Create `-env-local` file

Create .env.local file in `/frontend` directory, containing the following
API environment variables:

```
API_TOKEN_URL=https://your.api.path.com/token
API_USER=YourAuthUserName
API_PASS=YourAuthUserPassword
API_SECRET=JWTSecretShouldGoHere
API_TOKEN_TIMEOUT_MINS=59
API_TOKEN=
API_TOKENTIME=
```

### Supervisor Config

```
[program:frontend]
directory=%(ENV_HOME)s/csc/frontend
command=npm run start
autostart=true
autorestart=true
environment=NODE_ENV=production
```
