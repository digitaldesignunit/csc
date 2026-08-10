# Uberspace Supervisord Services

- Copy `fastapi.ini.example` and rename it to `fastapi.ini`
- Set your environment variables
- Create supervisord services for fastapi and frontend using the SSH shell
- For CI-built frontend deploys (no `next build` on the host), use
  `frontend_ci.ini.example` as `frontend.ini` so the process runs `node server.js`