# Import of the ReCreate pilot element data (open dataset, CC BY 4.0)

Test data for the Catalog of Second Chances (decision 8.145): 1150 reclaimed precast concrete elements of
three donor buildings, with their geometry, concrete values and reinforcement, imported through the HTTP
API like any other contribution. The data is **fetched from Zenodo and never committed**; this folder holds
the tools only.

Purpose: a validation of the CSC data model against a precedent component database (an element inventory
of reclaimed precast concrete with its own schema), part of the maintainer's doctoral thesis (decision 8.147).

## Source, licence, attribution

ReCreate (EU Horizon 2020, grant agreement 958200), *Reclaimed Precast Concrete Elements: Data Collection
Guidelines, Templates, & Pilot Element Data*, version 1, 2025-08-12,
<https://doi.org/10.5281/zenodo.16809738>, licensed **CC BY 4.0**
(<https://creativecommons.org/licenses/by/4.0/>).

The licence requires attribution, so the dataset and the project are named in the committed files. Every
imported dataset carries this text in its description:

> Source: ReCreate (EU Horizon 2020, grant agreement 958200), "Reclaimed Precast Concrete Elements: Data
> Collection Guidelines, Templates, & Pilot Element Data", v1, 2025-08-12,
> https://doi.org/10.5281/zenodo.16809738, licensed CC BY 4.0. Imported unchanged in substance; geometry
> computed from the published cross-section views and reinforcement drawn from the published layer tables
> (see each version's capture notes). State as published in 2025, not the present state of the elements.

Each evidence record cites the dataset itself (kind report, the DOI as url) and quotes the source text as
its claim. Names of buildings and companies come from the data at run time and are never written into this
repository; no person is named anywhere.

## What it makes

Three datasets, one per pilot (`recreate_nl`, `recreate_de`, `recreate_fi`), for the three pilot
buildings: 1150 components (one per element: load-bearing facade walls, hollow-core and solid slabs, beams,
columns), 4010 evidence records and 45474 reinforcement bars.

- **Geometry** (`geometry.py`): one watertight mesh per product (120), computed from the published data:
  the three cross-section views (front, side, plan) extruded through each other and intersected, voids
  subtracted, corbels added; hollow-core slabs from their parameters (cores, covers, webs, topping). Data
  fixes and assumptions are written into the capture notes of every version that uses them (German
  interior walls have the plan axes swapped, detected and swapped back; mirrored products are reflected
  about x = L / 2; a void of 16 corners is two hulls of 8; cut hollow-core slabs spread their cores evenly).
  Nothing of this enters the backend or the geometry runner: the mesh is uploaded like a captured mesh
  (inline, plus `detailed.ply` above 500 faces, decision 8.95).
- **Origin**: `deinstallation`, 2023 (year precision), from the donor building (name and identifier, year
  built, use, `prefabricated`; place with coordinates; position in work = wing, floor, grid, facade
  orientation; connection types; the deconstruction company as organisation). Version 0 is effective from
  2023 with the storage location. The ReCreate ids, status, intervention class and test and damage flags
  are kept in `attributes.recreate`; ids are uuid5 of the ReCreate element id, so a run is resumable.
- **Evidence**: `archival_document` records (concrete class, in-situ compressive strength mean where the
  notes give one, rebar spec, exposure class, smallest concrete cover) and `reinforcement_layout` records
  (basis drawing) with bars computed as centre lines from the layer tables: layer bars spaced along the
  third axis, stirrups repeated along their span, strands along the slab, mirrored with the mesh; bars
  outside the element are left out and counted in the accuracy note. The concrete class keeps the
  dataset's own name (no equivalent is invented); `FI_K30` becomes C25/30 only because a note of the
  dataset says so. No manufacturer, production date or condition grade is invented.

## Environments

| step | environment |
|---|---|
| `fetch.py`, `plan.py` | any Python 3.10 or newer; standard library only |
| `parse.py`, `geometry.py`, `preview.py`, `check_bars.py` | a virtual environment of their own with `requirements-import.txt` (openpyxl, manifold3d, trimesh, shapely, numpy, matplotlib) |
| `run.py`, `derive_local.py`, `spotcheck.py` | the backend's environment (the `csc` conda environment): backend models, `requests`, `pymongo`, `csc_gh` |

`requirements-import.txt` is not part of `src/backend/requirements.txt` or `constraints.txt`, not of
`requirements-dev.txt`, and not installed by CI (decisions 8.114, 8.145). The tests in
`tests/import_recreate/` use hand-written rows, never the Zenodo files; they skip what the environment
lacks (openpyxl, manifold3d, trimesh, shapely), and CI does not run them.

    python -m venv ../import-venv
    ../import-venv/Scripts/python.exe -m pip install -r scripts/import/requirements-import.txt

Run the scripts as `python -I -X utf8 <script> ...` (isolated mode: the data is untrusted input). Every
script takes its paths as arguments; the defaults are the places of the local rehearsal below. Computed
output goes outside the repository or into `.dev/` (git ignores it); a path anywhere else in the
repository is refused.

## Order

Paths below are the defaults (`--data` = `.dev/open_datasets/recreate/zenodo-16809738`, `--out` =
`.dev/import_open/recreate/out`).

    PY=<import-venv>/Scripts/python.exe        # openpyxl, manifold3d, trimesh
    CSC=<conda env csc>/python.exe             # backend packages

    python -I -X utf8 scripts/import/recreate/fetch.py [--dest DIR]            # Zenodo -> DIR, MD5 checked
    $PY -I -X utf8 scripts/import/recreate/parse.py [--data DIR] [--out OUT]   # parsed.json, structure.md
    $PY -I -X utf8 scripts/import/recreate/geometry.py [--out OUT]             # 120 meshes, geometry.json
    $PY -I -X utf8 scripts/import/recreate/preview.py [--out OUT]              # preview.png (visual check)
    python -I -X utf8 scripts/import/recreate/plan.py [--out OUT]              # plan.json, report.md
    $PY -I -X utf8 scripts/import/recreate/check_bars.py [--out OUT]           # bars_check.md
    $CSC -X utf8 scripts/import/recreate/run.py --dry-run [--out OUT]          # every body against the models
    $CSC -X utf8 scripts/import/recreate/run.py --server URL --username NAME   # writes through the API
    $CSC -X utf8 scripts/import/recreate/derive_local.py                       # local instance only
    $CSC -X utf8 scripts/import/recreate/spotcheck.py --out OUT                # counts and samples vs the plan

- `fetch.py` downloads every file of the record (only from `https://` URLs on `zenodo.org`; any other URL
  in the record is refused), checks each against the MD5 sum of the record (a
  mismatching file is refused and deleted, exit code 1), skips files that are already there with the right
  sum, and writes `record.json` beside the data folder.
- `parse.py` reads the files as published: columns by header text across the three header rows (the pilot
  files differ from the templates: `h1`/`v1` vs `x1`/`z1`, `Reinf_ID` vs `Reinf ID`, `Radius (mm)` vs
  `Radius/ Bevel (mm)`, `Storgage Lat`, no density column in the hollow-core files). It does no
  interpretation beyond grouping point lists; the planner maps the result to CSC records.
- `plan.py` is deterministic: the same data gives a byte-identical `plan.json` (ids are uuid5).
- `run.py --dry-run` validates every body against the backend's own models offline (`IdentityCreateBody`,
  `SnapshotDraftBody`, `EvidenceBulkItem`, `registry.prepare_record`) and must report 0 refused.
- `run.py` signs in with `--username` (the password is asked on the terminal, no echo, and exchanged at
  `POST /auth/token`) or takes a bearer token from the environment variable `CSC_IMPORT_TOKEN`. Neither is
  stored or printed. `--config FILE` may hold defaults for `server` and `username` (a local file, never
  committed). `--dataset recreate_nl`, `--only recreate:NL:` and `--limit N` narrow a run. It is
  **idempotent**: a second run finds every component by its id and creates nothing. It writes
  `<out>/run-<time>.log`.
- `derive_local.py` runs the geometry runner on the imported snapshots of a local instance (production: the
  cron of decision 8.136, `main_geometry.py --due`). It refuses a database that is not on this machine (one
  plain `mongodb://` host, no `+srv`, no host list) and an `--assets` folder that is not inside `.dev/`: it
  writes previews and proxies there, so use a copy, never the original assets. It deletes nothing.

## Local rehearsal

1. Start the instance: launch configs `backend-261012` (backend on 8791, throwaway mongod on 27791, a copy
   of the production assets in `.dev/assets-261012`) and `frontend-261012` (3100) in `.claude/launch.json`.
   Never point `--assets` at the original backup of the assets, and never run a runner with `--sweep` on it.
2. Fetch, parse, compute geometry, plan, check (the order above).
3. `run.py --dry-run`, then `run.py --server http://127.0.0.1:8791 --username dev-admin` (the password of
   the local admin account is in `.dev/dev-migrated-credentials-8791.txt`).
4. `derive_local.py`, then `spotcheck.py --out OUT --username dev-admin`.

## Production

Per dataset, one after the other (`--dataset recreate_nl`, then `recreate_de`, `recreate_fi`):

1. Fetch and check the data; run parse, geometry, plan and check_bars; read `report.md` and
   `bars_check.md`; `run.py --dry-run` must report 0 refused.
2. Sign in as an **admin**: the plan fixes the dataset ids, and only an admin may state a slug (an
   account's own dataset gets one derived from its name and a limit of three datasets). The account is made
   moderator and contributor of each dataset the run creates.
3. `run.py --server https://<api host> --username <admin> --dataset recreate_nl --dry-run`, then without
   `--dry-run`. The datasets are created **private** (visibility `members`, pieces not public).
4. The geometry stages (frame, shape class, proxies, descriptors, complexity, previews) are derived by the
   production cron (`main_geometry.py --due`, every 20 minutes; the import marks every snapshot as due); wait
   for it or run it by hand with a limit.
5. Check the result in the web app: the counts per dataset against `report.md`, and a few elements of each
   type (`spotcheck.py` reads a local database only and is for the rehearsal).
6. **Making a dataset public** (the public switch on the dataset page, `POST /datasets/{did}/public`) is a
   separate step that needs the project owner's approval; nothing in these tools does it.

A run that stopped can be started again with the same arguments.
