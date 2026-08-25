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
     (`MONGODB_URI`, `NEXTAUTH_SECRET`, `NEXTAUTH_URL=https://2ndchances.build`,
     `MONGODB_DB`, `MONGODB_USERCOLLECTION`, `FASTAPI_URL`, etc.).
     The process must start with `node start-standalone.cjs` (see
     `frontend_ci.ini.example`) so those files are loaded under supervisord.
   - Ensure `GITHUB_REPO_URL` and `GITHUB_CSC_DEPLOY_TOKEN` (or `GITHUB_CSC_GH_TOKEN`) are set
   - Sanity-check after deploy:
     `curl -s http://127.0.0.1:3000/api/auth/session` should return JSON, not HTML
     If the service exits immediately, `supervisorctl tail frontend` will list missing env keys.

2. **CI**
   - Set repo variable `NEXT_PUBLIC_STATIC_BASE_URL` (e.g. `https://public.2ndchances.build`)
   - No release secret needed: the workflow's built-in `GITHUB_TOKEN` creates the
     release via its `permissions: contents: write` grant
   - Run workflow **Frontend Standalone Release** (Actions → workflow_dispatch)

### Build-time vs runtime configuration

Since the build moved to CI, this distinction matters:

| Kind | Where it must be set | Examples |
| --- | --- | --- |
| Build time (compiled into the client bundle) | GitHub repo variable / workflow input | `NEXT_PUBLIC_*` |
| Runtime (read per request on the server) | `~/csc/frontend/.env` | `NEXTAUTH_SECRET`, `MONGODB_*`, `FASTAPI_URL`, `BETA_PHASE`, `BETA_BANNER_TEXT`, `BETA_LOGIN_MESSAGE`, `GH_INTERFACE_DEACTIVATED` |

Setting a `NEXT_PUBLIC_*` value in the server `.env` has no effect — it is baked in
during `next build`. Conversely, the beta/gh-interface flags stay editable on the
server: the root layout is `force-dynamic`, so changing `.env` plus
`supervisorctl restart frontend` is enough, no rebuild needed.

Note that `NEXT_PUBLIC_STATIC_BASE_URL` only applies to Apache-hosted catalog assets.
Assets bundled in `public/` (`/logo/`, `/gh-interface/`, `/backgroundmeshes/`) are
deliberately kept on the app origin by `resolveStatic()`.

3. **Deploy on Uberspace** (from `~/csc` or wherever the script lives)

   ```bash
   bash csc_deploy_frontend_ci.sh                 # latest frontend-* release
   bash csc_deploy_frontend_ci.sh frontend-0.5.0.1  # specific tag
   ```

Existing `csc_deploy_frontend*.sh` scripts are unchanged and still build on the host.
