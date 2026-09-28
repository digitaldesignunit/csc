# Uberspace Supervisord Services

Two services, both running the active release under `~/csc/current`:

- `fastapi.ini.example` --> `~/etc/services.d/fastapi.ini` (fill in the environment
  variables --- this file holds the backend's secrets and is gitignored)
- `frontend.ini.example` --> `~/etc/services.d/frontend.ini`

After changing them: `supervisorctl reread && supervisorctl update`.
Deploys restart both services themselves (`csc_release_deploy.sh`).
