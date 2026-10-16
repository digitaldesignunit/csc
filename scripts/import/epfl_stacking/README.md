# Import of the EPFL stones for augmented stacking (open dataset, MIT)

Test data for the Catalog of Second Chances (decision 8.146): 452 quarry offcut stones, each a scanned point
cloud and a Poisson mesh, imported through the HTTP API with the same rules as a Grasshopper upload. The
data is **fetched from Zenodo and never committed**; this folder holds the tools only. It follows the pattern
of the ReCreate import (`scripts/import/recreate/`, decision 8.145) and reuses its guards, sign-in and
Zenodo checks (`recreate_common.py`).

Purpose: a validation of the CSC data model against a precedent component database (a scanned inventory of
irregular stone offcuts with geometry only), part of the maintainer's doctoral thesis (decision 8.147).

## Source, licence, attribution

"Dataset of mineral scraps for augmented stacking", IBOIS and EESD, EPFL; GitHub
`ibois-epfl/augmented-stacking-dataset`, release v1 (<https://github.com/ibois-epfl/augmented-stacking-dataset/tree/v1>);
archived at Zenodo, version v1, 2022-10-10, <https://doi.org/10.5281/zenodo.7180964>; licensed under the
**MIT licence**. (The README of the dataset carries a placeholder DOI of its own; the Zenodo DOI is the one
used here.) The authors are named in the dataset's own BibTeX citation: `plan.py` reads them from the
unpacked README **at run time** and writes them into the description of the imported dataset; no name or
address of a person is written into this repository.

The description of the dataset `epfl_stacking` ("EPFL: Mineral scraps for augmented stacking") carries the
attribution: the title, the authors, EPFL (IBOIS, EESD), release v1 and date, the DOI, the GitHub release, the
licence, and the statement that the meshes are reduced to the client's levels (the original is kept), that
the point clouds are multiplied by 1000 (below) and that the date of each version is the publication date,
not the scan date.

## What the data holds, and what the import does with it

Per stone `<ID>` (A0 to E56; groups A to E): `stones/mesh_high_res/remeshed_high_res_<ID>.ply` and
`stones/pcd_high_res/pcd_high_res_<ID>.ply`, ASCII PLY exported by Rhino 7 with normals and scan colours (the
mesh file also has an unused `material` element). Nothing else: no dimensions, no material, no date.

- **Units: meshes are in mm, point clouds in metres.** The authors' script (`util/rh_pcd_2_mesh.py`) meshes the
  cloud in metres and then scales the result by 1000. The published meshes are therefore millimetres (a
  stone is about 450 x 300 x 70 mm, centred at the origin), the published clouds are the same stones in
  metres, in the same position. `prepare.py` derives a factor per stone from the two bounding boxes (1000,
  or 1; within a factor of 2, because a few clouds carry stray points), multiplies the cloud by it and
  says so in the capture notes; a stone whose cloud fits neither keeps no cloud and is flagged. The meshes
  are never rescaled. Every stone is checked against 20 mm to 3000 mm on each side and flagged outside.
- **Levels, by the Grasshopper client's rules** (`csc_gh.build`, decision 8.95): the inline preview mesh is
  the mesh up to 1000 faces and 1000 faces above that (decision 8.148); a `reduced.ply` of 10000 faces for
  meshes of more than 15000 faces; the original as `detailed.ply` (binary, with its colours) above 1000
  faces; the cloud inline thinned to 1000 points and, above 1000 points, the whole cloud as `cloud.ply`. All 452 meshes have more
  than 15000 faces. Reductions are quadric decimation (`fast-simplification` through trimesh); the colours
  of a reduced mesh are those of the nearest original vertex.
- **Not watertight**: about a quarter of the meshes have holes (122 of 452 in the first run). They go up as
  they are and are counted in the report; the capture notes of such a version say so.
- **Component** (one per stone): key `epfl_stacking:<ID>`, id uuid5 of the key (so a run is resumable),
  dataset `epfl_stacking`, material `natural_stone`, original function `IfcBuildingElementProxy`
  (the data names none, but the backend requires one for a component without parents; this is the
  vocabulary's generic "Unknown"), origin `offcut` ("Quarry
  extraction offcut", no date), `attributes.epfl_stacking` with the id, group, file names and DOI. Version 0:
  named "Stone <ID>", effective from the publication date of the dataset (2022-10-10, day precision; the
  capture notes say it is not the scan date), colour = the mean colour of the scan, no capture method (the
  vocabulary has none that fits a Rhino export), the software and the source in the capture notes. No
  evidence records: the data holds no measurements.

## Environments

| step | environment |
|---|---|
| `fetch.py`, `plan.py` | any Python 3.10 or newer; standard library only |
| `prepare.py` | a virtual environment of its own with `scripts/import/requirements-import.txt` (numpy, scipy, trimesh, fast-simplification, ...) and this repository (it imports `grasshopper_lib/csc_gh`) |
| `run.py`, `spotcheck.py`, `../recreate/derive_local.py` | the backend's environment (the `csc` conda environment): backend models, `requests`, `pymongo` |

`requirements-import.txt` is shared with the ReCreate import; it is not part of `src/backend/requirements.txt`
or `constraints.txt`, not of `requirements-dev.txt`, and not installed by CI (decisions 8.114, 8.145, 8.146).
The tests in `tests/import_epfl_stacking/` use tiny spheres written as the dataset's files are, never the
dataset; they skip what the environment lacks, and CI does not run them. Run the scripts as
`python -I -X utf8 <script> ...` (isolated mode: the data is untrusted input); `prepare.py` in the import
environment. Every script takes its paths as arguments; the defaults are the local rehearsal's (`--data` =
`.dev/open_datasets/epfl_stacking/zenodo-7180964`, `--out` = `.dev/import_open/epfl_stacking/out`). Computed
output goes outside the repository or into `.dev/`; a path anywhere else in the repository is refused.

## Order

    PY=<import-venv>/Scripts/python.exe        # numpy, scipy, trimesh, fast-simplification
    CSC=<conda env csc>/python.exe             # backend packages

    python -I -X utf8 scripts/import/epfl_stacking/fetch.py [--dest DIR]            # Zenodo -> DIR, MD5, unpack
    $PY -X utf8 scripts/import/epfl_stacking/prepare.py [--data DIR] [--out OUT]    # stones/<ID>/..., prepare.json, report.md
    python -I -X utf8 scripts/import/epfl_stacking/plan.py [--out OUT] [--data DIR] # plan.json, plan-report.md
    $CSC -X utf8 scripts/import/epfl_stacking/run.py --dry-run [--out OUT]          # every body against the models
    $CSC -X utf8 scripts/import/epfl_stacking/run.py --server URL --username NAME   # writes through the API
    $CSC -X utf8 scripts/import/recreate/derive_local.py --attribute epfl_stacking  # local instance only
    $CSC -X utf8 scripts/import/epfl_stacking/spotcheck.py --out OUT --username NAME

- `fetch.py` downloads the archive of the record (631 MB; only from `https://` URLs on `zenodo.org`), checks
  its MD5 sum against the record (a mismatch is refused and deleted, exit code 1) and unpacks it by a
  **checked extraction**: a member with an absolute path, a drive letter, a `..` part or a backslash is
  refused, and nothing is extracted from an archive that holds one; a file that is already there with the right
  size is left alone, so a second run downloads and writes nothing. The record keys the archive with a folder
  (`<owner>/<file>.zip`); it lands as `<file>.zip` in `--dest`.
- `prepare.py` writes, per stone, `preview.json` (inline mesh and cloud), `reduced.ply`, `detailed.ply`,
  `cloud.ply` and `meta.json` into `<out>/stones/<ID>/` (about 600 MB for all), then `<out>/prepare.json` and
  `<out>/report.md` (counts, groups, face counts, not watertight, units, flags). A stone with a `meta.json` is
  skipped unless `--force`; `--jobs` sets the processes; `--only A0,B7` and `--limit N` narrow a run.
- `plan.py` is deterministic and reads the authors from the README; it refuses to plan when the README has
  no author field.
- `run.py --dry-run` validates every body against the backend's models (`IdentityCreateBody`,
  `SnapshotDraftBody`) and checks that every prepared file exists; it must report 0 refused.
- `run.py` signs in as `recreate/run.py` does (`--username` with the password asked, or `CSC_IMPORT_TOKEN`;
  nothing is stored or printed; `--config FILE` for local defaults, never committed). The account must be an
  **admin** (the plan fixes the dataset id). Per stone: create the identity with the inline mesh and cloud,
  `PUT` the `reduced` and `detailed` levels and the full cloud, submit, publish. **Idempotent**: a
  published stone is left alone; one that stopped in `draft`, `rejected` or `pending` goes on from where it
  was (a level the snapshot already lists in `mesh_ply_resolutions` is not sent again); a `rejected` or
  `withdrawn` snapshot is logged with its state and id. The dataset is created **private**.
- `spotcheck.py` (local rehearsal only: it reads a local database) checks the count (452) and one stone per
  group: published, location none, origin `offcut`, material, the inline preview and cloud, the listed mesh
  levels and the staged cloud as the API serves it.
- The geometry stages (frame, shape class, proxies, descriptors, complexity, previews) are derived by the
  production cron (`main_geometry.py --due`; every write marks the snapshot as due, decision 8.136); on a
  local instance `../recreate/derive_local.py --attribute epfl_stacking` does it (a local database and an
  asset copy under `.dev/` only).

## Local rehearsal

1. Start the instance: launch configs `backend-261012` (backend on 8791, throwaway mongod on 27791, a copy of
   the production assets in `.dev/assets-261012`) and `frontend-261012` (3100) in `.claude/launch.json`.
   Never point `--assets` at the original backup of the assets, and never run a runner with `--sweep` on it.
2. Fetch, prepare, plan; `run.py --dry-run`; `run.py --server http://127.0.0.1:8791 --username dev-admin`
   (the password is in `.dev/dev-migrated-credentials-8791.txt`); run it again (it creates nothing).
3. `derive_local.py --attribute epfl_stacking`, then `spotcheck.py`.

## Production

1. Fetch and prepare, read `report.md` (units, flags, not watertight), plan; `run.py --dry-run` must report 0
   refused.
2. Sign in as an **admin** and run `run.py --server https://<api host> --username <admin>`. The dataset is
   created private (members only). The account is made moderator and contributor of it.
3. The geometry stages come from the production cron; wait for it or run it by hand with a limit.
4. Check the result in the web app: the count (452) and a few stones of each group.
5. **Making the dataset public** (the public switch on the dataset page) is a separate step that needs the
   project owner's approval; nothing in these tools does it.

A run that stopped can be started again with the same arguments.
