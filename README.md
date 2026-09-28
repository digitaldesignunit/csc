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

- **CSC**: 0.5.1.0 --- backend, web frontend and Grasshopper interface are released together
  under one version (tag `v0.5.1.0`); the single source is the `VERSION` file.

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
UserObjects always talk to production (`CSC_Session` has no base-URL input yet).

### Tests

```
invoke test                       # unit tests + route tests on a throwaway mongod
invoke test -k auth               # a subset
invoke test --dump 260916         # also the smoke test against a local dump
invoke check-server-wheels        # would the backend install on Uberspace 7 without compiling?
```

Route tests are skipped with a message if no `mongod` is found.

### Troubleshooting

- **`[next-auth][error][CLIENT_FETCH_ERROR] ... "<!DOCTYPE" is not valid JSON`**
  (or "Jest worker encountered child process exceptions" in the dev server
  output): the Turbopack dev cache is broken. Stop `npm run dev`, delete
  `src/frontend/.next`, start again. Run only one dev server per checkout --- a
  second one shares and corrupts the same cache.
- **`Fatal error in launcher`** from `invoke` / `pytest`: the conda env was
  renamed or moved; recreate it (see step 2) or use `python -m invoke ...`. Every request
to a backend is logged with its `X-CSC-Client` header in
`logs/client_versions.log` (locally `.dev/logs/`).

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
SMTP, asset folders, CORS origins; optionally `GITHUB_CSC_GH_TOKEN` for higher
GitHub rate limits in `CSC_Update`).

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
- Paste your JWT secret key into both the `NEXTAUTH_SECRET` and `API_SECRET` fields. This is odd but unfortunately necessary.
- Add your MongoDB credentials so that the frontend can directly authenticate with MongoDB
- Set `NEXT_PUBLIC_STATIC_BASE_URL` to a URL served directly by Apache (e.g. `https://username.uberspace.de`). On Uberspace, Next.js runs behind a reverse proxy and serving large static files (previews, downloads) through it causes 502 timeouts. This variable redirects those requests to Apache directly. It is ignored on localhost.

## Grasshopper Interface Setup

The CSC Grasshopper Interface consists of Python 3 components that can be used directly in Grasshopper:

- **Location**: `grasshopper_userobjects_src/` - Source files for development
- **Installation**: Copy `.ghuser` files from `grasshopper_userobjects/` to your Grasshopper UserObjects folder
- **Requirements**: Python 3 with packages: requests, numpy, scipy, scikit-learn
- **Authentication**: Use `CSC_SignIn` component first to authenticate with the backend
- **Documentation**: Component reference, copy-to-clipboard XML, and release download on the frontend at `/gh-interface`
- **Backend routes**: Release download, sources, XML and updater assets are served under `/ghinterface/` (e.g. `version`, `download`, `src/{name}`, `xml/{name}`, `userobject/{name}`). They come from the GitHub release of the running backend (tag `v<version>`); a `channel` query param (GitHub branch or tag) overrides that for testing.

## Releases and deployment

Backend, web frontend and Grasshopper interface are one product with one
version (`VERSION`), released together as tag `v<version>` and deployed by
GitHub Actions. You make every commit, merge and tag; everything after the tag
push is automated.

**Cutting a release**

1. On your working branch: `invoke bump-version --version 0.5.1.1` (add `--gh`
   if the Grasshopper UserObjects changed --- then re-export the changed
   `.ghuser` / XML in Rhino). Fill in the new `CHANGELOG.md` section: it becomes
   the release notes.
2. Open a PR into `main`; CI must pass (`.github/workflows/ci.yml`): backend
   tests on MongoDB, server wheel check, deploy-script test, frontend type
   check / lint / build, Grasshopper checks (a changed component needs a higher
   `Version:` and a re-exported `.ghuser` + XML), version consistency.
3. Merge, then tag the merge commit on `main` and push the tag:
   `git tag v0.5.1.1 && git push origin v0.5.1.1`.
4. `.github/workflows/release.yml` runs CI again, builds
   `csc-backend-<v>.tar.gz`, `csc-frontend-<v>.zip`, `csc-gh-interface-<v>.zip`
   and `SHA256SUMS`, and publishes GitHub Release `v<v>` (pre-release if the
   version has a `-suffix`).
5. The deploy job waits for your approval (environment `production`), then runs
   `csc_release_deploy.sh v<v>` on Uberspace over a restricted SSH key: download
   and verify the bundles, unpack to `~/csc/releases/<v>/`, build a venv only if
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
| `FASTAPI_CORS_ORIGINS` (add the new origin) | `~/etc/services.d/fastapi.ini` and `~/.bash_profile` |
| `Access-Control-Allow-Origin` allowlist | `~/html/.htaccess` |

`NEXT_PUBLIC_STATIC_BASE_URL` and the `images.remotePatterns` entry in
`next.config.ts` describe where assets are *fetched from*, not where the app is
served, so they only change if the Apache asset host itself moves.

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

## Cron jobs

All jobs run the active release (`~/csc/current`) and log to `~/csc/shared/logs/`.
The entries, ready to paste into `crontab -e`, are in `uberspaceconfig/crontab/`:

| job | schedule | what |
|---|---|---|
| `previewgen_cronjob.ini` | every 5 min | renders missing component previews |
| `descriptors_simple_cronjob.ini` | every 5 min (`flock`) | computes missing geometric descriptors |
| `component_map_cronjob.ini` | every 6 h (`flock`) | precomputes PCA / UMAP layouts for the component map |
| `usermaintenance_cronjob.ini` | daily 2:00 | removes unverified accounts older than 7 days |
| `geometrymaintenance_cronjob.ini` | daily 3:00 | removes geometry folders without a component |

Each line starts with `source ~/.bash_profile &&` so the job sees the backend's
environment variables. To run a job by hand:
`~/csc/current/venv/bin/python ~/csc/current/backend/main_previewgen.py`.

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
`src/frontend`. CI runs all of it on every PR.

# Credits

## Public Funding

Part of this research was conducted within the Project _Fertigteil 2.0 -
Real-digital process chains for the production of built-in concrete
components_. The project _Fertigteil 2.0 (Precast Concrete Components 2.0)_
was funded by the Federal Ministry of Education and Research Germany (BMBF)
through the funding measure "Resource-efficient circular economy - Building and
mineral cycles (ReMin)".

Part of this research was conducted within the Project _ZirKuS -
Circular Construction and Structural Design of Reused Concrete Components_.
The project _ZirKuS_ is funded by the Deutsche Bundesstiftung Umwelt DBU
(German Federal Environmental Foundation) within the funding line
"Climate- and Resource-Efficient Construction."

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
interface is the [Catalog Explorer](https://github.com/ibois-epfl/Catalog-explorer)
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
