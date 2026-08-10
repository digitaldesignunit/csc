# Uberspace Deployment Scripts

These shell scripts deploy the CSC backend and/or frontend on Uberspace from GitHub.

## Classic (build on the server)

- Ensure environment variables in `~/.bash_profile` are set.
- Upload the scripts into `~/csc` (or run from a copy under `uberspaceconfig/deployment`).
- `bash csc_deploy.sh` / `csc_deploy_frontend.sh` / `*_v05.sh` — pull source, run `npm run build` on the host, restart services.

Use these only on hosts new enough for Next.js native SWC (glibc ≥ 2.27).

## CI standalone frontend (recommended on older glibc / Uberspace)

Build happens on GitHub Actions; the server only downloads and runs the bundle.

1. **One-time server setup**
   - Copy `../etc/services.d/frontend_ci.ini.example` to `~/etc/services.d/frontend.ini`
   - `supervisorctl reread && supervisorctl update`
   - Keep `~/csc/frontend/.env` and/or `.env.local` with runtime secrets
     (`MONGODB_URI`, `NEXTAUTH_SECRET`, `NEXTAUTH_URL=https://ddu.uber.space`,
     `MONGODB_DB`, `MONGODB_USERCOLLECTION`, `FASTAPI_URL`, etc.).
     The process must start with `node start-standalone.cjs` (see
     `frontend_ci.ini.example`) so those files are loaded under supervisord.
   - Ensure `GITHUB_REPO_URL` and `GITHUB_CSC_DEPLOY_TOKEN` (or `GITHUB_CSC_GH_TOKEN`) are set
   - Sanity-check after deploy:
     `curl -s http://127.0.0.1:3000/api/auth/session` should return JSON, not HTML
     If the service exits immediately, `supervisorctl tail frontend` will list missing env keys.

2. **CI**
   - Set repo variable `NEXT_PUBLIC_STATIC_BASE_URL` (e.g. `https://public.ddu.uber.space`)
   - Ensure secret `DDU_CSC_GH_RELEASE` can create releases
   - Run workflow **Frontend Standalone Release** (Actions → workflow_dispatch)

3. **Deploy on Uberspace** (from `~/csc` or wherever the script lives)

   ```bash
   bash csc_deploy_frontend_ci.sh                 # latest frontend-* release
   bash csc_deploy_frontend_ci.sh frontend-0.5.0.1  # specific tag
   ```

Existing `csc_deploy_frontend*.sh` scripts are unchanged and still build on the host.
