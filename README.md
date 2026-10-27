# CSC - Catalog of Second Chances

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20156666.svg)](https://doi.org/10.5281/zenodo.20156666)

The _Catalog of Second Chances (CSC)_ is a prototypical digital component database.
It catalogs digital representations of uniquely identifiable architectural components
for reuse. Furthermore, it provides corresponding interfaces and tools to leverage
them via a backend REST-API, a web-frontend as well as a interface for direct
interaction within Rhino Grasshopper.

## Prerequisites

- This is research level code! As always: expect bugs, weird behaviour, things
not working, etc. pp.
- This is a proof-of-concept / prototype. Things will change (and break) all the time.

## Software Structure

- The Catalog consists of a _database_, _backend_, _frontend_, and _Grasshopper interface_
- We use [_MongoDB Atlas_](https://www.mongodb.com/) as database
- The backend is implemented using [_FastAPI_](https://fastapi.tiangolo.com/)
- We use Python 3.13 (see `src/backend/constraints.txt` for the server's package caps)
- The frontend is implemented using the [_Next.JS_](https://nextjs.org/)
framework
- The frontend is designed to connect to the backend on the same server using JWT-based auth
- Grasshopper interface provides Python 3 components for direct integration with Rhino/Grasshopper
- Everything runs on a web server, in our case we use
[_Uberspace_](https://uberspace.de/)

## Current Versions

- **CSC**: 0.6.4.1 --- backend, web frontend and Grasshopper interface are released together
  under one version (tag `v0.6.4.1`); the single source is the `VERSION` file.

See `CHANGELOG.md` for release notes.

---

## Local development and tests

A complete local setup --- MongoDB, FastAPI backend, Next.js frontend, test
suite --- that never touches production. Commands are for PowerShell on Windows;
run them from the repository root unless stated otherwise.

### One-time setup

1. **MongoDB Community Server** (runs as the Windows service `MongoDB` on port
   27017 and starts with Windows):

   ```
   winget install --id MongoDB.Server --source winget
   Get-Service MongoDB          # Status should be Running
   ```

   The tests start their own throwaway `mongod` from this installation; set
   `MONGOD_BIN` only if it lives outside `C:\Program Files\MongoDB\Server\`.

2. **Python environment** (Python 3.13; backend packages at production
   versions, test tools, local tools):

   ```
   conda env create -f csc_env.yml      # creates the env "csc"
   conda activate csc
   ```

   If an older `csc` env exists, remove it first (`conda env remove -n csc`).
   Don't `conda rename` an env: pip's `.exe` launchers (`invoke`, `pytest`, ...)
   keep the old path and fail with "Fatal error in launcher". After `csc_env.yml` or the
   requirements change: `conda env update -n csc -f csc_env.yml` (it adds and
   upgrades; to drop packages, recreate the env).

3. **Backend settings**: copy `src/backend/dev.env.example` to
   `src/backend/dev.env` (gitignored). To see meshes, previews and photos, point
   the `SNAPSHOT_*_DIR` entries at a copy of the production assets.

4. **Frontend settings**: copy `src/frontend/.env.development.local.example` to
   `src/frontend/.env.development.local` (gitignored). `npm run dev` loads it
   last, so `.env` / `.env.local` can keep production values. Then install:

   ```
   cd src/frontend
   npm install
   ```

5. **Local data and an account**:

   ```
   invoke seed --dump 260916            # loads mongodb_collections_local/260916 into the local "csc" database
   invoke create-user --username me --email me@example.org --admin    # prompts for a password
   ```

   `invoke seed --dump 260916 --replace` reloads a dump over existing data.

### Running it (two terminals, env `csc` active)

| terminal | command | serves |
|---|---|---|
| 1 | `invoke dev-backend` | FastAPI on http://127.0.0.1:8000 (API docs at `/docs`), auto-reload |
| 2 | `cd src/frontend` then `npm run dev` | web app on http://localhost:3000 --- log in with the account from step 5 |

MongoDB needs no terminal: it is the Windows service. The Grasshopper
UserObjects talk to production by default; to use a local backend, set the `Server` input of
`CSC_Session` (e.g. `localhost:8000`; a host without a scheme becomes `http://` for localhost, else
`https://`). Changing it signs you out and clears the cache.

For browser checks open the web app as `http://127.0.0.1:<port>`, not
`localhost`: cookies do not separate by port, so a second dev server on another
port (a throwaway `invoke dev-local` with `NEXT_DIST_DIR` and
`NEXTAUTH_URL=http://127.0.0.1:<port>`) would otherwise share its NextAuth
session with the first.

**A local copy of the newest dump** (for checking the web app against real
data) starts from `.claude/launch.json`: `backend-local` (the newest
`mongodb_collections_local/<yymmdd>` folder, a throwaway `mongod` on 27791, the
backend on http://127.0.0.1:8791, assets copied to `.dev/assets-261012`) and
`frontend-local` (http://localhost:3000). Both run through
`scripts/dev/run_csc_python.cmd`, which finds the conda environment `csc`
without a path of your account: `CSC_PYTHON` (a `python.exe` you name), the
active environment when it is `csc`, the conda base from `CONDA_EXE`, the usual
install folders under `%USERPROFILE%` and `%ProgramData%`, then `conda run -n
csc`. The sign-in `dev-admin` has a new password at every start, written to
`.dev/dev-local-credentials-8791.txt`. The script is `scripts/dev/serve_dump.py`
(`invoke dev-local` runs it too); it loads a dump as it is, and `--migrate`
runs the 0.6 cutover steps on an old 0.5 dump. A collection with no export file in
the dump is not loaded, and an export file of 0 bytes holds no documents.

### Tests

```
invoke test-changed               # tier 1, while working: the tests of the changed paths
invoke test-all                   # tier 2, before a hand-off: everything but `slow`, -n auto; prints the tree hash
invoke test-release               # tier 4, before tagging: everything including `slow`
invoke test                       # plain pytest run (--all: with slow, --parallel: -n auto)
invoke test -k auth               # a subset
invoke test --dump 260916         # also the smoke test against a local dump
invoke check-server-wheels        # would the backend install on Uberspace 7 without compiling?
```

Route tests are skipped with a message if no `mongod` is found. Tests marked
`slow` (`pytest.ini`) are left out by default; `pytest -m ""` runs them too.
`-n auto` (pytest-xdist) gives every worker its own throwaway `mongod`; against a
shared server (`CSC_TEST_MONGODB_URI`) every worker gets its own database
`csc_<worker>`. CI runs only `tests/api`, the frontend and the deploy checks.

### Troubleshooting

- **`[next-auth][error][CLIENT_FETCH_ERROR] ... "<!DOCTYPE" is not valid JSON`**
  (or "Jest worker encountered child process exceptions" in the dev server
  output): the Turbopack dev cache is broken. Stop `npm run dev`, delete
  `src/frontend/.next`, start again. Run only one dev server per checkout --- a
  second one shares and corrupts the same cache.
- **`Fatal error in launcher`** from `invoke` / `pytest`: the conda env was
  renamed or moved; recreate it (see step 2) or use `python -m invoke ...`. Every request
to a backend is logged with its `X-CSC-Client` header in
`logs/client_versions.log` (locally `.dev/logs/`). The line holds the time, the
client name and version (or the browser's name), the method, the path and the
status: no IP address and no user name. Both this file and gunicorn's
`logs/fastapi.log` (the error log; the access log is off) rotate at midnight and
keep 14 days (`logrotation.py`), the retention the privacy page names. The
backend logs through the `csc` logger (`logging_setup.py`): in the API into
`logs/fastapi.log`, in the cron scripts to stderr, which their cron lines append
to the dated `*_cronjob.<date>.log` files; `CSC_LOG_LEVEL` sets the level. A log
line holds counts and ids only, never a user name, an e-mail address or a typed
value. When the database cannot be reached the API answers 503 with
`Retry-After` and logs the traceback.

Every environment variable of the backend is named once, with its type, default
and purpose, in `src/backend/settings.py`; it is the only place that reads the
environment. A missing or wrong value stops the start and names the variable,
never its value.

---

# Installation & Configuration

Start by cloning this repo onto your desktop computer.

## MongoDB

Either create a MongoDB atlas account and set up a new database or run a
MongoDB database by other means. You will need the full connection string in
the form `mongodb+srv://user:password@host/dbname`.

## Creating a Secret Key for JWT Auth

Open a terminal and run the following command to create a random secret key
that will be used to sign JWT access tokens while authenticating with the
FastAPI backend:

```
$ openssl rand -hex 32

>> 09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7
```

- You will end up with a key like the above (__DO NOT__ use the one in this
example!).
- If in doubt, have a look here for a detailed explanation of the auth setup:
[FastAPI OAuth2 with Password (and hashing), Bearer with JWT tokens]
(https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#handle-jwt-tokens)

## Setting up Environment Variables

All secrets and configuration are passed via environment variables - no config
files with credentials are used in the backend.

### Backend environment variables

The backend reads all configuration from the environment at startup and will
exit immediately with a clear error listing any missing variables. There are
two places you need to set them:

**1. `~/.bash_profile`** - for the cron jobs and the deploy script: copy the
template `uberspaceconfig/.bash_profile.example` and fill it in (MongoDB, JWT,
SMTP with the optional `SMTP_REPLY_TO`, the support address that replies to the
verification and password-reset mails go to, asset folders, CORS origins;
optionally `GITHUB_CSC_GH_TOKEN` for higher GitHub rate limits in
`CSC_Update`). Optional: `CSC_MAX_DATASETS_PER_USER` (default 3), how many
datasets a non-admin account may create; admins are not limited.

Apply immediately by running: `source ~/.bash_profile`

**2. `~/etc/services.d/fastapi.ini`** - for the supervisord-managed FastAPI
service (supervisord does _not_ read `~/.bash_profile`). Copy
`uberspaceconfig/etc/services.d/fastapi.ini.example` to the server, fill in
the real values in the `environment=` block, and keep it off git (it is
gitignored; only the `.example` file is tracked).

### Frontend environment variables

- Navigate to `...\csc\src\frontend`
- Copy `.env.example` and rename it to `.env`
- Edit `.env` and fill in the values following the comments in the file
- Proceed in the same way with copying `.env.local.example` and renaming it to `.env.local`
- Set `NEXTAUTH_SECRET` to a long random value of its own: it only encrypts the NextAuth session cookie and is independent of the backend's `JWT_SECRET` (the frontend never verifies the backend token). There is no `API_SECRET`; delete it from older `.env` files.
- The frontend has no database access and needs no MongoDB variables: the sign-in sends the credentials to the backend's `POST /auth/token`, the only place a password is checked. Older `.env` files may keep `MONGODB_*`; nothing reads them.
- The pages carry a Content-Security-Policy built per request with a fresh nonce (`proxy.ts`, `lib/csp.ts`): scripts only by nonce, styles inline, everything else from the app's own origin; the Google map frame and the static host of `NEXT_PUBLIC_STATIC_BASE_URL` (images only) are the exceptions. If a page breaks on a server because of it, set `CSC_CSP_REPORT_ONLY=1` in the frontend `.env` and restart the frontend: the same policy is then sent as `Content-Security-Policy-Report-Only`, which only logs violations in the browser console. Remove the line again once fixed.
- `NEXT_PUBLIC_STATIC_BASE_URL` is optional and only for public UI files under `/static/` served by Apache. Leave it empty otherwise. Catalogue files (previews, photos, meshes, point clouds, proxies, capture fixtures) are private: they live outside the web root (`~/csc_assets_private/`) and are served only through the authenticated `/snapshots/...` routes of the API. It is ignored on localhost.

## Grasshopper Interface Setup

The CSC Grasshopper Interface consists of Python 3 components that can be used directly in Grasshopper:

- **Location**: `grasshopper_userobjects_src/` - Source files for development
- **Installation**: Copy `.ghuser` files from `grasshopper_userobjects/` to your Grasshopper UserObjects folder
- **Requirements**: Python 3 with packages: requests, numpy, scipy, scikit-learn
- **Authentication**: Use the `CSC_Session` component first to sign in (see "Signing in from Grasshopper" below)
- **Documentation**: Component reference, copy-to-clipboard XML, and release download on the frontend at `/gh-interface`
- **Backend routes**: Release download, sources, XML and updater assets are served under `/ghinterface/` (e.g. `version`, `download`, `src/{name}`, `xml/{name}`, `userobject/{name}`). They come from the GitHub release of the running backend (tag `v<version>`); a `channel` query param (GitHub branch or tag) overrides that for testing.

### Signing in from Grasshopper

The `CSC_Session` component has two button inputs, `SignIn` and `SignOut`.

- **SignIn (Windows, Rhino 8)**: press it, the browser opens on the CSC
  consent page ("Sign in Grasshopper on this computer"), press Allow, and
  Grasshopper is signed in; no password goes into a document or an input. The
  component listens for the answer on your own computer only (`127.0.0.1`, a
  random port, at most 10 minutes, once) and Grasshopper stays usable while it
  waits. The sign-in is kept for your Windows user, encrypted with DPAPI, in
  `%APPDATA%\DDU_CSC\signin.json` (one entry per server address): after a
  restart of Rhino the component signs in again by itself. The access token is
  good for an hour and renews itself through that sign-in, also when a call
  answers 401; the stored sign-in is good 30 days after its last use and at
  most 90 days from your consent, then press SignIn again. Every account with a
  verified address may do it (it is no role).
- **SignOut**: deletes the stored sign-in on this computer and revokes it on the
  server.
- **Revoke from the website**: Settings, "Access tokens" lists every
  sign-in as "Grasshopper on" the name of that computer; "Revoke" ends it (the
  hour of the current access token runs out; the sign-in cannot renew).
- **Username and Password** stay as the fallback (and the only way on macOS):
  when both are connected they win over the stored sign-in. That path renews
  itself too: when a call answers 401 the component signs in once more with
  them and repeats the call.
- **Pressing SignIn without Windows** says that the sign-in without a password is
  Windows only.
- **Changing or resetting your password** ends every Grasshopper sign-in of the
  account too (and every other token and connection): the stored sign-in cannot
  renew any more, so press SignIn again afterwards.

## Releases and deployment

Backend, web frontend and Grasshopper interface are one product with one
version (`VERSION`), released together as tag `v<version>` and deployed by
GitHub Actions. You make every commit, merge and tag; everything after the tag
push is automated.

**Cutting a release**

1. On your working branch, in this order:
   1. `invoke bump-version --version 0.5.1.1` writes the version everywhere and
      opens a `## [0.5.1.1] - unreleased` section in `CHANGELOG.md`. Add `--gh`
      if the Grasshopper UserObjects changed --- then re-export the changed
      `.ghuser` / XML in Rhino. With `--gh`, a client version that already is
      the new version leaves `DDU_CSC_Session.py` as it is (the `Version:`
      header keeps matching the exported `.ghuser`).
   2. Fill in that `CHANGELOG.md` section: it becomes the release notes.
   3. `invoke release-prep` (`--date YYYY-MM-DD`, default today) dates the
      section, writes `.zenodo.json`, runs the version check for the tag and
      the Zenodo check, and runs `tests/ci`. It stops with an error if the
      section is missing or empty or a check fails, and prints the next steps;
      a second run only checks.
2. Run the whole suite once locally, including the slow tests:
   `invoke test-release` (set `CSC_TEST_RHINO=1` for the headless Rhino tests and
   `CSC_DUMP_DIR` for the migration on a dump). CI no longer runs `tests/catalog`,
   `tests/grasshopper` or anything marked `slow`, so this run is the check for
   them.
3. Open a PR into `main`; CI must pass (`.github/workflows/ci.yml`): backend
   route tests (`tests/api`) on MongoDB, server wheel check, deploy-script test,
   frontend type check / lint / tests / build, Grasshopper checks (a changed
   component needs a higher `Version:` and a re-exported `.ghuser` + XML),
   version consistency. On a PR the frontend and backend jobs run only when
   their paths changed; CI does not run on a push to a branch.
4. Merge, then tag the merge commit on `main` and push the tag:
   `git tag v0.5.1.1 && git push origin v0.5.1.1`.
5. `.github/workflows/release.yml` runs CI again (every job, whatever changed), builds
   `csc-backend-<v>.tar.gz`, `csc-frontend-<v>.zip`, `csc-gh-interface-<v>.zip`
   and `SHA256SUMS`, attests each of the three bundles (a signed statement that
   this repository's release workflow built exactly that file), and publishes
   GitHub Release `v<v>` (pre-release if the version has a `-suffix`).
6. The deploy job waits for your approval (environment `production`), then runs
   `csc_release_deploy.sh v<v>` on Uberspace over a restricted SSH key: download
   the bundles and verify them (`SHA256SUMS`, then `gh attestation verify` for the
   backend tar and the frontend zip; the deploy stops if `gh` is missing or a check
   fails), unpack to `~/csc/releases/<v>/`, build a venv only if
   the requirements changed, switch `~/csc/current`, restart, health-check
   (`/version` must report `<v>`, the frontend must answer) --- or roll back to
   the previous release by itself.

**Grasshopper updates** come from the release the server runs: `CSC_Update` and
the interface download on the web page read tag `v<version>` of the running
backend. Merging to `main` publishes nothing; deploying a release updates
backend, web and Grasshopper at once. Testers can still point `UPDATE_CHANNEL`
in `CSC_Update` at a branch.

**Redeploy, roll back, status:** run workflow **Deploy** by hand with
`deploy v<version>`, `rollback` or `status`; on the server the same commands are
`~/csc/bin/csc_release_deploy.sh v<version> | --rollback | --status`. Database
migrations are never part of a deploy.

## Server setup (Uberspace)

The server runs whatever `~/csc/current` points to:

```
~/csc/
+- releases/<version>/   backend/ frontend/ deploy/ VERSION venv -> ../../venvs/<hash>
+- current -> releases/<version>
+- venvs/<hash>/         one per requirements + constraints content
+- shared/frontend/      .env / .env.local (frontend secrets, linked into releases)
+- shared/logs/          backend and cron logs (linked as backend/logs)
+- bin/                  csc_release_deploy.sh, csc_deploy_gate.sh
```

The one-time setup (Python 3.13, directories, services, cron, deploy key, GitHub
environment) is described step by step in `uberspaceconfig/deployment/README.md`.
Templates: `uberspaceconfig/etc/services.d/` (supervisord),
`uberspaceconfig/crontab/` (cron jobs), `uberspaceconfig/.bash_profile.example`.

## Upgrading Next.js

Use the official Next.js codemod to upgrade the frontend to a newer version:

```bash
# Upgrade to the latest patch (e.g. 16.0.7 -> 16.0.8)
npx @next/codemod upgrade patch

# Upgrade to the latest minor (e.g. 15.3.7 -> 15.4.8). This is the default.
npx @next/codemod upgrade minor

# Upgrade to the latest major (e.g. 15.5.7 -> 16.0.7)
npx @next/codemod upgrade major

# Upgrade to a specific version
npx @next/codemod upgrade 16

# Upgrade to the canary release
npx @next/codemod upgrade canary
```

## Services Config using Supervisor

Uberspace runs services with _Supervisor_. The templates in
`uberspaceconfig/etc/services.d/` run the active release from `~/csc/current`:
copy `fastapi.ini.example` to `~/etc/services.d/fastapi.ini` and fill in the
`environment=` block (it holds the backend's secrets and is gitignored --- never
commit a filled-in copy), copy `frontend.ini.example` to
`~/etc/services.d/frontend.ini`, then `supervisorctl reread && supervisorctl
update`. Deploys restart both services themselves.

## Configuring Web Backends

- _Gunicorn_ is set up to run the _FastAPI_ backend on Port 8000
- The _Next.js_ frontend is configured to run on Port 3000
- The Web Backends have to be set to the port that the apps are listening on!

- First, we list the active backends:

```
[user@servername ~]$ uberspace web backend list
/ apache (default)
[user@servername ~]$
```

- We will not use the default backend, so we delete it

```
[user@servername ~]$ uberspace web backend del /
The web backend has been deleted.
[user@servername ~]$
```

- Next we register a subdomain for our _FastAPI_ backend...

```
[user@servername ~]$ uberspace web domain add api.username.uber.space
The webserver's configuration has been adapted.
Now you can use the following records for your DNS:
    A -> 185.26.156.55
    AAAA -> 2a00:d0c0:200:0:b9:1a:9c:37
[user@servername ~]$
```

- Then we add the corresponding web backend for _FastAPI_

```
[user@servername ~]$ uberspace web backend set api.username.uber.space/ --http --port 8000
Set backend for api.username.uber.space/ to port 8000; please make sure something is listening!
You can always check the status of your backend using "uberspace web backend list".
[user@servername ~]$ 
```

- Lastly, we set our default backend to point to the _Next.js_...

```
[user@servername ~]$ uberspace web backend set / --http --port 3000
Set backend for / to port 3000; please make sure something is listening!
You can always check the status of your backend using "uberspace web backend list".
[user@servername ~]$ 
```

For further information please refer to the corresponding Uberspace manual and
Uberlab guides:
- [Uberspace Web Backends](https://manual.uberspace.de/web-backends/)
- [Uberspace Web Domains](https://manual.uberspace.de/web-domains/)

## Client addresses and rate limits

The backend limits logins, registrations and the expensive exports (PDF, CERO)
per client. A visitor reaches the backend through two hops: the Uberspace web
proxy, then the Next.js server (`/api/backend`, `/api/auth`, `/api/register`).
Each proxy appends the address of its peer to `X-Forwarded-For`; whatever the
browser wrote itself stands on the left of that chain and is never believed.

- Next.js (`lib/clientAddress.ts`) takes the address `CSC_PROXY_HOPS` proxies
  from the right (default `1`, the Uberspace proxy; `0` = no proxy in front,
  nothing is passed on) and sends it to the backend as a single-entry
  `X-Forwarded-For`.
- The backend (`limiter.py`) believes that header only when its peer is listed
  in `CSC_TRUSTED_PROXIES` (default: loopback `127.0.0.0/8,::1`) and then takes
  the rightmost entry that is not itself a trusted proxy. From any other peer
  the header is ignored and the peer is the client. Signed-in callers of the
  exports count per user, everyone else per address.
- `conf.py` hands the same list to gunicorn as `forwarded_allow_ips`, so the server and
  the limits agree about who may speak for a client; a bad entry stops the start and
  `*` is refused. `bind = ':8000'` stays (the Uberspace web backend connects there).
- The counters live in MongoDB (`CSC_RATE_LIMIT_STORAGE`; unset, the database of
  `MONGODB_URI`, in the collection `rate_limit_counters`, which a TTL index
  empties), so that every gunicorn worker counts the same requests. If the
  database does not answer, requests pass uncounted and the log says so once;
  `memory://` keeps the counters in the process (tests, local runs). Failed
  sign-ins are counted per account as well: ten in fifteen minutes, then 429
  with `Retry-After`, until the window is over.
- Request bodies are capped before a route reads them: the mesh and point cloud
  uploads at `GEOMETRY_UPLOAD_LIMIT_MB`, evidence attachments at
  `EVIDENCE_UPLOAD_LIMIT_MB`, photos at `SNAPSHOT_PHOTO_UPLOAD_LIMIT_MB` (each plus
  1 MB for the multipart framing), every other route at `CSC_JSON_BODY_LIMIT_MB`
  (default 16). The result route of the remote runner has its own limits.
- Set `FASTAPI_URL=http://127.0.0.1:8000` on the server: the backend then sees
  the web server on loopback. If the web server reaches the backend through the
  public API host instead, the connection comes from the web proxy and the web
  server's own address is appended to the chain: add both to
  `CSC_TRUSTED_PROXIES`, and check after deploying that two visitors do not
  share a limit (the Uberspace manual does not state which headers its proxy
  sets or from which address it connects).

## Access tokens

A personal access token lets a tool other than the web app (for instance an AI
assistant through the MCP layer) read the catalog as its owner, and nothing
more. It is not the JWT of a sign-in: a token only works where its scope says,
and a JWT does not work in place of it.

- **Who.** Administrators at first. `CSC_PAT_ROLES` (default `admin`, a comma
  list of the global roles `admin` and `user`) opens it to more; the role is
  checked again on every request, so an account that loses it stops working at
  once. Everyone sees and revokes the tokens they hold in Settings, "Access
  tokens"; administrators see every token under Admin, "Access tokens", and can
  revoke any.
- **Create.** Settings, "Access tokens": a name and a lifetime of 30 days, 90
  days (the default) or 1 year; there is no token without an expiry. The token
  (`csc_pat_` and 43 characters) is shown once, with a copy button; copy it
  then. The list shows only its first 8 characters, name, scope, created, last
  used and expiry. At most 10 active tokens per account.
- **Renew.** Within 14 days of the expiry (and after it) the list offers
  "Renew": a new token with the same name is made and shown once, the old one
  is revoked.
- **Revoke.** "Revoke" in the list stops the token at once. Revoked and expired
  tokens, a lost role, an unverified, disabled or deleted account all stop it
  at once: the database is asked on every request, nothing is cached.
- **Try a token.** `curl -H "Authorization: Bearer csc_pat_..."
  https://<api host>/auth/token-check` answers the owner, the scope and the
  expiry; every other answer is the same 401, whatever the reason. This path
  and `/mcp` need no `X-CSC-Client` header (the connectors of Claude cannot
  send one); every other route still does.
- **Limits and the log.** 120 requests a minute per token (counted per worker,
  like the read limits); the last use is written at most once a minute and not
  at all while the maintenance flag is set; creating, renewing and revoking are
  writes and get the 503 of that flag. The log has one line per use: the first
  8 characters of the token and the route, no personal data.
- **Stored.** Only the SHA-256 of a token is stored (collection
  `access_tokens`), so a leaked database holds no usable token.
- **Password.** Changing your password (Settings) and resetting it by mail end
  every token and connection of the account at once, of every kind: personal
  access tokens, Claude connections and Grasshopper sign-ins, their refresh
  tokens included. Afterwards make a new token, press Allow in Claude again and
  press SignIn in Grasshopper again.

## Using CSC from Claude

Claude can read the catalog as you: ask it to find components, show one with its
versions and measurements, compare, or look at what happened to a piece. It
only reads, and it sees what you see on the website; nothing it can reach is
private to anybody else. Administrators can connect it for now (the roles are
`CSC_PAT_ROLES`).

**Connect.** In Claude, add a custom connector (claude.ai: Settings, Connectors,
Add custom connector; Claude Code: `claude mcp add --transport http csc
https://<api host>/mcp`) and give it the address `https://<api host>/mcp`, for
the production server `https://api.2ndchances.build/mcp`. Claude opens the CSC
consent page: sign in if asked, check the address it says you will be sent back
to (for Claude on the web that is `claude.ai`), and press Allow. Deny, or closing
the page, connects nothing. Nothing is remembered: every connection asks again.
Allow only connections you started yourself: anyone can start an authorization
and send you the link, so look at the large address line (the host you will be
sent back to) before you press Allow, and press Deny when it is not the tool you
just connected.

**What it can do.** Ten read-only tools: `search_components` (the filters of
Browse and `has_evidence`, which keeps only pieces with a published, current
record of one evidence method, for example `reinforcement_layout` for "with
reinforcement", a page at a time), `catalog_overview` (how many pieces, counted
by material, original function, dataset, shape class and circulation, the range
of each sorted side in millimetres, and how many have a location; it takes the
same filters), `get_component` (with the reinforcement layouts of the current
version as counts), `list_versions`, `get_version` (geometry as counts and a
link, never the meshes; the reinforcement layouts of the version as counts),
`get_evidence`, `list_datasets`, `get_dataset`, `get_timeline` and
`similar_components` (the pieces nearest in shape over the whole descriptor, not
on the two-dimensional similarity map, with their distance in standardised
units; it takes the same filters, which apply before the ranking). Every answer
carries the web link of the record, and a record that is not public is marked
(`visibility` private, `status` other than published). There are no write tools
and no tool for users, invitations or tokens; no answer holds an e-mail address
or an account id.

**How long it lasts.** The connection gives Claude an access token of one hour
and a refresh token that Claude renews by itself: the refresh token is good for
30 days after its last use and is replaced on every use (using an old one ends
the connection), and a connection never lasts more than 90 days from your
consent, then Allow again. Each connection is a line under Settings, "Access
tokens" (and under Admin for administrators): "Revoke" ends it at once, access
and refresh. An account that loses its role, is disabled or is deleted stops
working at once, because every call asks the database.

**For scripts and other clients.** A personal access token (Settings, "Access
tokens") works on `/mcp` too, as `Authorization: Bearer csc_pat_...`, for a
client that sends a header and cannot sign in through a browser.

**On the server.** `CSC_PUBLIC_API_URL` must be the API address (`https://<api
host>`); the MCP endpoint and the OAuth server (`/.well-known/...`, `/register`,
`/authorize`, `/token`, `/revoke`, `/mcp`) are served by the backend and are off
without it. During maintenance (the read-only flag) `/mcp` and the refreshing of
tokens keep working; a new connection, a new registration and a revoke wait. The
limits: 120 requests a minute per token, and per address on registering,
authorizing and the token endpoint.

## Custom domain (`2ndchances.build`)

`2ndchances.build` is the canonical frontend origin; The old address `ddu.uber.space`
stays registered and redirects to it. The app cannot be served on both origins
at once: NextAuth v4 resolves every absolute auth URL from the single
`NEXTAUTH_URL`, and its session cookie is host-only, so a login on the
non-canonical host would set a cookie there and then be redirected away from
it. The redirect lives in `src/frontend/next.config.ts` and matches on the
request host.

Register the domain and point it at the frontend port:

```
[user@servername ~]$ uberspace web domain add 2ndchances.build
[user@servername ~]$ uberspace web backend set 2ndchances.build/ --http --port 3000
```

Then update these values and restart both services:

| Value | Location |
| --- | --- |
| `NEXTAUTH_URL=https://2ndchances.build` | `~/csc/frontend/.env` |
| `FRONTEND_URL="https://2ndchances.build"` (verification email links) | `~/etc/services.d/fastapi.ini` and `~/.bash_profile` |
| `CSC_PUBLIC_API_URL="https://api.2ndchances.build"` (optional: the API address in the links of the JSON-LD and PDF exports) | `~/etc/services.d/fastapi.ini` and `~/.bash_profile` |
| `FASTAPI_CORS_ORIGINS` (add the new origin) | `~/etc/services.d/fastapi.ini` and `~/.bash_profile` |
| `CSC_WORKERS="2"` (optional, 1 to 8, default 2: gunicorn workers; each loads the geometry libraries, so the number follows the memory of the account) and `CSC_LOG_LEVEL="info"` (optional: `debug`, `info`, `warning`, `error`, `critical`, default `info`) | `~/etc/services.d/fastapi.ini` (read by `conf.py`; a deploy no longer resets them) |
| `Access-Control-Allow-Origin` allowlist | `~/html/.htaccess` |

`NEXT_PUBLIC_STATIC_BASE_URL` (public UI files under `/static/` only) describes
where those files are *fetched from*, not where the app is served, so it only
changes if the Apache static host itself moves. Catalogue files have no host:
`next.config.ts` allows no remote images, they come through the API.

Adding the domain to `FASTAPI_CORS_ORIGINS` is a safety net rather than a
requirement: the browser only ever calls the API through the same-origin proxy
at `/api/backend/[...path]`, which is a server-to-server request and therefore
not subject to CORS.

## Deploying .htaccess

The repo contains `uberspaceconfig/html/.htaccess` which must be placed at
`~/html/.htaccess` on the server. It sets CORS headers for the Apache layer and
forces `.wsc` files to download as `application/octet-stream` rather than being
served inline. Without it, Grasshopper component downloads will not work
correctly.

```
[user@servername ~]$ cp ~/csc/uberspaceconfig/html/.htaccess ~/html/.htaccess
```

Before deploying, update the origin allowlist in the `SetEnvIf Origin` line to
match your actual frontend domains. A plain `Header set Access-Control-Allow-Origin`
can only name a single origin, which is why the file reflects a matched origin
instead.

### Private asset files

The six `SNAPSHOT_*_DIR` folders (previews, photos, meshes, point clouds,
proxies, capture fixtures) live in `~/csc_assets_private/`, outside the web
root, next to the evidence attachments, and are served only by the API. Two
more `.htaccess` files keep the old location closed and the public UI files
open:

```
[user@servername ~]$ cp ~/csc/uberspaceconfig/html/csc_assets/.htaccess ~/html/csc_assets/.htaccess
[user@servername ~]$ cp ~/csc/uberspaceconfig/html/csc_assets/static/.htaccess ~/html/csc_assets/static/.htaccess
```

`~/html/csc_assets/.htaccess` denies everything (`Require all denied`) as a
second guard in case a folder is ever put back; `static/.htaccess` re-allows
the public UI files in `~/html/csc_assets/static/` (the Grasshopper interface
images the release deploy copies there).

### Maintenance mode

`~/csc/bin/csc_maintenance.sh on | off | status` shows a static 503 page for the
web domain while the frontend is stopped or deployed (cutovers, migrations); see
`uberspaceconfig/deployment/README.md`, "Maintenance mode" (the script uses the
domain's own folder `/var/www/virtual/$USER/<domain>`, creates it when missing and
removes it again, links `www.<domain>` to it, restores the backends it found, and
never writes to `~/html`; verify it on a test subdomain before the first use).

**Read-only mode:** `touch ~/csc/shared/READ_ONLY` before and `rm
~/csc/shared/READ_ONLY` after every maintenance step that writes to the database
or the asset folders (restore, purge, migration, cutover). While the file
exists the backend answers every write with 503 (`read-only: maintenance`),
sign-in stays open and writes nothing, the web app shows a banner and disables
its write buttons, and the cron jobs that write skip their run. Every worker
checks the file per request, so no restart is needed. Details:
`uberspaceconfig/deployment/README.md`, "Read-only mode".

## Cron jobs

All jobs run the active release (`~/csc/current`) and log to `~/csc/shared/logs/`,
each to a file of the day (`<job>_cronjob.<YYYY-MM-DD>.log`); one more line of the
crontab deletes those older than 14 days (the privacy page promises this).
The complete crontab, ready to paste into `crontab -e`, is
`uberspaceconfig/crontab/crontab.example` (it replaces the whole crontab; the
`MAILTO` line at its top names the maintainer's address, set only on the
server). Its jobs:

| job | schedule | what |
|---|---|---|
| geometry runner | every 20 min (`flock -n ~/csc/shared/locks/heavy.lock`, `--due --limit 10`: only the snapshots a write has marked) and nightly at 3:30 (`flock -w 900`, all snapshots, `--limit 200 --sweep`) | geometry runner: frame, shape class, proxies + deviation maps, descriptors, complexity, previews of every snapshot whose derivation is stale. With `CSC_GEOMETRY_HEAVY_STAGES=remote` it runs only frame and shape class, and the rest runs on a worker elsewhere (`main_geometry.py --remote <url> --user <admin>`, password in `CSC_API_PASSWORD`); the recompute route then only marks the heavy stages stale |
| component map | daily 4:15 (`flock -w 3600 ~/csc/shared/locks/heavy.lock`) | precomputes PCA / UMAP layouts for the component map |
| `usermaintenance.py` | daily 2:00 | removes unverified accounts older than 7 days (the log holds counts and ids, no names or addresses) |
| log retention | daily 1:30 | `find` deletes the cron and deploy logs older than 14 days |
| `geometrymaintenance.py` | daily 3:00 | removes geometry folders without a component |

The geometry runner and the component map share one lock, `~/csc/shared/locks/heavy.lock`
(not in `/tmp`, which other accounts on the host can write to; `mkdir -p ~/csc/shared/locks` once),
so the two heavy jobs never run together (server memory): the
frequent geometry run skips its run while the lock is held, the nightly run and
the map wait up to 15 minutes instead of losing their slot. A write that changes
what the geometry stages read (a new version, a file, the geometry, the colour,
an override, the function of the piece) marks the snapshot (`derivation_due`);
the frequent run derives only marked snapshots, the nightly run checks all of them
(`main_geometry.py --due` / without it).

Each line starts with `source ~/.bash_profile &&` so the job sees the backend's
environment variables. To run a job by hand:
`~/csc/current/venv/bin/python ~/csc/current/backend/main_geometry.py --snapshot <id>`
(`--help` lists the stages and `--recompute`). Only the cron passes `--sweep`, which
deletes the previews and deviation maps of snapshots that no longer exist: never
run it against a local copy of the assets.

## OpenAPI Model Generation

This project uses OpenAPI schema generation to keep frontend TypeScript models in sync with backend Pydantic models.

### How It Works

1. **Backend**: Pydantic models are enhanced with OpenAPI documentation and Field descriptions
2. **Schema Endpoint**: `/schema/component` endpoint exposes the ComponentModel schema
3. **Frontend Generation**: Script fetches schema and generates TypeScript interfaces
4. **Auto-sync**: Models are automatically kept in sync

### Usage

#### Generate Models

```bash
# Generate data models from backend
npm run generate:models
```

#### Development Workflow

1. **Update Backend Model**: Modify Pydantic model in `src/backend/apps/catalog/models.py`
2. **Restart Backend**: Restart FastAPI to regenerate OpenAPI schema
3. **Generate Frontend Models**: Run `npm run generate:models`
4. **Use Generated Models**: Import from `src/generated/ComponentModel`

#### Import Generated Models

```typescript
// Instead of importing from components/common/models
// import { ComponentData } from '@/components/common/models';

// Import from generated models
import { ComponentModel, ComponentType, ComponentComplexity } from '@/generated/ComponentModel';

// Use the generated interface
const component: ComponentModel = {
  _id: "uuid",
  type: "slab",
  material: "concrete",
  // ... other properties
};
```

### File Structure

```
src/frontend/
+-- scripts/
|   +-- generate-models.ts    # Generation script
+-- generated/                 # Auto-generated models
|   +-- ComponentModel.ts     # Generated ComponentModel interface
|   +-- index.ts             # Export index
+-- package.json              # Contains generate:models script
```

## Testing and linting

See "Local development and tests" above: `invoke test` runs the Python tests;
the frontend is checked with `npx tsc --noEmit` and `npm run lint` in
`src/frontend`. CI runs the route tests and the frontend checks on a PR (see above for the rest).

## Test data: open datasets

> **Note:** these imports aare used for validation within a doctoral thesis at the Digital Design Unit (DDU), TU Darmstadt. They
> validate the CSC data model against precedents: other researchers' component databases, each recorded with
> its own schema and purpose. Importing them as published, inventing nothing and documenting every assumption,
> shows what the model can represent and what it cannot.

| Dataset | Source | Tools and instructions |
|---|---|---|
| ReCreate pilot elements: 1150 reclaimed precast concrete elements of three donor buildings | <https://doi.org/10.5281/zenodo.16809738>, CC BY 4.0 | [`scripts/import/recreate/`](scripts/import/recreate/README.md) |
| EPFL stones for augmented stacking: 452 scanned quarry offcut stones | <https://doi.org/10.5281/zenodo.7180964>, MIT | [`scripts/import/epfl_stacking/`](scripts/import/epfl_stacking/README.md) |

The data is fetched from Zenodo and never committed. Everything else (environments, the order of the steps,
the local rehearsal, the production procedure, attribution) is in each folder's README.

# Credits

## Contributing

Bug reports, requests and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Public Funding

Part of this research was conducted within the project
[_Fertigteil 2.0 - Real-digital process chains for the production of built-in
concrete components_](https://www.dg.architektur.tu-darmstadt.de/forschung_ddu/digitale_prozessketten_ddu/computational_design/fertigteil_2__0/fertigteile_2__0.en.jsp)
(Precast Concrete Components 2.0), funded by the German Federal Ministry of
Education and Research (BMBF, today [BMFTR](https://www.bmftr.bund.de/)) through
the funding measure
["Resource-efficient circular economy - Building and mineral cycles (ReMin)"](https://www.fona.de/en/measures/funding-measures/Resource-efficient-circular-economy-building-and-mineral-cycles.php).

<a href="https://www.bmftr.bund.de/"><img src="src/frontend/public/logo/funding/bmbf.svg" alt="Funded by the Federal Ministry of Education and Research (BMBF)" height="80"></a>

Part of this research is conducted within the project
[_ZirKuS - Circular Construction and Structural Design of Reused Concrete
Components_](https://www.dg.architektur.tu-darmstadt.de/forschung_ddu/digitale_prozessketten_ddu/computational_design/zirkus/zirkus.en.jsp),
funded by the [Deutsche Bundesstiftung Umwelt - DBU](https://www.dbu.de/projektdatenbank/40160-01/)
(German Federal Environmental Foundation, project 40160-01) within the funding
line
["Climate- and Resource-Efficient Construction"](https://www.dbu.de/foerderung/projektfoerderung/foerderthemen/klima-und-ressourcenschonendes-bauen/).

<a href="https://www.dbu.de/projektdatenbank/40160-01/"><img src="src/frontend/public/logo/funding/dbu-sponsored-by.png" alt="Sponsored by the Deutsche Bundesstiftung Umwelt (DBU)" height="80"></a>

## Student Work

- The `csc_labels` python code to create QR-Code labels was developed by Mirko
Dutschke. The code has been refactored as a python module and integrated by
Max Benjamin Eschenbach.
- The `csc_sheetscan` python module was developed based on the scanning setup
for sheets that was developed by Mirko Dutschke. The functional code has been
written by Max Benjamin Eschenbach.
- Idea and prototype code for `FindLargestFlatSide` Grsshopper component by Alessandro Garruto. The code has been refactored and integrated by Max Benjamin Eschenbach.
Idea and prototype code for `MaxInscribedQuad` Grasshopper component by Alessandro Garruto. The code has been refactored and integrated by Max Benjamin Eschenbach.
## Licensing

- Original code is licensed under the MIT License.
- The `csc_sheetscan` module makes heavy use of the
[OpenCV](https://opencv.org/) library, more specifically its
[pre-built packages for python](https://anaconda.org/conda-forge/opencv)
via conda-forge.

## References

- The technical main inspiration for the _Catalog of Second Chances_
interface is the [Catalog Explorer](https://github.com/ibois-epfl/catalogue-explorer)
by [@AymbericBr](https://github.com/AymericBr).
- Another huge inspiration and reference is the
[Timberstone Project](https://epfl-enac.github.io/MANSLAB-IBOIS-EESD-timberstone/),
which is the origin of abovementioned Catalog Explorer.

## Citing

When using, extending or building upon this piece of softare in your work, please reference it accordingly:

### BibTex

```
@software{eschenbach_2026_20156667,
  author       = {Eschenbach, Max Benjamin},
  title        = {Catalog of Second Chances (CSC) - Digital Database
                   and Corresponding Interfaces for ReUse of
                   Architectural Components
                  },
  month        = may,
  year         = 2026,
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.20156666},
  abstract = {The Catalog of Second Chances (CSC) provides a prototypical platform and the corresponding tools to leverage a database of uniquely identified, digitized architectural components for creating designs that reuse these components.},
  url          = {https://doi.org/10.5281/zenodo.20156666},
}
```

### Other Citation Styles

Find pre-written citations in the style of your choice over at [Zenodo](https://zenodo.org/records/20156666) (Citation box on the right side).

# To-Do & Extension Ideas
